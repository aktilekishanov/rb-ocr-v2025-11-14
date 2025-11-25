# Refactor Phase 4 – Wire Application Use-Cases to Domain Pipeline

Goal of Phase 4: connect the new **domain pipeline** and **infrastructure adapters** to the FastAPI app **through the application layer**, replacing the old `services` pipeline usage, while keeping APIs and behavior compatible.

At the end of this phase, `/v1/process` and the async jobs path will use:
- `RunContext` + domain `run_pipeline`
- `StoragePort` via `LocalDiskStorageAdapter`
- `OCRPort` via `OcrHttpClient`
- `LLMPort` via `LlmHttpClient`

We will do this in a controlled way, with tests and no breaking changes to public contracts.

Security/auth/retention remain out of scope.

---

## 0. Constraints & success criteria

- No imports from `apps/main-dev`.
- Public API behavior:
  - Request/response schemas unchanged for `/v1/process` and `/v1/jobs*`.
  - Error responses remain compatible with current standardized format.
- `runs/` directory layout remains the same.
- Domain pipeline (`run_pipeline`) and adapters are used via the **application layer**, not directly from routes.
- All tests (existing + new) pass with `PYTHONPATH=. pytest`.

---

## 1. Application use-case: sync process (`process_document`)

File: `app/application/usecases/process_document.py`

### 1.1 Design goals

- Move orchestration logic for the sync `/v1/process` endpoint into a **use-case**.
- Use domain pipeline + adapters end-to-end.
- Keep FastAPI route thin and focused on HTTP concerns.

### 1.2 Implementation outline

1. **Imports** (domain & adapters):

   ```python
   from pathlib import Path
   from typing import Any

   from app.core.config import get_settings
   from app.domain.pipeline.models import RunContext, RunResult
   from app.domain.pipeline.orchestrator import run_pipeline
   from app.application.services.factories import (
       build_storage_adapter,
       build_ocr_client,
       build_llm_client,
   )
   ```

2. **Function signature**

   The use-case should be framework-agnostic. Let it accept pre-validated inputs:

   ```python
   async def process_document(
       *,
       run_id: str,
       input_path: Path,
       extra_meta: dict[str, Any] | None = None,
   ) -> RunResult:
       ...
   ```

3. **Body**

   - Build adapters from settings:

     ```python
     settings = get_settings()
     storage = build_storage_adapter()
     ocr_client = build_ocr_client()
     llm_client = build_llm_client()
     ```

   - Construct `RunContext`:

     ```python
     ctx = RunContext(
         run_id=run_id,
         input_path=input_path,
         work_dir=settings.RUNS_DIR,
         artifacts={},
         meta=extra_meta or {},
     )
     ```

   - Call domain pipeline:

     ```python
     result = await run_pipeline(
         run_id=run_id,
         storage=storage,
         ocr_client=ocr_client,
         llm_client=llm_client,
         context=ctx,
     )
     return result
     ```

4. **No HTTP here**

- Use-case should not know about `UploadFile`, `Request`, or response models.
- It operates purely on `run_id` and a `Path` refering to the saved input file.

---

## 2. Application service: pipeline runner bridge

File: `app/application/services/pipeline_runner.py`

### 2.1 Design goals

- Provide a **bridge** for current code that expects `run_sync_pipeline` while delegating to the new use-case.
- Introduce a new application-level API (e.g., `run_sync_pipeline_app`) that can be used by routes and jobs.

### 2.2 Implementation adjustments

1. Keep existing re-export for backward-compat (until we fully switch):

   ```python
   from app.services.pipeline_runner import run_sync_pipeline as legacy_run_sync_pipeline
   __all__ = ["legacy_run_sync_pipeline", "run_sync_pipeline_app"]
   ```

2. Implement `run_sync_pipeline_app` using `process_document`:

   ```python
   from pathlib import Path
   from typing import Any

   from app.application.usecases.process_document import process_document


   async def run_sync_pipeline_app(*, run_id: str, input_path: Path, meta: dict[str, Any] | None = None) -> dict[str, Any]:
       result = await process_document(run_id=run_id, input_path=input_path, extra_meta=meta)
       # Convert RunResult (domain) to the dict shape expected by current APIs/tests.
       return {
           "run_id": result.run_id,
           "verdict": result.verdict,
           "errors": result.errors,
           # Optionally surface checks/meta as needed later.
       }
   ```

3. In Phase 4, do **not** remove the legacy function or change existing uses yet. Instead, we will progressively switch call sites.

---

## 3. Switch sync `/v1/process` to new pipeline (via application layer)

File: `app/api/v1/routes_process.py`

### 3.1 Design goals

- Route stays responsible for:
  - parsing `UploadFile` and form fields,
  - writing the temporary file to disk,
  - handling HTTP errors/status codes.
- Actual pipeline logic moves to `run_sync_pipeline_app`.

### 3.2 Implementation outline

1. **Find current logic**

- Locate the part in `/v1/process` handler where it:
  - reads uploaded file into a temp path,
  - calls the old `run_sync_pipeline` service.

2. **Replace call site**

- Instead of importing from `app.services.pipeline_runner`, import from `app.application.services.pipeline_runner`:

  ```python
  from app.application.services.pipeline_runner import run_sync_pipeline_app
  ```

- At the point where we have a `temp_path` and `fio` (and maybe other form fields):

  ```python
  from pathlib import Path
  run_id = str(uuid.uuid4())  # or reused from existing logic
  result = await run_sync_pipeline_app(run_id=run_id, input_path=Path(temp_path), meta={"fio": fio})
  ```

3. **Map `RunResult` dict to response model**

- If your FastAPI response model already expects `run_id`, `verdict`, `errors`, this should stay unchanged.
- Ensure any additional fields used in responses (e.g. `checks`) are either:
  - filled from `RunResult`, or
  - omitted to preserve current schema.

4. **Error handling**

- Wrap the call in try/except if needed, but prefer existing standardized error mapping you already have.
- Domain errors can remain unwrapped in Phase 4; we will map them more cleanly in a later refactor.

---

## 4. Prepare async jobs to use new pipeline (but keep behavior)

Files:
- `app/services/jobs.py`
- `app/api/v1/routes_jobs.py`

### 4.1 Design goals

- Async jobs should use the **same application-level pipeline function** as sync, just in a background task.
- Job persistence format (`meta/job.json`) should remain unchanged.

### 4.2 Implementation outline

1. In `app/services/jobs.py`, locate the async job worker function (currently calling old pipeline runner).

2. Replace the call to the old pipeline with `run_sync_pipeline_app`:

   ```python
   from app.application.services.pipeline_runner import run_sync_pipeline_app
   from pathlib import Path


   async def _process_job_async(run_id: str, file_temp_path: str, fio: str) -> None:
       try:
           set_running(run_id)
           result = await run_sync_pipeline_app(run_id=run_id, input_path=Path(file_temp_path), meta={"fio": fio})
           set_completed(... based on result ...)
       except Exception as e:
           set_failed(run_id, error=str(e)[:200])
       finally:
           ... # existing cleanup
   ```

3. Ensure job status logic (`set_completed`, `set_failed`, job JSON) remains consistent with current expectations.

---

## 5. Tests for Phase 4 wiring

### 5.1 New/updated tests

1. **Integration tests for `/v1/process`**
   - Ensure that after wiring to the new pipeline, responses:
     - still have `run_id`, `verdict`, `errors` as before,
     - still reject unsupported file types and invalid input exactly as now.
   - Optionally assert that domain’s minimal validation rule is respected (e.g., missing `fio` leads to error) if that matches current behavior.

2. **Integration tests for `/v1/jobs`**
   - Submit an async job, poll status until completion.
   - Assert status transitions and final job JSON remain unchanged.

3. **Unit tests for `process_document` and `run_sync_pipeline_app`**
   - Use fake adapters (similar to `test_domain_pipeline`) to verify that:
     - `process_document` calls `run_pipeline` correctly.
     - `run_sync_pipeline_app` returns the expected dict shape.

### 5.2 Regression checks

- Run the full suite:

  ```bash
  PYTHONPATH=. pytest
  ```

- Optionally run selected endpoint checks manually:
  - `uvicorn app.main:app --reload`
  - POST `/v1/process` with a small valid doc.
  - Use the `runs/` directory to confirm artifacts still appear in the expected location.

---

## 6. Migration strategy & rollback

### 6.1 Strategy

- Switch sync path first (`/v1/process`) to use the new pipeline via application layer.
- Then switch async jobs to use the same application function.
- Keep legacy `app.services.pipeline_runner.run_sync_pipeline` and related logic in place until you’ve:
  - validated the new pipeline in a non‑prod or staging environment,
  - confirmed parity on a representative sample of documents.

### 6.2 Rollback

- If issues appear, you can revert the route and job service imports back to the old pipeline:
  - change imports from `app.application.services.pipeline_runner` back to `app.services.pipeline_runner`.
- Because domain + adapters are additive and not wired into bootstrapping, rollback is low‑risk.

---

## 7. Acceptance criteria for Phase 4

- [ ] `app/application/usecases/process_document.py` implemented and uses domain `run_pipeline` and factories.
- [ ] `app/application/services/pipeline_runner.py` exposes `run_sync_pipeline_app` and still preserves legacy re-export for rollback.
- [ ] `/v1/process` route calls `run_sync_pipeline_app` instead of the old pipeline service.
- [ ] Async job worker in `app/services/jobs.py` calls `run_sync_pipeline_app`.
- [ ] All tests pass with `PYTHONPATH=. pytest`.
- [ ] Manual smoke tests for `/v1/process` and `/v1/jobs` succeed and behave as before (or within acceptable new validation rules).
- [ ] No imports from `apps/main-dev`.
- [ ] `runs/` layout and artifact filenames remain unchanged.

Once all items are complete, the FastAPI service will be **fully running on the new clean domain pipeline and adapters**, while public HTTP contracts remain stable. This completes the core refactor from main-dev into the new service architecture.
