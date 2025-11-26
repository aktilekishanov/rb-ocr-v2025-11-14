# idp-loan-service — Minimal FastAPI Plan (Just Working)

## Goals
- Provide a minimal, working HTTP service wrapping the main-dev RB-OCR pipeline.
- Async job submission with polling retrieval.
- Keep internal logic and data schemas aligned with apps/main-dev (reuse orchestrator and artifacts).

## Reuse from apps/main-dev
- Orchestrator: `rb-ocr/pipeline/orchestrator.py::run_pipeline(...)` (no changes).
- Config and artifacts:
  - `RUNS_DIR` from `pipeline/core/settings.py` (`RB_IDP_RUNS_DIR` optional override).
  - Final artifacts live under `runs/YYYY-MM-DD/<run_id>/{input,ocr,llm,meta,validation}`.
  - `meta/final_result.json` structure: `{ run_id, verdict, errors:[{code}] }`.
- Feature flags: `RB_IDP_STAMP_ENABLED=false` (disabled for minimal service).
- OCR client: Forte OCR v2; keep hardcoded base URL: `https://dev-ocr.fortebank.com/v2`.

## Service: idp-loan-service
- Framework: FastAPI + Uvicorn.
- Process model: single-process, in-memory job store plus minimal on-disk mapping for completed jobs.

## API
- POST `/v1/jobs`
  - multipart/form-data
    - `file`: required. Accept pdf/jpg/jpeg/png (or any image; orchestrator handles conversion).
    - `fio`: required string.
  - Behavior: enqueue background run and return immediately.
  - Response (202): `{ "job_id": "uuid", "status": "queued" }`
  - Notes:
    - Internally default: `reason=None`, `doc_type="Иные документы"`.
    - Internally track `run_id` once `run_pipeline` completes; not exposed in API.

- GET `/v1/jobs/{job_id}`
  - Response examples:
    - Running: `{ "job_id": "...", "status": "running", "verdict": null, "errors": [] }`
    - Completed: `{ "job_id": "...", "status": "completed", "verdict": true|false, "errors": [{"code":"..."}, ...] }`
    - Error: `{ "job_id": "...", "status": "error", "verdict": false, "errors": [{"code":"..."}] }`
  - Status vocabulary: `queued | running | completed | error`.

## Execution flow
1. POST receives `file` and `fio`.
2. Save file to a temp path (e.g., `tempfile.TemporaryDirectory`).
3. Generate `job_id = uuid4` and create an in-memory entry: `status=queued`.
4. Schedule background task to call orchestrator:
   - `run_pipeline(fio=fio, reason=None, doc_type="Иные документы", source_file_path=tmp_path, original_filename=uploaded_name, content_type=guessed_type, runs_root=RUNS_DIR)`.
5. In background:
   - Set status `running`.
   - On completion: set `completed` or `error` based on returned dict; persist `{job_id -> run_id, status, final_result_path}` into `RUNS_DIR/jobs_index.json`.
6. GET reads from in-memory job store; if `completed`, read `final_result.json` for `{verdict, errors}`; else show `running/queued`.
   - Optionally, if not found in memory, read `jobs_index.json` to recover completed jobs across restarts and then load `final_result.json`.

## Minimal persistence
- File: `<RUNS_DIR>/jobs_index.json` (append/update per `job_id`).
  - Structure (example): `{ "job_id": { "run_id": "...", "status": "completed", "final_result_path": "..." }, ... }`.
  - This enables GET after process restarts for completed jobs.

## Directory layout (service)
- `apps/idp-loan-service/`
  - `main.py` (FastAPI app, endpoints, background tasks, job store)
  - `requirements.txt` (fastapi, uvicorn[standard], python-multipart, httpx, pydantic, rapidfuzz, pypdf, PyPDF2)
  - `README.md` (how to run)

## Config
- `RB_IDP_RUNS_DIR` (optional) — override runs root; else use main-dev default.
- `RB_IDP_STAMP_ENABLED=false` (default in config; no action needed).
- `OCR_BASE_URL` — not required (hardcoded in main-dev OCR client to dev-ocr v2).

## Error handling
- Return 400 if `file` or `fio` missing.
- Surface pipeline error codes from `final_result.json` as-is (`errors:[{code}]`).
- Map internal exceptions in background task to `status=error` with synthetic code `INTERNAL_ERROR` when `final_result.json` not produced.

## Dependencies
- `fastapi`, `uvicorn[standard]`, `python-multipart`
- Reuse main-dev deps: `httpx`, `pydantic>=2`, `rapidfuzz`, `pypdf` or `PyPDF2` (already used), etc.

## Implementation steps
1. Create `apps/idp-loan-service` folder with `main.py`, `requirements.txt`, `README.md`.
2. Implement in-memory `JobsStore` with thread-safe dict and file-backed `jobs_index.json` updater.
3. Implement POST `/v1/jobs`:
   - Validate inputs.
   - Save to tmp; enqueue `run_pipeline` via `BackgroundTasks` or a `ThreadPoolExecutor`.
   - Return 202 with `{job_id, status:"queued"}`.
4. Implement GET `/v1/jobs/{job_id}`:
   - Lookup in memory; if completed, load `final_result.json` and return verdict/errors.
   - If missing in memory, attempt to read `<RUNS_DIR>/jobs_index.json` to serve completed jobs.
5. Run server: `uvicorn main:app --host 0.0.0.0 --port 8000`.
6. Smoke test: upload a <=3-page PDF + fio; poll GET until `completed`.

## Limitations (acceptable for MVP)
- Jobs in progress are not recovered after service restart (only completed jobs can be served via `jobs_index.json`).
- No rate limiting or auth.
- Single-process background execution (no distributed queue).
- Uses local filesystem; no S3/Kafka integration in this MVP.

## Future improvements (optional)
- Persist live jobs to disk; resume on startup.
- Replace background tasks with a work queue (RQ/Celery) if needed.
- Add Prometheus metrics and structured logging similar to main-dev StageTimers.
- Add configurable OCR/LLM URLs and timeouts, and retry/backoff policies.
