# Refactor Phase 3 – Explanation

Goal of Phase 3: implement the **loan deferment pipeline logic** as pure domain code (stages + orchestrator) under `app/domain/pipeline`, using the ports and DTOs from earlier phases, and verify it with tests – **without wiring it into the live FastAPI routes yet**.

This document explains every Phase 3 component:
- What it is
- Why it is needed
- How it works

Public behavior of the running service remains unchanged.

---

## 1. Domain stages (under `app/domain/pipeline/stages/`)

We created 6 small, focused stage modules. Each operates only on domain models and ports, with no HTTP or filesystem access.

### 1.1 `stages/acquire.py`

**What it is**
- The **acquire** stage, responsible for basic sanity checks on `RunContext`.

**Why needed**
- Every pipeline run must have a valid `run_id` (and eventually an `input_path`).
- Centralizing this check in a stage makes it easier to extend later (e.g. ensuring input exists, checking metadata).

**How it works**

```python
from app.domain.pipeline.models import RunContext
from app.domain.pipeline.errors import InvalidInputError


def run_acquire(context: RunContext) -> RunContext:
    if not context.run_id:
        raise InvalidInputError("run_id is required in RunContext")
    return context
```

- For now, it only ensures `run_id` is non-empty and returns the same context.

---

### 1.2 `stages/ocr.py`

**What it is**
- The **OCR** stage, which calls the OCR port and attaches an `OcrResult` to the context.

**Why needed**
- OCR is a core step: everything else depends on having page-level text.
- Keeping this logic in a stage that depends on `OCRPort` (not httpx) keeps the domain clean and testable.

**How it works**

```python
from app.domain.pipeline.models import RunContext, OcrResult
from app.domain.ports.ocr_port import OCRPort
from app.domain.pipeline.errors import OcrError


def run_ocr(context: RunContext, *, ocr_client: OCRPort, timeout: float, poll_interval: float) -> RunContext:
    if context.input_path is None:
        raise OcrError("input_path is not set in RunContext for OCR stage")
    try:
        job_id = ocr_client.upload(context.input_path)
        ocr_result: OcrResult = ocr_client.wait_result(job_id, timeout=timeout, poll_interval=poll_interval)
    except Exception as exc:
        raise OcrError(f"OCR failed: {exc}") from exc

    context.artifacts["ocr_result"] = ocr_result
    return context
```

- Ensures `input_path` is present.
- Uses `OCRPort` methods; no direct httpx or file access here.
- Stores `OcrResult` under `context.artifacts["ocr_result"]` for downstream stages.

---

### 1.3 `stages/doc_type.py`

**What it is**
- The **doc-type** stage, which classifies the document type via the LLM.

**Why needed**
- Many business rules depend on doc type (loan deferment vs some other form).
- The LLM endpoint is abstracted behind `LLMPort`; this stage orchestrates that call.

**How it works**

```python
from app.domain.pipeline.models import RunContext, OcrResult, DocTypeResult
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.errors import LlmError, StageError


def run_doc_type(context: RunContext, *, llm_client: LLMPort) -> RunContext:
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

- Reads OCR output from `context.artifacts` and passes it to `LLMPort.classify_doc_type`.
- On success, stores the `DocTypeResult` and sets `context.meta["doc_type"]`.

---

### 1.4 `stages/extract.py`

**What it is**
- The **extraction** stage, which asks the LLM to extract structured fields from OCR text.

**Why needed**
- Downstream validation and decision-making require structured fields (FIO, amounts, dates, etc.).

**How it works**

```python
from app.domain.pipeline.models import RunContext, OcrResult, ExtractionResult
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.errors import LlmError, StageError


def run_extract(context: RunContext, *, llm_client: LLMPort) -> RunContext:
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

- Similar pattern to doc-type stage: read `OcrResult`, call LLM, store `ExtractionResult`.

---

### 1.5 `stages/merge.py`

**What it is**
- The **merge** stage, which combines key artifacts (OCR, doc-type, extraction) into a single merged structure used by validation.

**Why needed**
- Validation and final result need a consolidated view of:
  - document type,
  - extracted fields,
  - possibly additional metadata later.
- A merged dict simplifies the validate logic and keeps checks centralized.

**How it works**

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
    }
    context.artifacts["merged"] = merged
    return context
```

- Validates that all required artifacts are present.
- Builds a merged dict and stores it under `context.artifacts["merged"]`.

---

### 1.6 `stages/validate.py`

**What it is**
- The **validate** stage, which applies simple rules to produce:
  - `ValidationResult`
  - `RunResult` (verdict, errors, checks, meta)

**Why needed**
- The pipeline must produce a final decision and explain why.
- This stage is the last step in the domain pipeline chain.

**How it works**

```python
from typing import Tuple

from app.domain.pipeline.models import RunContext, ValidationResult, RunResult
from app.domain.pipeline.errors import StageError


def run_validate(context: RunContext) -> Tuple[RunContext, RunResult]:
    merged = context.artifacts.get("merged")
    if not isinstance(merged, dict):
        raise StageError("Merged artifacts missing for validate stage")

    errors: list[str] = []
    warnings: list[str] = []

    fields = merged.get("fields") or {}

    # Minimal rule example: require fio field
    if "fio" not in fields:
        errors.append("Missing required field: fio")

    is_valid = len(errors) == 0

    val = ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
    run_result = RunResult(
        run_id=context.run_id,
        verdict=is_valid,
        errors=list(errors),
        checks={"has_fio": "fio" in fields},
        meta={"doc_type": merged.get("doc_type")},
    )

    context.artifacts["validation_result"] = val
    context.artifacts["run_result"] = run_result
    return context, run_result
```

- Uses a **very simple rule**: require `fio` in extracted fields.
- Creates `ValidationResult` and `RunResult`, stores them in artifacts, returns both.
- Rules can be expanded in later phases without touching orchestration.

---

## 2. Domain orchestrator (`app/domain/pipeline/orchestrator.py`)

**What it is**
- The main **orchestrator** function that wires all stages together and returns a `RunResult`.
- Lives entirely in the domain layer; uses only ports and DTOs.

**Why needed**
- Provides a single entrypoint (`run_pipeline`) that:
  - expresses the pipeline sequence,
  - allows tests to exercise the whole flow,
  - later can be called from the application layer (use‑cases) instead of old services.

**How it works**

```python
from .models import RunResult, RunContext
from app.domain.ports.storage_port import StoragePort
from app.domain.ports.ocr_port import OCRPort
from app.domain.ports.llm_port import LLMPort
from app.domain.pipeline.stages.acquire import run_acquire
from app.domain.pipeline.stages.ocr import run_ocr
from app.domain.pipeline.stages.doc_type import run_doc_type
from app.domain.pipeline.stages.extract import run_extract
from app.domain.pipeline.stages.merge import run_merge
from app.domain.pipeline.stages.validate import run_validate


async def run_pipeline(
    *,
    run_id: str,
    storage: StoragePort,
    ocr_client: OCRPort,
    llm_client: LLMPort,
    context: RunContext,
) -> RunResult:
    """Run the full loan deferment pipeline (pure domain).

    Notes:
    - Does not perform IO directly; relies on ports for OCR/LLM and expects input_path in context.
    - storage is accepted for future use (e.g., artifact persistence) but unused in Phase 3.
    - Keeps timeouts conservative; callers may adjust in later phases.
    """
    ctx = context
    ctx = run_acquire(ctx)
    ctx = run_ocr(ctx, ocr_client=ocr_client, timeout=60.0, poll_interval=0.25)
    ctx = run_doc_type(ctx, llm_client=llm_client)
    ctx = run_extract(ctx, llm_client=llm_client)
    ctx = run_merge(ctx)
    ctx, result = run_validate(ctx)
    return result
```

- Accepts `storage` but doesn’t use it yet (kept for future integration with persistence and artifacts).
- Calls stages in a clear sequence.
- Returns `RunResult` from `run_validate`.
- Is only called by tests in Phase 3, not by any live route or service.

---

## 3. Domain pipeline tests (`tests/test_domain_pipeline.py`)

**What it is**
- A test module that exercises the **entire domain pipeline** using fake implementations of ports.

**Why needed**
- Validates that all stages + orchestrator work together.
- Ensures DTOs, errors, and ports integrate cleanly.
- Keeps this verification independent of FastAPI, httpx, or real services.

**How it works**

1. **Fake ports**

```python
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

- Storage fake records written JSON in memory but is not used by `run_pipeline` yet.
- OCR fake returns a simple single-page `OcrResult`.
- LLM fake returns deterministic `DocTypeResult` and `ExtractionResult`.

2. **Happy-path test**

```python
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

- Constructs fakes and a `RunContext` with a dummy `input_path`.
- Calls `run_pipeline` and verifies:
  - Correct run id.
  - Verdict is `True` (because `fio` is present).
  - No errors.
  - `checks["has_fio"]` is `True`.

3. **Test coverage summary**
- This test implicitly exercises:
  - all stages (`acquire`, `ocr`, `doc_type`, `extract`, `merge`, `validate`),
  - orchestrator wiring,
  - DTOs and error types (in the happy path, errors are not triggered).

---

## 4. Behavior and boundaries

- **No imports from `apps/main-dev`**.
- **No changes** to:
  - `app/main.py`
  - `app/api/v1/*` routes
  - existing `app/services/*` modules
- Live pipeline still uses old `pipeline_runner` and storage; domain pipeline is **test-only**.
- Directory layout under `runs/` used by the live system remains unchanged.
- Test command:

```bash
PYTHONPATH=. pytest
# 13 tests passed
```

Phase 3 gives you a **fully functional domain pipeline** – wired, testable, and independent of web framework and IO. In later phases, we will route real traffic through this pipeline by wiring it into the application layer and endpoints, but that has not been done yet, so production behavior remains stable.
