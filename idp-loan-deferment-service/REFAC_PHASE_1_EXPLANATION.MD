# Refactor Phase 1 – Explanation

Goal of Phase 1: turn the Phase 0 skeleton into **real domain contracts and models**, without wiring them into runtime yet and without changing behavior.

This document explains **every component touched in Phase 1**:
- What it is
- Why it is needed
- How it works (and how it is intentionally not yet used by live endpoints)

Security/auth/retention remain out of scope.

---

## 1. Domain models (`app/domain/pipeline/models.py`)

File: `app/domain/pipeline/models.py`

Phase 1 changed this file from small stubs into a set of concrete DTOs and core models.

### 1.1 `OcrPage`

**What it is**
- A Pydantic model representing a **single OCR page** of text.

**Why needed**
- The OCR service returns text per page.
- Downstream logic (LLM, validators) often needs page‑level context (page numbers, text length, etc.).
- Having a typed `OcrPage` standardizes how we represent that.

**How it works**
- Fields:
  - `page_number: int` – 1‑based page index.
  - `text: str` – text extracted from that page.
- It’s used inside `OcrResult.pages`.
- Not yet used by runtime logic; only by Phase 1 DTOs and tests.

### 1.2 `OcrResult`

**What it is**
- A Pydantic model representing the **full OCR result** for a document.

**Why needed**
- Stages and LLM calls need a structured view of OCR output.
- Instead of passing raw dicts around, we encapsulate them in a typed model.

**How it works**
- Fields:
  - `pages: list[OcrPage]` – ordered list of page objects.
  - `raw: dict[str, Any] | None = None` – optional raw OCR payload for debugging/advanced use.
- The `OCRPort.wait_result` method returns an `OcrResult`.
- Still not connected to the real OCR client; that comes in later phases.

### 1.3 `DocTypeResult`

**What it is**
- A Pydantic model describing the **document type classification**.

**Why needed**
- Main‑dev’s pipeline includes a doc‑type agent; we mirror that with a clear DTO.
- This makes it easier to check and log doc type and to enforce business rules per type.

**How it works**
- Fields:
  - `doc_type: str` – e.g. `"loan_deferment"`, `"unknown"`.
  - `confidence: float | None = None` – optional confidence score.
  - `raw: dict[str, Any] | None = None` – raw LLM response if needed.
- `LLMPort.classify_doc_type` returns `DocTypeResult`.

### 1.4 `ExtractionResult`

**What it is**
- DTO for **field extraction** from the LLM or rules.

**Why needed**
- The pipeline needs structured data like FIO, amounts, dates, etc.
- This model gives a typed, extensible container for those fields.

**How it works**
- Fields:
  - `fields: dict[str, Any]` – mapping from field name to value.
  - `raw: dict[str, Any] | None = None` – raw LLM payload if we need to debug.
- `LLMPort.extract_fields` returns `ExtractionResult`.

### 1.5 `ValidationResult`

**What it is**
- DTO for **final validation outcome**.

**Why needed**
- Pipeline decisions are based not just on doc type and extracted fields, but also validation.
- We need to capture validation failures and warnings in a structured way.

**How it works**
- Fields:
  - `is_valid: bool`
  - `errors: list[str]`
  - `warnings: list[str] = []`
- Later, stages will produce/consume this; Phase 1 only defines the shape.

### 1.6 `RunResult`

**What it is**
- The **canonical final result** returned by the domain pipeline.

**Why needed**
- We need a stable, typed representation of what the pipeline concludes for a `run_id`.
- It will be the bridge between domain and API response models.

**How it works**
- Fields:
  - `run_id: str` – unique pipeline run id.
  - `verdict: bool` – high‑level decision (e.g. accepted vs rejected).
  - `errors: list[str] = []` – list of human‑readable error messages.
  - `checks: dict[str, bool] | None = None` – optional per‑check booleans.
  - `meta: dict[str, Any] | None = None` – generic extra info.
- It is currently used only by the orchestrator stub signature and tests; the live API still uses the older structure.

### 1.7 `RunContext`

**What it is**
- Context object that flows between stages of a pipeline run.

**Why needed**
- Stages share information such as:
  - where the input is stored,
  - working directories,
  - intermediate artifacts.
- A structured `RunContext` keeps this organized instead of passing loose dicts.

**How it works**
- Fields:
  - `run_id: str`
  - `input_path: Path | None = None` – path to the saved input document.
  - `work_dir: Path | None = None` – base working directory for the run.
  - `artifacts: dict[str, Any] = {}` – stage‑specific outputs or metadata.
  - `meta: dict[str, Any] = {}` – misc contextual info.
- Not yet used in runtime; reserved for future stage implementations.

---

## 2. Domain ports (`app/domain/ports/*.py`)

### 2.1 `StoragePort` (`storage_port.py`)

**What it is**
- A `Protocol` defining how the domain interacts with storage.

**Phase 1 changes**
- Tightened the signature of `save_input` to use `Path` instead of `str` for `src_path`.

**Why needed**
- Using `Path` throughout avoids ambiguity about file locations and matches the rest of the codebase.
- `StoragePort` stays purely about *what* is needed, not *how* it’s implemented.

**How it works**
- Methods:
  - `save_input(self, run_id: str, src_path: Path) -> Path`
  - `write_json(self, run_id: str, rel_path: str, obj: dict) -> Path`
  - `read_json(self, run_id: str, rel_path: str) -> dict`
  - `ensure_dirs(self, run_id: str, *rel_dirs: str) -> None`
- No implementation; it’s just a contract.
- Existing runtime still uses `app/services/storage/local_disk.py`, not this interface yet.

### 2.2 `OCRPort` (`ocr_port.py`)

**What it is**
- Interface describing how the domain talks to the OCR service.

**Phase 1 changes**
- Added a typed return model `OcrResult`.
- Clarified job id as a `str`.

**Why needed**
- Domain code should think in terms of structured results, not raw dicts.
- Typed outputs (`OcrResult`) reduce duplication and errors when consuming OCR data.

**How it works**
- Imports `OcrResult` from `domain.pipeline.models`.
- Methods:
  - `upload(self, pdf_path: Path) -> str` – returns an OCR job id.
  - `wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult` – returns parsed OCR data.
- Still just a `Protocol`; real implementation sits in `OcrHttpClient` (stubbed) later.

### 2.3 `LLMPort` (`llm_port.py`)

**What it is**
- Interface for LLM operations: doc‑type classification and field extraction.

**Phase 1 changes**
- Uses typed DTOs and takes `OcrResult` as input.

**Why needed**
- LLM consumers should work with strongly typed OCR results.
- Structured return types (`DocTypeResult`, `ExtractionResult`) make downstream validation and logging straightforward.

**How it works**
- Imports `OcrResult`, `DocTypeResult`, `ExtractionResult` from domain models.
- Methods:
  - `classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult`
  - `extract_fields(self, pages_obj: OcrResult) -> ExtractionResult`
- Still no implementations; used by stubs and tests only.

---

## 3. Domain errors (`app/domain/pipeline/errors.py`)

File: `app/domain/pipeline/errors.py`

**What it is**
- A small **error taxonomy** for the domain pipeline.

**Phase 1 changes**
- Replaced generic names with more precise error types:
  - `PipelineError` – base class.
  - `InvalidInputError` – unsupported/malformed input.
  - `OcrError` – OCR failures and timeouts.
  - `LlmError` – LLM failures or invalid responses.
  - `StageError` – failures within specific stages (doc‑type, extract, merge, validate).

**Why needed**
- Domain should raise **semantic** errors rather than generic `Exception`.
- Later, the API layer can map these to consistent HTTP errors and error codes.

**How it works (Phase 1)**
- Each class is an empty subclass of `Exception` or `PipelineError`.
- Not yet raised by any live code; reserved for future stage/orchestrator logic.

---

## 4. Orchestrator signature (`app/domain/pipeline/orchestrator.py`)

File: `app/domain/pipeline/orchestrator.py`

**What it is**
- The central **domain entrypoint** for running the loan deferment pipeline.

**Phase 1 changes**
- Replaced the `*args, **kwargs` signature with a precise, typed signature.

**New signature**

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

**Why needed**
- Makes the orchestrator’s dependencies explicit:
  - it needs storage, OCR client, LLM client, and run context.
- Aligns with the hexagonal architecture: domain depends on ports, not concrete classes.

**How it works (Phase 1)**
- Imports:
  - `RunResult`, `RunContext` from `domain.pipeline.models`.
  - `StoragePort`, `OCRPort`, `LLMPort` from `domain.ports`.
- Body:

```python
raise NotImplementedError("Domain run_pipeline is not implemented yet (Phase 1)")
```

- It is **not** called by existing endpoints or jobs; runtime still uses the old `app.services.pipeline_runner`.

---

## 5. Domain constants (`app/domain/pipeline/constants.py`)

File: `app/domain/pipeline/constants.py`

**What it is**
- Centralized set of **canonical artifact paths and defaults**.

**Phase 1 changes**
- Defined realistic filenames and limits:
  - `OCR_PAGES_JSON = "ocr/pages.json"`
  - `FINAL_RESULT_JSON = "meta/final_result.json"`
  - `JOB_STATUS_JSON = "meta/job.json"`
  - `DEFAULT_MAX_PDF_PAGES: int = 200`

**Why needed**
- Avoids scattering hard‑coded relative paths throughout code.
- Keeps limits (`DEFAULT_MAX_PDF_PAGES`) aligned with config defaults.

**How it works (Phase 1)**
- Declares constants only; nothing in runtime code imports or uses them yet.
- They will be used later by stages and infrastructure adapters to write/read artifacts.

---

## 6. Infrastructure stubs aligned to ports

Although Phase 1 does not wire infrastructure into runtime, we updated stubs so they conform to the new contracts.

### 6.1 `OcrHttpClient` (`app/infrastructure/clients/ocr_http.py`)

**What it is**
- Stub adapter implementing `OCRPort` for an HTTP OCR service.

**Phase 1 changes**
- Updated file comment to “Phase 1: stub only”.
- Switched signatures to match `OCRPort` and models:
  - `upload(self, pdf_path: Path) -> str`
  - `wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult`
- Imports `OcrResult` from domain models.

**Why needed**
- Ensures the eventual real implementation will match the domain contracts.
- Keeps infrastructure code in sync with interfaces.

**How it works (Phase 1)**
- Constructor stores `base_url`, `timeout_seconds`, `verify_ssl`.
- Methods simply raise `NotImplementedError("… Phase 1")`.
- Not imported by `main.py` or any routes; no behavior impact.

### 6.2 `LlmHttpClient` (`app/infrastructure/clients/llm_http.py`)

**What it is**
- Stub adapter implementing `LLMPort` for the LLM HTTP service.

**Phase 1 changes**
- Updated comment to Phase 1.
- Imports `OcrResult`, `DocTypeResult`, `ExtractionResult` from domain models.
- Methods now match `LLMPort`:
  - `classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult`
  - `extract_fields(self, pages_obj: OcrResult) -> ExtractionResult`

**Why needed**
- Same reasoning as `OcrHttpClient`: stubs must fit the updated ports.

**How it works (Phase 1)**
- Constructor holds `base_url`, `timeout_seconds`, `verify_ssl`.
- Methods raise `NotImplementedError("… Phase 1")`.
- Not used by runtime; no HTTP calls yet.

### 6.3 `LocalDiskStorageAdapter` (`app/infrastructure/storage/local_disk_adapter.py`)

**What it is**
- Stub adapter implementing `StoragePort` using the local filesystem.

**Phase 1 changes**
- Updated comment to Phase 1.
- Changed `save_input` signature to accept `src_path: Path` instead of `str`.
- Updated all `NotImplementedError` messages to Phase 1.

**Why needed**
- Aligns with `StoragePort` so the real implementation can be dropped in later.

**How it works (Phase 1)**
- Constructor stores a `base_dir: Path`.
- All methods (`save_input`, `write_json`, `read_json`, `ensure_dirs`) raise `NotImplementedError`.
- Not wired into the running app; current runtime still uses `app/services/storage/local_disk.py`.

---

## 7. Contract tests (`tests/test_domain_contracts.py`)

File: `tests/test_domain_contracts.py`

**What it is**
- A small **smoke test** to ensure domain models and ports are importable and consistent.

**Why needed**
- Early detection of mismatches:
  - incorrect import paths,
  - signature mismatches between ports and adapters,
  - broken Pydantic models.
- Keeps Phase 1 self‑contained without touching HTTP endpoints.

**How it works**
- Imports:
  - All domain models: `RunResult`, `RunContext`, `OcrPage`, `OcrResult`, `DocTypeResult`, `ExtractionResult`, `ValidationResult`.
  - Ports: `StoragePort`, `OCRPort`, `LLMPort`.
- Defines fake implementations:
  - `FakeStorage(StoragePort)` – returns dummy paths and dicts.
  - `FakeOCR(OCRPort)` – returns a simple `OcrResult` with one page.
  - `FakeLLM(LLMPort)` – returns `DocTypeResult` and `ExtractionResult` with dummy data.
- Tests:
  - `test_models_instantiation()` – verifies models can be constructed and fields behave as expected.
  - `test_ports_protocols()` – type‑checks basic protocol usage and runtime behavior of fakes.
- Does **not** import `app.main` or call APIs; isolated to domain/infrastructure contracts.

All tests pass with:

```bash
PYTHONPATH=. pytest
# 7 passed
```

---

## 8. Behavior and boundaries

- Phase 1 did **not** change:
  - `app/main.py`
  - Any routes under `app/api/v1/`
  - `app/services/*` (including the old pipeline and storage implementations)
  - Dockerfile or runtime config behavior
- No new security/auth/retention logic was added.
- No file/directory structure changes occurred under `runs/`.

The new components are:
- **Fully typed, domain‑focused contracts** (models, ports, errors, orchestrator, constants).
- Kept strictly behind the existing runtime, ready to be used in Phase 2+ without risking regressions.

Phase 1’s main value is **clarity and safety**: you now have a well‑defined domain surface area to plug a new implementation into, while your current service continues to run unchanged.
