# Phase 2 — Async Jobs (BackgroundTasks) Implementation Plan

Scope: add an asynchronous job submission flow on top of Phase 1.
- `POST /v1/jobs` — accept the same inputs as Phase 1 (`file`, required `fio`), return quickly with `{ run_id, status: "accepted" }`.
- `GET /v1/jobs/{run_id}` — return `{ status, verdict, errors }` when available.
- Use FastAPI `BackgroundTasks` to run the existing Phase 1 pipeline in the background.
- Persist basic job status to disk for audit; keep an in-memory job store for live status.

No Celery/Redis in this phase; that’s a later upgrade.

---

## 1. High‑level design of Phase 2

User journey:
1. Client sends `POST /v1/jobs` with:
   - `file` (PDF/JPG/PNG)
   - `fio` (required string)
2. Service:
   - Generates a new `run_id` (UUID v4).
   - Records job status as `accepted` in an in-memory store and writes an initial job file to disk.
   - Schedules a background task to execute the Phase 1 pipeline.
   - Immediately returns `{ run_id, status: "accepted" }`.
3. Background task:
   - Marks status `running`.
   - Calls the Phase 1 `run_sync_pipeline(...)` to do the work (save file, write artifacts, compute verdict/errors).
   - On success: marks status `completed`, stores `verdict` and `errors`.
   - On exception: marks status `failed`, stores error information.
   - Updates `runs/<date>/<run_id>/meta/job.json` throughout.
4. Client polls `GET /v1/jobs/{run_id}` until status is `completed` or `failed`.

Statuses lifecycle: `accepted` → `running` → `completed|failed`.

---

## 2. New files to create or extend

Under `apps/idp-loan-deferment-service/`:

### 2.1 API layer – `/v1/jobs`
- `app/api/v1/routes_jobs.py`
  - New router module for async job endpoints.

### 2.2 Models – request/response shapes
- Extend `app/models/schemas.py` with:
  - `JobSubmitResponse` → `{ run_id: str, status: Literal["accepted"] }`
  - `JobStatus` (Literal type) → `"accepted" | "running" | "completed" | "failed"`
  - `JobStatusResponse` → `{ run_id: str, status: JobStatus, verdict: bool | None, errors: list[str] | None }`

### 2.3 Services – job store and orchestration
- `app/services/jobs.py`
  - In-memory job registry with a simple thread-safe structure:
    - `create_job(run_id) -> None`
    - `set_running(run_id) -> None`
    - `set_completed(run_id, verdict: bool, errors: list[str]) -> None`
    - `set_failed(run_id, error: str) -> None`
    - `get(run_id) -> dict`
  - Integrate with disk persistence via the storage layer: write `meta/job.json` on every transition.
  - Use a `threading.Lock` to guard the in-memory map since BackgroundTasks can run concurrently.

### 2.4 Reuse – storage and pipeline
- Reuse `app/services/storage/local_disk.py` and `app/services/pipeline_runner.py` from Phase 1.
  - The background task calls `run_sync_pipeline(...)` and converts its result to job status fields.

---

## 3. `routes_jobs.py` – API design and behavior

### 3.1 Router and endpoint signatures

```python
from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Request
from app.models.schemas import JobSubmitResponse, JobStatusResponse
from app.services.jobs import submit_job, get_job_status

router = APIRouter(prefix="/v1", tags=["jobs"])

@router.post("/jobs", response_model=JobSubmitResponse)
async def submit(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    fio: str = Form(...),
):
    # file-type extension validation (same as Phase 1)
    # stream to temp path, then call submit_job(...), passing background_tasks
    ...

@router.get("/jobs/{run_id}", response_model=JobStatusResponse)
async def status(run_id: str) -> JobStatusResponse:
    # fetch from in-memory store; if not found, optionally check disk meta/job.json
    ...
```

### 3.2 Steps inside `POST /v1/jobs`
1. Validate extension: only allow `.pdf|.jpg|.jpeg|.png`.
2. Stream the upload to a temp file (do not keep entire file in memory).
3. Generate `run_id` and create the initial job record: `status=accepted`.
4. Schedule background handler with `BackgroundTasks`:
   - The handler marks `running`.
   - Calls `run_sync_pipeline(fio=fio, source_file_path=temp_path)`.
   - On success → `completed` with `verdict/errors`.
   - On exception → `failed` with a short error message.
   - Deletes the temp file in a `finally` block.
5. Immediately return `JobSubmitResponse(run_id=..., status="accepted")`.

### 3.3 Steps inside `GET /v1/jobs/{run_id}`
- Return the current in-memory job record as `JobStatusResponse`.
- If not found in memory (edge case after restart):
  - Optionally attempt to read `meta/job.json` and reconstruct status.
  - If still not found, return 404.

---

## 4. `schemas.py` – data models

Additions (conceptual):
```python
from typing import Literal

JobStatus = Literal["accepted", "running", "completed", "failed"]

class JobSubmitResponse(BaseModel):
    run_id: str
    status: Literal["accepted"]

class JobStatusResponse(BaseModel):
    run_id: str
    status: JobStatus
    verdict: bool | None = None
    errors: list[str] | None = None
```

---

## 5. `jobs.py` – in-memory job store and background handler

### 5.1 Responsibilities
- Maintain a thread-safe in-memory dictionary: `run_id -> {status, verdict, errors}`.
- Persist status to `meta/job.json` in the run directory on each transition.
- Provide helper `submit_job(background_tasks, file_temp_path, fio) -> run_id` that:
  - Generates `run_id`.
  - Creates initial job in memory and writes `job.json` with `status=accepted`.
  - Adds `background_tasks.add_task(process_job, run_id, file_temp_path, fio)`.

### 5.2 `process_job` outline
```python
async def process_job(run_id: str, file_temp_path: str, fio: str) -> None:
    try:
        set_running(run_id)
        result = await run_sync_pipeline(fio=fio, source_file_path=file_temp_path)
        set_completed(run_id, verdict=bool(result.get("verdict")), errors=list(result.get("errors", [])))
    except Exception as e:
        set_failed(run_id, error=str(e)[:200])
    finally:
        # best-effort cleanup of temp file
        ...
```

### 5.3 Disk persistence of job status
- Path: `RUNS_DIR/YYYY-MM-DD/<run_id>/meta/job.json`.
- Contents (example): `{ "run_id": "...", "status": "running", "verdict": null, "errors": [] }`.
- Update on every transition.

---

## 6. Wiring everything together

### 6.1 Include `/v1/jobs` router
In `app/main.py`:
```python
from app.api.v1.routes_jobs import router as jobs_router
app.include_router(jobs_router)
```

### 6.2 Logging & request IDs
- Reuse Phase 0 logging + middleware.
- Log `job_submitted`, `job_started`, `job_completed`, `job_failed` with `run_id`.

### 6.3 Config (optional additions)
- Optionally add `IDP_JOBS_MAX_IN_MEMORY` to cap the in-memory registry size.
- Optionally add `IDP_JOB_RETENTION_MINUTES` for future cleanup logic.

---

## 7. How to test Phase 2

### 7.1 Manual with curl
1. Submit job:
```bash
curl -s -X POST "http://localhost:8000/v1/jobs" \
  -F "file=@/path/to/sample.pdf" \
  -F "fio=Иванов Иван Иванович"
```
Expected:
```json
{ "run_id": "<uuid>", "status": "accepted" }
```

2. Poll status:
```bash
curl -s "http://localhost:8000/v1/jobs/<uuid>"
```
Expected progression:
- `{"run_id":"...","status":"running","verdict":null,"errors":null}`
- then `{"run_id":"...","status":"completed","verdict":true,"errors":[]}`

3. Invalid file type still returns 400 on submit (`/v1/jobs`).

### 7.2 Automated tests (optional for Phase 2)
- Add `tests/test_jobs.py` with FastAPI `TestClient`:
  - Submit job and assert `status=accepted`.
  - Poll status until `completed` with a timeout.
  - Assert `run_id` folder exists with `meta/job.json` updated.
  - Negative: unsupported extension → 400.

---

## 8. Acceptance criteria for Phase 2
- Service exposes async endpoints:
  - `POST /v1/jobs` returns `{ run_id, status: "accepted" }` quickly.
  - `GET /v1/jobs/{run_id}` returns live job status, verdict, and errors.
- Background task runs the Phase 1 pipeline without blocking the request.
- In-memory job store tracks status across the lifecycle.
- `meta/job.json` is written/updated under each run directory.
- Logging contains job lifecycle entries with `run_id`.

---

## 9. Notes & future upgrades
- In-memory store is **ephemeral**; a restart clears it. Disk `job.json` provides fallback info, but for robust production tracking migrate to **Redis + Celery** in the next phase.
- BackgroundTasks run in the same process; for heavy workloads, move to a worker queue.
- No API contract changes for Phase 1; Phase 2 is additive.
