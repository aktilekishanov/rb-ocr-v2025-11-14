# Refactor Phase 3 – Rebuild Domain Pipeline Stages (Pure Domain)

Goal of Phase 3: rebuild the **loan deferment pipeline logic** as pure domain code under `app/domain/pipeline`, using the ports and DTOs from Phases 1–2, and test it in isolation with fake adapters.

Important: Phase 3 still **must not change live runtime behavior**.
- FastAPI routes continue to use the old pipeline in `app/services/pipeline_runner.py`.
- New domain pipeline is exercised only via tests.

---

## 0. Constraints & success criteria

- No imports from `apps/main-dev`.
- No changes to:
  - `app/main.py`
  - `app/api/v1/*`
  - `app/services/*`
- Domain pipeline uses only:
  - `StoragePort`, `OCRPort`, `LLMPort`
  - DTOs in `domain/pipeline/models.py`
  - domain constants & errors.
- New tests under `tests/` exercise the domain pipeline via fake adapters.
- All tests pass with `PYTHONPATH=. pytest`.

---

## 1. High-level pipeline design (pure domain)

We will implement a **stage-based pipeline** as pure functions, orchestrated by `run_pipeline`:

Stages (conceptual):
1. `acquire` – ensure input doc reference is in `RunContext` (paths, run id).
2. `ocr` – call `OCRPort` and attach `OcrResult` to context.
3. `doc_type` – call `LLMPort.classify_doc_type` and set doc-type in context.
4. `extract` – call `LLMPort.extract_fields` and store extracted fields.
5. `merge` – combine OCR, doc-type, and extraction into final domain data.
6. `validate` – compute `ValidationResult` and `RunResult` (verdict/errors/checks).

This all lives under `app/domain/pipeline/` and must not touch:
- FastAPI,
- httpx,
- filesystem APIs directly (those are in infra).

---

## 2. Implement stage modules

Create new modules under `app/domain/pipeline/stages/`:

- `acquire.py`
- `ocr.py`
- `doc_type.py`
- `extract.py`
- `merge.py`
- `validate.py`

Each module exports a single primary function, e.g. `run_acquire`, `run_ocr`, etc.

### 2.1 `stages/acquire.py`

**What it does**
- Ensures `RunContext` has:
  - `run_id`
  - `input_path` (Path) already set by the outer layer (Phase 4+), or at least present in `meta`.
- For Phase 3, keep it minimal:
  - Validate that `run_id` is non-empty.
  - Return the context unchanged (or slightly massaged).

**Implementation outline**

```python
from app.domain.pipeline.models import RunContext
from app.domain.pipeline.errors import InvalidInputError


def run_acquire(context: RunContext) -> RunContext:
    if not context.run_id:
        raise InvalidInputError("run_id is required in RunContext")
    # Further checks (e.g., input_path not None) can be added later.
    return context
```

### 2.2 `stages/ocr.py`

**What it does**
- Calls `OCRPort` to get `OcrResult` and stores it in context (e.g., `context.artifacts["ocr_result"]`).

**Implementation outline**

```python
from app.domain.pipeline.models import RunContext, OcrResult
from app.domain.ports.ocr_port import OCRPort
from app.domain.pipeline.errors import OcrError


def run_ocr(context: RunContext, ocr_client: OCRPort, timeout: float, poll_interval: float) -> RunContext:
    try:
        # In Phase 3, assume StoragePort has already persisted the input; context.input_path is available.
        if context.input_path is None:
            raise OcrError("input_path is not set in RunContext for OCR stage")
        job_id = ocr_client.upload(context.input_path)
        ocr_result: OcrResult = ocr_client.wait_result(job_id, timeout=timeout, poll_interval=poll_interval)
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc

    context.artifacts["ocr_result"] = ocr_result
    return context
```

- Note: actual timeout values can be passed in by orchestrator; Phase 3 can hardcode reasonable defaults in tests.

### 2.3 `stages/doc_type.py`

**What it does**
- Uses `LLMPort.classify_doc_type` on `OcrResult` to determine doc type.

**Implementation outline**

```python
from app.domain.pipeline.models import RunContext, OcrResult, DocTypeResult
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.errors import LlmError, StageError


def run_doc_type(context: RunContext, llm_client: LLMPort) -> RunContext:
    ocr_result = context.artifacts.get("ocr_result")
    if not isinstance(ocr_result, OcrResult):
        raise StageError("OCR result missing from context for doc_type stage")
    try:
        dt: DocTypeResult = llm_client.classify_doc_type(ocr_result)
    except Exception as exc:
        raise LlmError(f"Doc-type classification failed: {exc}") from exc

    context.artifacts["doc_type_result"] = dt
    context.meta.setdefault("doc_type", dt.doc_type)
    return context
```

### 2.4 `stages/extract.py`

**What it does**
- Uses `LLMPort.extract_fields` on `OcrResult` to obtain structured fields.

**Implementation outline**

```python
from app.domain.pipeline.models import RunContext, OcrResult, ExtractionResult
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.errors import LlmError, StageError


def run_extract(context: RunContext, llm_client: LLMPort) -> RunContext:
    ocr_result = context.artifacts.get("ocr_result")
    if not isinstance(ocr_result, OcrResult):
        raise StageError("OCR result missing from context for extract stage")
    try:
        ex: ExtractionResult = llm_client.extract_fields(ocr_result)
    except Exception as exc:
        raise LlmError(f"Field extraction failed: {exc}") from exc

    context.artifacts["extraction_result"] = ex
    return context
```

### 2.5 `stages/merge.py`

**What it does**
- Combines OCR, doc-type, and extraction results into a single structure used for validation and final result.

**Implementation outline**

```python
from app.domain.pipeline.models import RunContext, OcrResult, DocTypeResult, ExtractionResult
from app.domain.pipeline.errors import StageError


def run_merge(context: RunContext) -> RunContext:
    ocr = context.artifacts.get("ocr_result")
    dt = context.artifacts.get("doc_type_result")
    ex = context.artifacts.get("extraction_result")
    if not isinstance(ocr, OcrResult) or not isinstance(dt, DocTypeResult) or not isinstance(ex, ExtractionResult):
        raise StageError("Missing required artifacts for merge stage")

    merged = {
        "doc_type": dt.doc_type,
        "doc_type_confidence": dt.confidence,
        "fields": ex.fields,
        # Additional info can be attached later (page texts, raw, etc.).
    }
    context.artifacts["merged"] = merged
    return context
```

### 2.6 `stages/validate.py`

**What it does**
- Applies simple business rules to decide the verdict and produce `ValidationResult` and `RunResult`.
- Goal in Phase 3: a **minimal but structured** validator, not a full reproduction of main-dev rules yet.

**Implementation outline**

```python
from app.domain.pipeline.models import RunContext, ValidationResult, RunResult
from app.domain.pipeline.errors import StageError


def run_validate(context: RunContext) -> tuple[RunContext, RunResult]:
    merged = context.artifacts.get("merged")
    if not isinstance(merged, dict):
        raise StageError("Merged artifacts missing for validate stage")

    errors: list[str] = []
    warnings: list[str] = []

    fields = merged.get("fields") or {}

    # Example simple rule: require fio field
    if "fio" not in fields:
        errors.append("Missing required field: fio")

    is_valid = len(errors) == 0
    val = ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)

    run_result = RunResult(
        run_id=context.run_id,
        verdict=is_valid,
        errors=errors.copy(),
        checks={"has_fio": "fio" in fields},
        meta={"doc_type": merged.get("doc_type")},
    )

    context.artifacts["validation_result"] = val
    context.artifacts["run_result"] = run_result
    return context, run_result
```

- Later phases can enrich rules to match main-dev exactly; Phase 3 focuses on structure and testability.

---

## 3. Wire stages in `run_pipeline` (domain orchestrator)

File: `app/domain/pipeline/orchestrator.py`

### 3.1 Orchestrator responsibilities

- Take `run_id`, ports (`StoragePort`, `OCRPort`, `LLMPort`), and an initial `RunContext`.
- Execute stages in order, handling domain errors.
- Return `RunResult`.
- Still **not** performing IO directly (storage, HTTP done via ports).

### 3.2 Implementation steps

1. Import required pieces:

   ```python
   from app.domain.ports.storage_port import StoragePort
   from app.domain.ports.ocr_port import OCRPort
   from app.domain.ports.llm_port import LLMPort
   from app.domain.pipeline.models import RunContext, RunResult
   from app.domain.pipeline.errors import PipelineError
   from app.domain.pipeline.stages.acquire import run_acquire
   from app.domain.pipeline.stages.ocr import run_ocr
   from app.domain.pipeline.stages.doc_type import run_doc_type
   from app.domain.pipeline.stages.extract import run_extract
   from app.domain.pipeline.stages.merge import run_merge
   from app.domain.pipeline.stages.validate import run_validate
   ```

2. Implement `run_pipeline` body:

   ```python
   async def run_pipeline(
       *,
       run_id: str,
       storage: StoragePort,
       ocr_client: OCRPort,
       llm_client: LLMPort,
       context: RunContext,
   ) -> RunResult:
       # In Phase 3, we assume the caller prepared input_path and wrote metadata as needed.
       ctx = context
       ctx = run_acquire(ctx)
       ctx = run_ocr(ctx, ocr_client=ocr_client, timeout=60.0, poll_interval=1.0)
       ctx = run_doc_type(ctx, llm_client=llm_client)
       ctx = run_extract(ctx, llm_client=llm_client)
       ctx = run_merge(ctx)
       ctx, result = run_validate(ctx)
       return result
   ```

- Keep error handling simple for Phase 3. We will add richer handling (e.g., mapping `PipelineError` to result fields) in later refactor phases if needed.
- Do not call any `storage` methods here yet; storage use will come when we integrate with the application layer.

3. Keep `run_pipeline` **unused by runtime**

- Do not import this from any live route or `app/services` code yet.
- Domain orchestrator is only used by new tests in Phase 3.

---

## 4. Domain pipeline tests (pure domain)

Add tests that exercise the complete domain pipeline using **fake ports**.

### 4.1 Test file: `tests/test_domain_pipeline.py`

**What it is**
- A test module that:
  - defines fake implementations of `StoragePort`, `OCRPort`, `LLMPort`,
  - constructs a `RunContext`,
  - calls `run_pipeline` and asserts on `RunResult` and context artifacts.

**Why needed**
- Validates that stages are wired correctly.
- Ensures error classes and DTOs integrate nicely.

**Test outline**

1. Fakes:

   ```python
   from pathlib import Path

   from app.domain.ports.storage_port import StoragePort
   from app.domain.ports.ocr_port import OCRPort
   from app.domain.ports.llm_port import LLMPort
   from app.domain.pipeline.models import (
       RunContext,
       RunResult,
       OcrResult,
       OcrPage,
       DocTypeResult,
       ExtractionResult,
   )
   from app.domain.pipeline.orchestrator import run_pipeline


   class FakeStorage(StoragePort):
       def __init__(self) -> None:
           self.written: dict[tuple[str, str], dict] = {}

       def save_input(self, run_id: str, src_path: Path) -> Path:
           return src_path

       def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path:
           self.written[(run_id, rel_path)] = obj
           return Path("/dev/null")

       def read_json(self, run_id: str, rel_path: str) -> dict:
           return self.written.get((run_id, rel_path), {})

       def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None:
           return None


   class FakeOCR(OCRPort):
       def upload(self, pdf_path: Path) -> str:
           return "job-123"

       def wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult:
           return OcrResult(pages=[OcrPage(page_number=1, text="hello world")])


   class FakeLLM(LLMPort):
       def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult:
           return DocTypeResult(doc_type="loan_deferment", confidence=0.9)

       def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult:
           return ExtractionResult(fields={"fio": "John Doe"})
   ```

2. Test happy path:

   ```python
   import pytest


   @pytest.mark.asyncio
   async def test_run_pipeline_happy_path(tmp_path: Path) -> None:
       storage = FakeStorage()
       ocr_client = FakeOCR()
       llm_client = FakeLLM()

       ctx = RunContext(run_id="run-1", input_path=tmp_path / "doc.pdf")
       result: RunResult = await run_pipeline(
           run_id="run-1",
           storage=storage,
           ocr_client=ocr_client,
           llm_client=llm_client,
           context=ctx,
       )

       assert result.run_id == "run-1"
       assert result.verdict is True
       assert result.errors == []
       assert result.checks is not None and result.checks.get("has_fio") is True
   ```

3. Test error propagation (optional for Phase 3):
- Simulate OCR/LLM failures by having fakes raise exceptions and assert that `PipelineError`/subclasses bubble up.

---

## 5. No wiring changes checklist

While implementing Phase 3, explicitly **avoid**:

- Importing `run_pipeline` or stage modules in:
  - `app/services/pipeline_runner.py`
  - `app/services/jobs.py`
  - any `app/api/v1/*` routes.
- Writing to disk from stages or orchestrator (that’s infrastructure’s job).
- Changing behavior of existing `LocalStorage`, `pipeline_runner`, or job service.

Domain pipeline remains **test-only** in Phase 3.

---

## 6. Acceptance criteria for Phase 3

- [ ] `app/domain/pipeline/stages/acquire.py` implemented and tested via pipeline tests.
- [ ] `app/domain/pipeline/stages/ocr.py` implemented using `OCRPort`.
- [ ] `app/domain/pipeline/stages/doc_type.py` implemented using `LLMPort.classify_doc_type`.
- [ ] `app/domain/pipeline/stages/extract.py` implemented using `LLMPort.extract_fields`.
- [ ] `app/domain/pipeline/stages/merge.py` combines OCR/doc-type/extraction into a merged dict.
- [ ] `app/domain/pipeline/stages/validate.py` produces `ValidationResult` and `RunResult`.
- [ ] `app/domain/pipeline/orchestrator.run_pipeline` wires stages in a clear order and returns `RunResult`.
- [ ] `tests/test_domain_pipeline.py` (or equivalent) exercises the pipeline with fake ports and passes.
- [ ] No imports from `apps/main-dev`.
- [ ] No changes to routes, services, or live storage/pipeline behavior.
- [ ] `PYTHONPATH=. pytest` fully passes.

When all boxes are checked, you will have a **fully functional, testable domain pipeline** that can later be wired into the application layer (Phase 4) with minimal risk.
