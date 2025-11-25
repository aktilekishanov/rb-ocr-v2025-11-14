# Refactor Phase 1 – Domain Contracts & Models (No Behavior Change)

Goal of Phase 1: turn the Phase 0 skeleton into **real domain contracts and models** for the pipeline and ports, while still **not changing runtime behavior** of the service.

You should be able to:
- Run all tests exactly as before (with `PYTHONPATH=.`).
- Have `domain/pipeline` and `domain/ports` contain realistic, typed models and error types.
- Keep all new code unused by live endpoints/jobs (or only used in tests), so behavior is stable.

Security/auth/retention remain out of scope.

---

## 0. Constraints & success criteria

- **No imports from `apps/main-dev`** – Phase 1 is still independent redesign.
- **No behavior change** in:
  - `app/main.py`
  - `app/api/v1/*`
  - `app/services/*`
  - `app/services/storage/*`
- All changes must be **internal to the domain layer** + pure type/contract improvements in stubs.
- Tests must still pass with:
  - `PYTHONPATH=. pytest`

---

## 1. Refine domain models (`app/domain/pipeline/models.py`)

### 1.1 Run-level models

- Expand `RunResult` to be the canonical final result shape the pipeline will produce.
  - Fields (initial set):
    - `run_id: str`
    - `verdict: bool`
    - `errors: list[str]`
    - `checks: dict[str, bool] | None = None` (placeholder for validation checks)
    - `meta: dict[str, Any] | None = None` (optional extra info)
  - Keep this aligned with the service’s current `final_result.json` structure as much as possible.
- Refine `RunContext`:
  - Add fields needed by most stages, e.g.:
    - `run_id: str`
    - `input_path: Path | None = None`
    - `work_dir: Path | None = None`
    - `artifacts: dict[str, Any] = {}`
  - Remember: still **unused** by runtime; used later by stages.

### 1.2 OCR / LLM DTOs (minimal set)

- Add Pydantic models that represent structured OCR and LLM results at a high level.

Examples (Phase 1 minimal version – you can keep fields coarse):

- `class OcrPage(BaseModel)`
  - `page_number: int`
  - `text: str`
- `class OcrResult(BaseModel)`
  - `pages: list[OcrPage]`
  - `raw: dict[str, Any] | None = None`
- `class DocTypeResult(BaseModel)`
  - `doc_type: str`
  - `confidence: float | None = None`
  - `raw: dict[str, Any] | None = None`
- `class ExtractionResult(BaseModel)`
  - `fields: dict[str, Any]`
  - `raw: dict[str, Any] | None = None`

Keep them **generic**; exact schemas will be tightened later as we port from main-dev.

### 1.3 Validation/decision models

- Add a small model for validation outcomes:
  - `class ValidationResult(BaseModel)`
    - `is_valid: bool`
    - `errors: list[str]`
    - `warnings: list[str] = []`

---

## 2. Strengthen ports (`app/domain/ports/*.py`)

### 2.1 StoragePort

- Update `StoragePort` signatures to use richer types where reasonable:
  - Use `Path` consistently for filesystem locations.
  - Clarify `rel_path` is POSIX-style path inside run directory.
- Add docstrings per method explaining intent.
- Optionally, add a return type alias, e.g. `JsonDict = dict[str, Any]` for readability.
- Do **not** import `LocalStorage` or any infrastructure; keep `StoragePort` pure.

### 2.2 OCRPort

- Change return types to use the new DTOs where appropriate:
  - `upload(self, pdf_path: Path) -> str` (job id)
  - `wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult`
- Import `OcrResult` from `domain/pipeline/models.py` (domain depending on domain is fine).
- Clarify in docstrings that:
  - errors should be represented via domain errors (see Section 3) or returned as part of DTOs in later phases.

### 2.3 LLMPort

- Use DTOs from `models.py`:
  - `classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult`
  - `extract_fields(self, pages_obj: OcrResult) -> ExtractionResult`
- Import those models from `domain/pipeline/models.py`.

Remember: ports are **interfaces only**. No logic or runtime usage change in Phase 1.

---

## 3. Domain error taxonomy (`app/domain/pipeline/errors.py`)

### 3.1 Expand error types

- Extend the basic set to match realistic categories:
  - `class PipelineError(Exception)` – base class.
  - `class InvalidInputError(PipelineError)` – file not supported, malformed.
  - `class OcrError(PipelineError)` – OCR job failed or timed out.
  - `class LlmError(PipelineError)` – LLM request failed or returned invalid data.
  - `class StageError(PipelineError)` – generic stage failure (doc-type, extraction, merge, validate).

### 3.2 Keep unused in runtime

- These exceptions should **not** yet be raised in live code.
- They will be used in Phase 3+ when building stages and wiring orchestrator.

---

## 4. Orchestrator signature (`app/domain/pipeline/orchestrator.py`)

### 4.1 Stabilize function signature

- Keep `run_pipeline` as the main entrypoint but make its intent clearer:

  - Suggested signature (still raising `NotImplementedError` in Phase 1):

    ```python
    async def run_pipeline(
        *,
        run_id: str,
        storage: StoragePort,
        ocr_client: OCRPort,
        llm_client: LLMPort,
        context: RunContext,
    ) -> RunResult:
        ...
    ```

- Import `StoragePort`, `OCRPort`, `LLMPort`, `RunContext`, and `RunResult` from domain modules.

### 4.2 Keep implementation stubbed

- Body must still raise:

  ```python
  raise NotImplementedError("Domain run_pipeline is not implemented yet (Phase 1)")
  ```

- Do **not** call this from routes or jobs yet.

---

## 5. Domain constants (`app/domain/pipeline/constants.py`)

### 5.1 Introduce named constants

- Define symbolic names for core artifacts and limits (no behavior wiring yet):

  - Example:

    ```python
    OCR_PAGES_JSON = "ocr/pages.json"
    FINAL_RESULT_JSON = "meta/final_result.json"
    JOB_STATUS_JSON = "meta/job.json"

    DEFAULT_MAX_PDF_PAGES = 200
    ```

- These are **not** yet referenced from existing storage code; they will be used by stages/orchestrator later.

### 5.2 Keep aligned with current layout

- Ensure paths reflect the existing `runs/YYYY-MM-DD/<run_id>/...` structure used by `LocalStorage`.

---

## 6. Tests for contracts (optional but recommended)

Even though there is no runtime behavior, add small tests to ensure contracts are consistent and importable.

### 6.1 Import smoke tests

- Create `tests/test_domain_contracts.py` with checks like:
  - Import `RunResult`, `RunContext`, `OcrResult`, `DocTypeResult`, `ExtractionResult`, `ValidationResult`.
  - Instantiate each with minimal valid data.
  - Import ports and annotate fake implementations that satisfy protocols.

Example snippet:

```python
from pathlib import Path

from app.domain.pipeline.models import RunResult, OcrResult, OcrPage
from app.domain.ports.storage_port import StoragePort


class FakeStorage(StoragePort):
    def save_input(self, run_id: str, src_path: str) -> Path:  # pragma: no cover
        return Path("/tmp")

    def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path:  # pragma: no cover
        return Path("/tmp")

    def read_json(self, run_id: str, rel_path: str) -> dict:  # pragma: no cover
        return {}

    def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None:  # pragma: no cover
        return None


def test_run_result_instantiation() -> None:
    RunResult(run_id="test", verdict=True, errors=[])
```

### 6.2 Ensure tests do not touch runtime

- Do **not** import `app.main` or call endpoints from this test.
- This test exists purely to ensure contracts and imports are stable.

---

## 7. No wiring changes in Phase 1

Explicitly **avoid** the following in Phase 1:

- Updating `app/services/pipeline_runner.py` to use `domain.run_pipeline`.
- Updating `app/services/jobs.py` to use domain models or ports.
- Updating FastAPI routes to import from the `application` layer.
- Changing file names or directory structure in `runs/`.

All of these are **Phase 2+** tasks.

---

## 8. Checklist before declaring Phase 1 done

- [ ] `app/domain/pipeline/models.py` contains well-typed models: `RunResult`, `RunContext`, `OcrPage`, `OcrResult`, `DocTypeResult`, `ExtractionResult`, `ValidationResult`.
- [ ] `app/domain/ports/storage_port.py` uses consistent types and has clear docstrings.
- [ ] `app/domain/ports/ocr_port.py` returns `OcrResult` (or appropriate DTOs).
- [ ] `app/domain/ports/llm_port.py` returns `DocTypeResult` and `ExtractionResult`.
- [ ] `app/domain/pipeline/errors.py` has a small taxonomy of domain errors.
- [ ] `app/domain/pipeline/orchestrator.py` has a stable signature referencing ports and models, but still raises `NotImplementedError`.
- [ ] `app/domain/pipeline/constants.py` defines canonical artifact filenames and limits, unused by runtime.
- [ ] Optional: `tests/test_domain_contracts.py` passes.
- [ ] `PYTHONPATH=. pytest` passes with no changes in public behavior.

Once all boxes are checked, you are ready for **Refactor Phase 2 – Implement infrastructure adapters** (local disk + OCR/LLM httpx clients) while still respecting the no‑behavior‑change principle until we explicitly start migrating execution paths.
