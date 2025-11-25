# Phase 1 – Sync Processing (MVP API) Implementation Plan

Scope: implement the **first real API endpoint** of the service:
- `POST /v1/process` – synchronously processes a single document and returns:
  - `run_id` (string UUID, for example `"123e4567-e89b-12d3-a456-426614174000"`)
  - `verdict` (true / false)
  - `errors` (array of objects or strings, depending on design; at minimum, list of error codes)

Artifacts (files, JSONs) are still stored **locally on disk** under `RUNS_DIR`, for internal audit and debugging only. They are **not** exposed directly in the API response.

No async jobs, no Kafka, no MinIO/S3 in this phase.

---

## 1. High-level design of Phase 1

User journey for this phase:

1. Client sends `POST /v1/process` with:
   - Document file (PDF/JPG/PNG).
   - Required field: `fio` (full name of the client), used later by the pipeline to validate extracted data against the provided name.
2. Service:
   - Validates input.
   - Creates a new `run_id` and per-run directory under `RUNS_DIR`.
   - Saves the uploaded file.
   - Runs a **simplified pipeline** (for Phase 1 we can stub out some heavy parts if necessary, but the structure should be ready for real OCR/LLM logic):
     - Stage 1: acquire (save file, capture metadata).
     - Stage 2: (later) OCR.
     - Stage 3: (later) LLM-based checks.
     - Stage 4: validate and compute `verdict` + `errors`.
   - Writes basic artifacts to disk (e.g. a `final_result.json` for internal use).
3. Service returns JSON (note: `run_id` is a real UUID, example shortened here):

```json
{
  "run_id": "123e4567-e89b-12d3-a456-426614174000",
  "verdict": true,
  "errors": []
}
```

For Phase 1, it is acceptable to **start with a minimal pipeline implementation** (e.g. fake verdict logic) as long as the structure is correct and we can later plug in real OCR/LLM processors.

---

## 2. New files to create or extend

Under `apps/idp-loan-deferment-service/`:

### 2.1 API layer – `/v1/process`

- `app/api/v1/routes_process.py`
  - New router module for processing endpoints.

### 2.2 Models – request/response shapes

- `app/models/schemas.py`
  - Pydantic models for:
    - `ProcessRequestMeta` – metadata part (required `fio`, used for validation in the pipeline).
    - `ProcessResponse` – output (`run_id`, `verdict`, `errors`).
    - `ErrorItem` – optional structured error object (e.g. `{ code: str, message: Optional[str] }`).

### 2.3 Services – pipeline orchestration

- `app/services/pipeline_runner.py`
  - Contains the high-level `run_sync_pipeline(...)` function used by `/v1/process`.
  - In Phase 1, this function can:
    - Accept metadata and a saved file path.
    - Generate `run_id`.
    - Create per-run directories under `settings.RUNS_DIR`.
    - Save metadata and final result JSON.
    - Return an in-memory result object with `run_id`, `verdict`, and `errors`.

### 2.4 Services – storage abstraction (local only for now)

- `app/services/storage/base.py`
  - Define a minimal interface/protocol for storage operations (even if we only implement local disk now):
    - `save_input_file(temp_path: str, run_id: str) -> str`
    - `write_json(run_id: str, relative_path: str, obj: dict) -> str`
    - Optionally: helpers for directory creation.

- `app/services/storage/local_disk.py`
  - Implement the above interface using `settings.RUNS_DIR`.
  - Responsibilities:
    - Create `runs/YYYY-MM-DD/<run_id>/input/` and `meta/` folders, where `<run_id>` is a UUID string.
    - Move or copy the uploaded file into the `input` folder.
    - Write JSON files (e.g. `meta/metadata.json`, `meta/final_result.json`).

> Note: For Phase 1 we can keep the storage interface **very small** and expand it later.

### 2.5 Tests (optional initial smoke)

- `tests/test_smoke.py`
  - Add at least one simple test that calls `/health` and `/ready`.
  - Optionally, add a basic test for `/v1/process` with a dummy small file.

---

## 3. `routes_process.py` – API design and behavior

### 3.1 Router and endpoint signature

Implementation outline:

```python
from fastapi import APIRouter, UploadFile, File, Form, Depends, Request
from app.models.schemas import ProcessResponse
from app.services.pipeline_runner import run_sync_pipeline

router = APIRouter(prefix="/v1", tags=["process"])


@router.post("/process", response_model=ProcessResponse)
async def process_document(
    request: Request,
    file: UploadFile = File(...),
    fio: str = Form(...),
):
    ...
```

### 3.2 Steps inside the endpoint

1. **Logging and request ID**
   - Get a logger via `get_logger(__name__)`.
   - Optionally log basic request information (path, filename).

2. **Validation**
   - Basic validation is handled by FastAPI and Pydantic (required `Form(...)` and `File(...)`).
   - You can add simple custom checks for file type if needed (e.g. allow only pdf/jpg/png).

3. **Temporary file handling**
   - Read the uploaded file and write it to a temporary location (e.g. using Python's `tempfile` module).
   - Pass the temp path to `run_sync_pipeline(...)`.

4. **Call the pipeline service**
   - `result = await run_sync_pipeline(fio=fio, source_file_path=temp_path)`
     - Even if `run_sync_pipeline` is synchronous, we can call it in a threadpool or synchronous context for now; optimization to async can come later.

5. **Build response**
   - Extract `run_id`, `verdict`, and `errors` from the pipeline result.
   - Return `ProcessResponse(run_id=..., verdict=..., errors=...)`.

6. **Error handling**
   - Catch unexpected exceptions, log them with `request_id` and path, and return a 500-style error.
   - For Phase 1, keep it simple: generic error code or message.

---

## 4. `schemas.py` – data models

Define Pydantic models to keep the API contract explicit.

### 4.1 `ErrorItem`

```python
from pydantic import BaseModel
from typing import Optional


class ErrorItem(BaseModel):
    code: str
    message: Optional[str] = None
```

### 4.2 `ProcessResponse`

```python
class ProcessResponse(BaseModel):
    run_id: str
    verdict: bool
    errors: list[ErrorItem] | list[str]
```

- At minimum, we can start with `list[str]` for errors and later switch to structured objects if needed.

(If you prefer to keep it very simple for now, start with `errors: list[str]` only.)

---

## 5. `pipeline_runner.py` – minimal synchronous pipeline

### 5.1 Responsibilities

- Generate a `run_id`.
- Determine run directories under `RUNS_DIR`.
- Use the storage layer to:
  - Save the input file into the run folder.
  - Write metadata JSON.
  - Write final result JSON.
- Return a dict (or small class) with `run_id`, `verdict`, and `errors`.

### 5.2 Implementation outline

High-level sketch (not exact code):

```python
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.storage.local_disk import LocalStorage


async def run_sync_pipeline(
    *,
    fio: str | None,
    source_file_path: str,
) -> dict[str, Any]:
    settings = get_settings()
    logger = get_logger(__name__)

    # Generate a proper RFC 4122 UUID (version 4) for external contracts
    run_id = str(uuid.uuid4())

    storage = LocalStorage(settings.RUNS_DIR)

    # 1) Save input file
    saved_input_path = storage.save_input_file(source_file_path, run_id)

    # 2) Write metadata.json (optional but aligned with future phases)
    storage.write_json(run_id, "meta/metadata.json", {
        "fio": fio,
        "original_path": saved_input_path,
    })

    # 3) Minimal logic for verdict/errors (Phase 1 stub)
    verdict = True
    errors: list[str] = []

    # 4) Write final_result.json for internal use
    storage.write_json(run_id, "meta/final_result.json", {
        "run_id": run_id,
        "verdict": verdict,
        "errors": errors,
    })

    logger.info("pipeline_completed", extra={"run_id": run_id, "verdict": verdict})

    return {"run_id": run_id, "verdict": verdict, "errors": errors}
```

Notes:
- For Phase 1, verdict can be hardcoded or based on a very simple rule (for example, always `True` unless the file is missing). Later we will plug in OCR/LLM stages.
- The important part is **structure**: run_id generation, directory layout, metadata, final_result.

---

## 6. Storage layer – `base.py` and `local_disk.py`

### 6.1 `storage/base.py`

Define a very small abstraction. Example (conceptual):

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Storage(ABC):
    @abstractmethod
    def save_input_file(self, source_path: str, run_id: str) -> str: ...

    @abstractmethod
    def write_json(self, run_id: str, relative_path: str, obj: dict[str, Any]) -> str: ...
```

### 6.2 `storage/local_disk.py`

Implement `Storage` using local filesystem.

Key behaviors:
- Root: `settings.RUNS_DIR`.
- Directory layout:
  - `RUNS_DIR / YYYY-MM-DD / <run_id> / input/`
  - `RUNS_DIR / YYYY-MM-DD / <run_id> / meta/`
    - `<run_id>` is the UUID returned to calling systems.
- `save_input_file`:
  - Create dirs if needed.
  - Copy or move the source file to `input/`.
  - Return the final path as string.
- `write_json`:
  - Create parent directories.
  - Dump JSON using UTF-8 and indentation.

This keeps the file layout **encapsulated** inside the storage layer, so later we can replace it with S3/MinIO without changing the API layer.

---

## 7. Wiring everything together

### 7.1 Include /v1/process router

In `app/main.py`:
- Import `router` from `app.api.v1.routes_process`.
- Add:

```python
from app.api.v1.routes_process import router as process_router

app.include_router(process_router)
```

Health routes remain as-is.

### 7.2 Ensure logging and request IDs still work

No extra work is needed here: the existing `RequestIdMiddleware` and logging setup in Phase 0 already cover new endpoints.

---

## 8. How to test Phase 1

### 8.1 Manual testing with uvicorn

1. Start the service (as in Phase 0):
   - `uvicorn app.main:app --reload`

2. Send a request to `/v1/process` using curl or a tool like Postman:

```bash
curl -X POST "http://localhost:8000/v1/process" \
  -F "file=@/path/to/sample.pdf" \
  -F "fio=Иванов Иван Иванович"
```

3. Expected response shape:

```json
{
  "run_id": "2025...",
  "verdict": true,
  "errors": []
}
```

4. Check filesystem under `RUNS_DIR`:
   - Confirm that a new run directory was created.
   - Confirm that input file, `metadata.json`, and `final_result.json` exist.

### 8.2 Basic automated tests (optional for Phase 1)

- Add tests to `tests/test_smoke.py`:
  - Test `/health` and `/ready` still work.
  - Use FastAPI's `TestClient` to send a request to `/v1/process` with a small dummy file and assert:
    - HTTP 200 response.
    - Response contains `run_id`, `verdict`, and `errors`.

---

## 9. Acceptance criteria for Phase 1

- Service exposes `POST /v1/process` that:
  - Accepts one document file and required metadata (`fio`).
  - Returns `run_id`, `verdict`, and `errors`.
- Each call creates a new `run_id` and corresponding directory under `RUNS_DIR`.
- Basic artifacts (`metadata.json`, `final_result.json`) are written to disk for internal use.
- Logging shows request IDs and `pipeline_completed` entries with `run_id` and `verdict`.
- Phase 0 health endpoints continue to function correctly.
