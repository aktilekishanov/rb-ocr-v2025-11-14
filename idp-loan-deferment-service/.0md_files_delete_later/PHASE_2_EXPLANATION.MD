# Phase 2 — Async Jobs (What, Why, How)

This document explains everything implemented in **Phase 2** of the standalone FastAPI service:
- what each new component is,
- why it is needed,
- how it works at runtime.

Phase 2 adds **async job submission** on top of the synchronous Phase 1 pipeline, using FastAPI `BackgroundTasks` and a small in-memory job store.

---

## 0) Phase 2 goal (recap)

From `REPORT_3.MD`:
- Add **better UX under load** by introducing async jobs:
  - `POST /v1/jobs` — submits work, returns quickly with `{ run_id, status: "accepted" }`.
  - `GET /v1/jobs/{run_id}` — returns job `status`, `verdict`, and `errors` when done.
- Keep the core work (the pipeline) **the same**: still handled by the Phase 1 runner.
- No Kafka, Celery, Redis yet — just a simple in-process async pattern.

In other words: move from “client waits for the whole pipeline” to “client submits job, then polls for result” without changing the business logic.

---

## 1) API Layer — `app/api/v1/routes_jobs.py`

### What it is
A new FastAPI router that exposes **two endpoints**:
- `POST /v1/jobs` — submit a job.
- `GET /v1/jobs/{run_id}` — check job status.

### Why needed
- Some clients do **not** want to hold an HTTP connection open until all OCR/LLM/validation work is done.
- Async jobs allow:
  - Better perceived performance.
  - Simplified error handling and retries on the client side.
  - A natural path to future Kafka / worker-based architectures.

### How it works

#### `POST /v1/jobs`

- **Inputs**:
  - `file: UploadFile` — same as Phase 1.
  - `fio: str` — required, same reason as in Phase 1 (validation / name match in future).

- **Steps**:
  1. **Logging**: logs `job_submit_request_received` with filename/content type and `request_id` from middleware.
  2. **File-type validation**:
     - Extracts file extension (`.pdf`, `.jpg`, `.jpeg`, `.png` are allowed).
     - If not allowed → `HTTP 400` with a clear error message.
  3. **Streaming to temp file**:
     - Reads the uploaded file in chunks.
     - Writes to a temporary file on disk (like Phase 1) to avoid holding the whole file in memory.
  4. **Job submission**:
     - Calls `submit_job(background_tasks, file_temp_path=temp_path, fio=fio)` from `app.services.jobs`.
     - This function:
       - Generates a new `run_id` (UUID v4).
       - Creates an initial job record (status `accepted`) in memory and on disk.
       - Schedules a background task that will later run the pipeline.
  5. **Response**:
     - Immediately returns `JobSubmitResponse(run_id=<uuid>, status="accepted")`.

- **Error handling**:
  - If reading the upload fails → `400` with reason.
  - If anything goes wrong **before** scheduling the background task → cleans up the temp file and returns `500` with a generic message, logging the real error.

#### `GET /v1/jobs/{run_id}`

- **Inputs**:
  - `run_id: str` path parameter.

- **Steps**:
  1. Calls `get_job_status(run_id)` from `app.services.jobs`.
  2. If a job record is found in memory, returns it as `JobStatusResponse`.
  3. If not found, returns `404 Job not found` for Phase 2.
     - (Future upgrade could use `meta/job.json` on disk to reconstruct status after a restart.)

- **Outputs** (`JobStatusResponse`):
  - `run_id: str`
  - `status: "accepted" | "running" | "completed" | "failed"`
  - `verdict: bool | None` (only set when completed)
  - `errors: list[str] | None` (only set when completed/failed)

---

## 2) Models — `app/models/schemas.py`

### What it is
Additional Pydantic models and type aliases for Phase 2 job API:
- `JobStatus` — allowed job statuses.
- `JobSubmitResponse` — response for job submission.
- `JobStatusResponse` — response for job status.

### Why needed
- Keep the async API contract **explicit and typed**.
- Ensure FastAPI automatically documents and validates the new endpoints.

### How it works

- `JobStatus = Literal["accepted", "running", "completed", "failed"]`
  - A type alias for allowed status strings.

- `JobSubmitResponse`:
  ```python
  class JobSubmitResponse(BaseModel):
      run_id: str
      status: Literal["accepted"]
  ```
  - Ensures the only valid status in submit response is exactly `"accepted"`.

- `JobStatusResponse`:
  ```python
  class JobStatusResponse(BaseModel):
      run_id: str
      status: JobStatus
      verdict: bool | None = None
      errors: list[str] | None = None
  ```
  - Provides a consistent JSON shape for polling.

---

## 3) Job Service — `app/services/jobs.py`

### What it is
A small service module that manages jobs and their lifecycle:
- In-memory job records.
- Disk persistence to `meta/job.json`.
- Background pipeline execution wrapper.

### Why needed
- Centralizes job state management instead of doing it ad-hoc in the route.
- Keeps responsibilities clear:
  - Routes: HTTP and input/output handling.
  - Jobs service: lifecycle, status transitions, integration with the pipeline.

### How it works

#### Internal structures
- `_jobs: dict[str, dict[str, Any]]`
  - Maps `run_id` → `{status, verdict, errors}`.
- `_lock: threading.Lock()`
  - Ensures thread-safe access to `_jobs` since background tasks may run concurrently.
- `_storage()` helper
  - Returns a `LocalStorage` instance bound to `RUNS_DIR`.

#### Disk persistence helper
- `_write_job_json(run_id, payload)`
  - Uses `LocalStorage.write_json(run_id, "meta/job.json", payload)`.
  - Logs an error if write fails, but does not crash the app.

#### Lifecycle functions

- `create_job_record(run_id)`
  - Sets initial in-memory state: `{"status": "accepted", "verdict": None, "errors": None}`.
  - Writes this to `meta/job.json`.

- `set_running(run_id)`
  - Updates in-memory state to `status="running"`.
  - Writes updated `job.json`.

- `set_completed(run_id, verdict, errors)`
  - Updates in-memory state to `status="completed"`, with actual `verdict` and `errors` (list of strings).
  - Writes final `job.json` snapshot.

- `set_failed(run_id, error)`
  - Updates in-memory state to `status="failed"`, `verdict=None`, `errors=[error]`.
  - Writes final `job.json` snapshot.

- `get_job_status(run_id)`
  - Returns `{run_id, status, verdict, errors}` dict or `None` if job is unknown.

#### Background processing

- `submit_job(background_tasks, file_temp_path, fio) -> str`
  - Generates a new `run_id` (UUID v4).
  - Calls `create_job_record(run_id)`.
  - Schedules:
    ```python
    background_tasks.add_task(process_job_sync, run_id, file_temp_path, fio)
    ```
  - Logs `job_submitted` with `run_id`.
  - Returns `run_id`.

- `process_job_sync(run_id, file_temp_path, fio)`
  - **Why**: FastAPI `BackgroundTasks` runs sync callables; our pipeline is async.
  - Creates a small bridge that runs the async pipeline function with `asyncio.run(...)` in this background thread.
  - If any top-level exception escapes, it marks the job as failed.

- `_process_job_async(run_id, file_temp_path, fio)`
  - **Actual async implementation**:
    - Calls `set_running(run_id)`.
    - Calls Phase 1 pipeline: `run_sync_pipeline(fio=fio, source_file_path=file_temp_path, run_id=run_id)`.
      - Passing `run_id` ensures the same ID is used for artifacts and for the job.
    - Extracts `verdict` and `errors` from pipeline result.
    - Calls `set_completed(...)` on success.
    - Calls `set_failed(...)` on exception.
    - Cleans up the temp file (`os.unlink(file_temp_path)`) in a `finally` block.

Net effect: once a job is submitted, its status is updated through the lifecycle and persisted to `meta/job.json` while the pipeline work happens asynchronously.

---

## 4) Pipeline runner update — `app/services/pipeline_runner.py`

### What it is
A small change to the Phase 1 pipeline runner:
- `run_sync_pipeline` can now **accept an optional `run_id`**.

### Why needed
- For Phase 1, the runner always generated its own `run_id`.
- For Phase 2, the **job layer** generates `run_id` first, and we need the same ID to:
  - Identify the job,
  - Name the run directory,
  - Write artifacts.

### How it works

Before:
```python
async def run_sync_pipeline(*, fio: str, source_file_path: str) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    ...
```

After:
```python
async def run_sync_pipeline(*, fio: str, source_file_path: str, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or str(uuid.uuid4())
    ...
```

- If `run_id` is provided (Phase 2 jobs): it is reused.
- If not provided (Phase 1 `/v1/process`): it falls back to generating a new UUID v4.

All other behavior (saving input, writing `metadata.json` and `final_result.json`) remains the same.

---

## 5) App wiring — `app/main.py`

### What it is
A small change to include the new jobs router.

### Why needed
- The FastAPI application must register the `/v1/jobs` routes so they become accessible.

### How it works

`app/main.py` now imports and includes:

```python
from app.api.v1.routes_jobs import router as jobs_router
...
app.include_router(health_router)
app.include_router(process_router)
app.include_router(jobs_router)
```

No other startup/shutdown behavior was changed. Logging, settings, and request ID middleware remain as defined in Phase 0.

---

## 6) Runtime behavior (end-to-end Phase 2)

1. **Submit job** (`POST /v1/jobs`):
   - Client uploads file + `fio`.
   - Service checks extension and writes a temp file.
   - `submit_job(...)` is called:
     - Generates `run_id`.
     - Creates job record `status=accepted` in memory and writes `meta/job.json`.
     - Schedules background `process_job_sync`.
   - API immediately returns `{ "run_id": "...", "status": "accepted" }`.

2. **Background processing**:
   - `process_job_sync` calls `_process_job_async` via `asyncio.run`.
   - `_process_job_async`:
     - Sets `status=running`, updates `job.json`.
     - Calls `run_sync_pipeline(...)` to run the existing Phase 1 pipeline.
     - On success: `status=completed`, writes `verdict` and `errors` to in-memory store and `job.json`.
     - On exception: `status=failed`, with a short error message.
     - Deletes the temp file.

3. **Poll status** (`GET /v1/jobs/{run_id}`):
   - Client calls repeatedly.
   - Gets:
     - `status="accepted"` just after submission.
     - Soon after, `status="running"`.
     - Finally, `status="completed"` (and `verdict`, `errors`) or `status="failed"`.

4. **Artifacts**:
   - As in Phase 1, are written under `RUNS_DIR/YYYY-MM-DD/<run_id>/...` using the shared `run_id`.
   - `meta/job.json` contains the last known status and result.

---

## 7) Key guarantees and best practices followed

- **API stability**: Phase 1 `/v1/process` is unchanged; Phase 2 adds new `/v1/jobs` endpoints.
- **Correct ID usage**: The same `run_id` identifies both the job and the pipeline run directory.
- **Async-friendly design**: Uses FastAPI `BackgroundTasks` in a safe way, bridging to an async pipeline runner.
- **Thread safety**: Job store is protected by a lock; background tasks do not race writing the same dictionary.
- **Observability**: Logs job lifecycle (`job_submitted`, `running`, `completed`, `failed`) with `run_id` and `request_id`.
- **Extensibility**: Clear separation of job orchestration (jobs.py) from pipeline logic; easy to migrate to real workers (Celery, Kafka consumers) later.

---

## 8) How to test Phase 2 manually

1. **Submit job**:
   ```bash
   curl -s -X POST "http://localhost:8000/v1/jobs" \
     -F "file=@/path/to/sample.pdf" \
     -F "fio=Иванов Иван Иванович"
   ```

   Expected:
   ```json
   { "run_id": "<uuid>", "status": "accepted" }
   ```

2. **Poll status**:
   ```bash
   curl -s "http://localhost:8000/v1/jobs/<uuid>"
   ```

   Expected progression:
   - `{"run_id":"...","status":"running","verdict":null,"errors":null}`
   - then `{"run_id":"...","status":"completed","verdict":true,"errors":[]}`

3. **Filesystem**:
   - Check `runs/YYYY-MM-DD/<run_id>/meta/job.json` to see the final status persisted.

4. **Negative tests**:
   - Submit with unsupported file type → expect `400`.
   - Query with non-existing `run_id` → expect `404`.

This completes the explanation of Phase 2: async jobs built on top of the existing Phase 1 pipeline, using BackgroundTasks, an in-memory job store, and disk-backed `job.json` status.
