# Phase 1 — What, Why, How (Detailed Explanation)

This document explains every component implemented in Phase 1 of the standalone FastAPI service, covering what it is, why we need it, and how it works at runtime.

---

## 0) Phase 1 goal (recap)

- Expose a synchronous API endpoint `POST /v1/process` that accepts:
  - a document file (PDF/JPG/PNG), and
  - required `fio` string (full name, used by pipeline validation in future phases).
- Return a simple JSON: `{ run_id: <UUID v4>, verdict: bool, errors: [] }`.
- Persist internal artifacts locally under `RUNS_DIR/YYYY-MM-DD/<run_id>/` for audit.
- Keep the implementation isolated from `main-dev` (no cross-imports).

---

## 1) API Layer — `app/api/v1/routes_process.py`

- **What it is**
  - A FastAPI router that defines the `POST /v1/process` endpoint.

- **Why needed**
  - Provides the single entrypoint for synchronous document processing.
  - Establishes a clear external contract for clients while hiding internal artifacts.

- **How it works**
  - Validates inputs: `file` (required) + `fio` (required).
  - Performs simple file-type validation by extension: allows only `.pdf`, `.jpg`, `.jpeg`, `.png`. Others return `400`.
  - Streams the uploaded file to a secure temporary path (without loading the entire content into memory at once).
  - Calls the pipeline runner (`run_sync_pipeline(fio, source_file_path)`).
  - Returns a `ProcessResponse` model with `run_id` (UUID v4 string), `verdict`, `errors`.
  - Logs key events with request ID (via middleware from Phase 0) for correlation.
  - Ensures temp file cleanup in a `finally` block.

---

## 2) Models — `app/models/schemas.py`

- **What it is**
  - Pydantic models for request/response shapes and future error structures.

- **Why needed**
  - Make the API contract explicit and self-documenting.
  - Enable FastAPI to auto-generate OpenAPI docs and validate responses.

- **How it works**
  - `ProcessResponse` defines response fields:
    - `run_id: str` (UUID v4 string)
    - `verdict: bool`
    - `errors: list[str]` (simple for Phase 1; can be upgraded later)
  - `ErrorItem` is included for future use (structured error objects, e.g., with `code` and optional `message`).
  - `ProcessRequestMeta` holds required `fio` for explicitness and future reuse, though the endpoint currently binds directly from `Form`.

---

## 3) Pipeline Runner — `app/services/pipeline_runner.py`

- **What it is**
  - A minimal orchestration function (`run_sync_pipeline`) for Phase 1.

- **Why needed**
  - Central place to generate `run_id`, coordinate storage writes, and produce the response shape used by the API.
  - Encapsulates pipeline concerns so the API layer remains thin and focused.

- **How it works**
  - Generates a proper RFC 4122 UUID v4 as `run_id`.
  - Initializes local storage (see next section) using `RUNS_DIR` from settings.
  - Saves the input file under the run directory.
  - Writes `meta/metadata.json` with the provided `fio` and file origin path.
  - Computes a stubbed verdict (`True`) and empty `errors` list for Phase 1.
  - Writes `meta/final_result.json` with `run_id`, `verdict`, and `errors`.
  - Returns an in-memory dict consumed by the API (`ProcessResponse`).

---

## 4) Storage Abstraction — `app/services/storage/base.py`, `local_disk.py`

- **What it is**
  - A simple storage interface (`Storage`) with a local filesystem implementation (`LocalStorage`).

- **Why needed**
  - Clean separation of concerns: business logic works against an interface, not a concrete filesystem.
  - Eases future migration to MinIO/S3 by swapping implementations without changing API/pipeline code.

- **How it works**
  - Directory layout for each run:
    - `RUNS_DIR/YYYY-MM-DD/<run_id>/input/` — the uploaded document (named `document<ext>`)
    - `RUNS_DIR/YYYY-MM-DD/<run_id>/meta/` — metadata and results (`metadata.json`, `final_result.json`)
  - `save_input_file(source_path, run_id)`
    - Creates necessary directories.
    - Copies the temp file into the run’s `input/` directory.
    - Returns the saved path as string.
  - `write_json(run_id, relative_path, obj)`
    - Creates parent directories.
    - Writes JSON in UTF-8 with indentation for readability.

---

## 5) App Wiring — `app/main.py`

- **What it is**
  - The application entrypoint that initializes settings, logging, middleware, and routes.

- **Why needed**
  - Provides a single ASGI app for `uvicorn` to serve.
  - Centralizes bootstrap (settings + logging) and lifecycle hooks.

- **How it works**
  - Loads settings via `get_settings()` and configures logging.
  - Adds `RequestIdMiddleware` so every log has a `request_id`.
  - Includes routers: health (`/health`, `/ready`) and process (`/v1/process`).
  - Logs `service_startup` and `service_shutdown` events.

---

## 6) Dependencies — `requirements.txt`

- **What it is**
  - Python dependencies needed to run Phase 0 + Phase 1.

- **Why needed**
  - `python-multipart` is required by FastAPI to parse multipart file uploads.

- **How it works**
  - `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `python-multipart` are specified with reasonable version caps.

---

## 7) Tests — `tests/test_smoke.py`

- **What it is**
  - A basic smoke test suite that verifies the service boots and main flows work.

- **Why needed**
  - Early regression detection and confidence when evolving the pipeline/storage.

- **How it works**
  - Uses `fastapi.testclient.TestClient` to:
    - Assert `/health` returns 200.
    - Assert `/ready` returns 200.
    - Assert `/v1/process` with a small in-memory PDF-like payload returns 200 and includes `run_id`, `verdict`, `errors`.
    - Assert `/v1/process` rejects unsupported file extensions with 400 and a clear message.

---

## 8) Runtime behavior (end-to-end)

1. Client sends `multipart/form-data` with:
   - `file=@...` (must be pdf/jpg/jpeg/png)
   - `fio=...` (required string)
2. The API performs extension validation and streams the file to a temporary path.
3. The pipeline runner generates a UUID `run_id`, persists the input and metadata, computes a stub verdict, writes `final_result.json`, and returns a result object.
4. The API serializes and returns the `ProcessResponse` JSON.
5. Artifacts exist under `RUNS_DIR/YYYY-MM-DD/<run_id>/` for audit.

---

## 9) Key guarantees and best practices followed

- **Correct external ID**: `run_id` is a proper UUID v4 string.
- **Single entrypoint**: A single `/v1/process` endpoint, matching tech lead guidance.
- **Isolation**: No imports from `main-dev`; this service is standalone.
- **Observability**: Request ID middleware in logs for correlation; clean info/error logs.
- **Security & robustness (basic)**: Input type checks; temp files cleaned; minimal error surfaces.
- **Extensibility**: Storage abstraction enables swapping to S3/MinIO; `ErrorItem` ready for structured errors; easy to plug in real OCR/LLM in runner.

---

## 10) How to run locally

```bash
uvicorn app.main:app --reload
```

Then test:

```bash
curl -X POST "http://localhost:8000/v1/process" \
  -F "file=@/Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/dekret-prikaz-multiple.pdf" \
  -F "fio=Иванов Иван Иванович"
```

Expected response:

```json
{
  "run_id": "123e4567-e89b-12d3-a456-426614174000",
  "verdict": true,
  "errors": []
}
```

Artifacts will be in:
```
apps/idp-loan-deferment-service/runs/YYYY-MM-DD/<run_id>/
  input/document.pdf
  meta/metadata.json
  meta/final_result.json
```

---

## 11) What’s next (preview)

- Replace stub logic with real OCR/LLM processors and validator.
- Upgrade `errors` to structured `ErrorItem` with stable codes.
- Add S3/MinIO storage and Kafka ingestion (Phase 2+) without changing the API contract.
