# Refactor Phase 0 – Explanation

Goal of Phase 0: prepare a clean architecture skeleton (application, domain, infrastructure, config) **without changing any runtime behavior** of the service.

This document explains **every component added or touched in Phase 0**:
- What it is
- Why it is needed
- How it works (or, for now, how it is intentionally *not* yet wired)

Security, auth, and data‑retention are **explicitly out of scope** in Phase 0.

---

## 1. Application layer

### 1.1 `app/application/__init__.py`

**What it is**
- A Python package marker for the **application layer**.

**Why needed**
- We want a dedicated layer whose job is to orchestrate **use‑cases**:
  - glue between FastAPI (HTTP layer), domain (pure business logic), and infrastructure (adapters).
- Keeping this separate prevents controllers (routes) from filling up with business logic and HTTP details from leaking into the domain.

**How it works**
- In Phase 0 it only contains a docstring; it makes `app.application` a valid module.
- It is imported nowhere critical yet; it exists to support future Phase 1+ work.

---

### 1.2 `app/application/usecases/__init__.py`

**What it is**
- Package marker for **use‑case entrypoints**, e.g. "process document", "submit job".

**Why needed**
- Each use‑case is a single, well‑named function or class that:
  - receives data from the API layer (already validated forms/body),
  - calls into the **domain** to run the pipeline or parts of it,
  - uses **ports** and **infrastructure adapters** to talk to storage/OCR/LLM,
  - returns a structured result back to the API.
- Having a `usecases` package keeps that orchestration logic in one place instead of scattered in routes.

**How it works**
- Currently just a docstring; future phases will add real functions.

---

### 1.3 `app/application/usecases/process_document.py`

**What it is**
- A **placeholder use‑case** for the main sync operation: process one document.

**Why needed**
- Ultimately, `/v1/process` should delegate to `process_document` rather than calling low‑level services or domain directly.
- This makes it easy to:
  - test the use‑case in isolation,
  - swap implementations or orchestrator behavior without touching routes,
  - keep HTTP concerns (status codes, headers) out of the business logic.

**How it works (Phase 0)**
- Contains an async function:
  - `async def process_document(*args, **kwargs) -> Any:`
  - It only raises `NotImplementedError`.
- It is **not imported or used by any route** in Phase 0.
- Because it is unused, it cannot change current behavior; it is pure scaffolding.

---

### 1.4 `app/application/services/__init__.py`

**What it is**
- Package marker for **application‑level services** (things that are not strictly domain, but also not HTTP controllers).

**Why needed**
- Some behaviors are not exactly domain rules, but also not pure IO either (e.g. job management glue, pipeline runner wrappers).
- Grouping them under `application/services` keeps the structure clean.

**How it works**
- Currently only a docstring; used to organize service modules such as `pipeline_runner.py`.

---

### 1.5 `app/application/services/pipeline_runner.py`

**What it is**
- Application‑level view of the pipeline runner.
- In Phase 0 it is mostly a **thin re‑export** of the existing implementation.

**Why needed**
- Long term, we want the pipeline orchestration to live in the **domain** + **use‑cases**, not in a generic `services` module.
- This file will become the bridge between FastAPI endpoints and the domain pipeline.
- For Phase 0, we must not change behavior, so we:
  - keep the old implementation in `app/services/pipeline_runner.py`, and
  - make this module just re‑export it.

**How it works (Phase 0)**
- It imports from the existing implementation:
  - `from app.services.pipeline_runner import run_sync_pipeline as run_sync_pipeline`
- It defines `__all__ = ["run_sync_pipeline"]` so other code could import from here later without changing behavior.
- It provides a **stub** for a future entrypoint:
  - `async def run_sync_pipeline_app(...): raise NotImplementedError`
- Crucially:
  - No route or service has been updated to import from this new module yet.
  - Existing behavior remains: routes still use the old `app.services.pipeline_runner.run_sync_pipeline`.

---

## 2. Domain layer

### 2.1 `app/domain/__init__.py`

**What it is**
- Package marker for the **domain layer** – pure business rules and models.

**Why needed**
- We want to keep the loan deferment pipeline logic independent of:
  - FastAPI,
  - HTTP,
  - file system details,
  - specific OCR/LLM APIs.
- This makes it easier to test and reuse, and reduces coupling.

**How it works**
- Only a docstring in Phase 0; it establishes `app.domain` as a namespace.

---

### 2.2 `app/domain/ports/__init__.py`

**What it is**
- Package marker for **ports (interfaces)** the domain uses to talk to the outside world.

**Why needed**
- Ports express **what** the domain needs (e.g., "save JSON", "run OCR"), not **how** it is implemented.
- Real implementations live in the `infrastructure` layer and conform to these ports.

**How it works**
- Right now the package contains only docstrings and the port modules (`storage_port.py`, `ocr_port.py`, `llm_port.py`).

---

### 2.3 `app/domain/ports/storage_port.py`

**What it is**
- A `Protocol` called `StoragePort` that defines the storage operations the domain pipeline needs.

**Why needed**
- The pipeline needs to:
  - save the input file,
  - write/read JSON artifacts and metadata,
  - ensure directories exist.
- But we don’t want the domain to know whether this is local disk, S3, MinIO, etc.
- `StoragePort` gives us a stable contract and allows multiple implementations.

**How it works (Phase 0)**
- Defines:
  - `save_input(self, run_id: str, src_path: str) -> Path`
  - `write_json(self, run_id: str, rel_path: str, obj: dict) -> Path`
  - `read_json(self, run_id: str, rel_path: str) -> dict`
  - `ensure_dirs(self, run_id: str, *rel_dirs: str) -> None`
- It uses `typing.Protocol` for structural typing.
- There is **no implementation here**.
- Existing storage logic in `app/services/storage/local_disk.py` remains in use; no code was switched to `StoragePort` yet.

---

### 2.4 `app/domain/ports/ocr_port.py`

**What it is**
- `OCRPort` protocol, representing the OCR service capabilities.

**Why needed**
- The domain pipeline must be able to:
  - send documents to OCR,
  - poll/wait for OCR results.
- We don’t want domain code to depend on:
  - httpx directly,
  - any specific endpoint paths,
  - TLS/verify flags.

**How it works (Phase 0)**
- Defines:
  - `upload(self, pdf_path: Path) -> Any`
  - `wait_result(self, job_id: str, timeout: float, poll_interval: float) -> dict`
- Return types are still coarse (`Any`, `dict`) to keep Phase 0 simple.
- There’s no logic; implementations in the infrastructure layer will fulfill this protocol later.

---

### 2.5 `app/domain/ports/llm_port.py`

**What it is**
- `LLMPort` protocol representing LLM functionality used by the pipeline.

**Why needed**
- The pipeline uses an internal LLM endpoint to:
  - classify document type,
  - extract structured data (fields) from OCR text.
- We want to be able to change or mock the LLM backend without rewriting domain logic.

**How it works (Phase 0)**
- Defines:
  - `classify_doc_type(self, pages_obj: dict) -> Any`
  - `extract_fields(self, pages_obj: dict) -> Any`
- Again, it’s a pure interface; the real HTTP logic will be in `infrastructure/clients/llm_http.py` later.

---

### 2.6 `app/domain/pipeline/__init__.py`

**What it is**
- Package marker for the **pipeline domain**: orchestrator, models, errors, and stages.

**Why needed**
- It groups all pipeline‑specific domain files under one namespace, instead of scattering them across the project.

**How it works**
- For now, it only exposes the package; logic is in the child modules.

---

### 2.7 `app/domain/pipeline/stages/__init__.py`

**What it is**
- Placeholder package for individual pipeline stages (acquire, ocr, doc‑type, extract, merge, validate).

**Why needed**
- Each stage will become its own module later.
- This makes each step of the pipeline small, testable, and focused.

**How it works (Phase 0)**
- Only a docstring; no stage modules yet.

---

### 2.8 `app/domain/pipeline/constants.py`

**What it is**
- Placeholder for domain‑level constants (e.g. filenames, limits).

**Why needed**
- Main‑dev has a set of canonical names for artifacts (like OCR output file names) and limits.
- Centralizing them here avoids hard‑coding strings throughout the codebase.

**How it works (Phase 0)**
- Contains only a minimal placeholder (`DEFAULT_MAX_PDF_PAGES`), not used anywhere yet.
- Real values will be ported in later phases.

---

### 2.9 `app/domain/pipeline/models.py`

**What it is**
- Pydantic models representing domain data structures:
  - `RunResult`
  - `RunContext`

**Why needed**
- Domain should use clear, typed models for:
  - the overall pipeline result (run id, verdict, errors, and later more fields),
  - context that flows between stages.
- This simplifies reasoning, validation, and future refactors.

**How it works (Phase 0)**
- `RunResult` has fields: `run_id: str`, `verdict: bool`, `errors: list[str]`.
- `RunContext` has `run_id` and a generic `meta` dict.
- Both models are **stubs** and currently unused; no code has been switched to them.

---

### 2.10 `app/domain/pipeline/errors.py`

**What it is**
- Domain‑level exception types:
  - `PipelineError`
  - `InvalidDocumentError`
  - `ExternalServiceError`

**Why needed**
- Eventually, we want the domain pipeline to raise **semantic errors** instead of raw generic exceptions.
- These can later be mapped to API‑level error codes and HTTP responses in a controlled way.

**How it works (Phase 0)**
- Each class simply subclasses `Exception`.
- They are not yet used in any active path; they are reserved for future phases.

---

### 2.11 `app/domain/pipeline/orchestrator.py`

**What it is**
- The future **domain orchestrator** of the pipeline.

**Why needed**
- This will eventually hold the core sequence of operations:
  - acquire input
  - OCR
  - doc‑type check
  - extraction + stamp
  - merge
  - validate & finalize
- Keeping it in domain prevents HTTP and IO details from cluttering this logic.

**How it works (Phase 0)**
- Defines `async def run_pipeline(*args, **kwargs) -> RunResult`.
- Immediately raises `NotImplementedError` with a clear message.
- It is **not called** by any endpoint or job; runtime still uses the old `app.services.pipeline_runner` implementation.

---

## 3. Infrastructure layer

### 3.1 `app/infrastructure/__init__.py`

**What it is**
- Package marker for **infrastructure adapters**.

**Why needed**
- Adapters implement domain ports and interact with real systems:
  - local filesystem, S3/MinIO,
  - OCR HTTP service,
  - LLM HTTP service, etc.
- Separating this layer makes it clear which code has side effects.

**How it works**
- In Phase 0, only a docstring; logic is in child modules.

---

### 3.2 `app/infrastructure/storage/__init__.py`

**What it is**
- Package marker for storage adapters.

**Why needed**
- Allows multiple storage options (local disk now, S3/MinIO later) all satisfying `StoragePort`.

**How it works (Phase 0)**
- Only a docstring; `local_disk_adapter.py` is the first stub under this package.

---

### 3.3 `app/infrastructure/storage/local_disk_adapter.py`

**What it is**
- A **stub adapter** `LocalDiskStorageAdapter` implementing `StoragePort` for local disk.

**Why needed**
- This will eventually become the infrastructure implementation that replaces `app/services/storage/local_disk.py`.
- Having it behind `StoragePort` makes it easy to swap or mock.

**How it works (Phase 0)**
- Constructor stores a `base_dir: Path`.
- All methods (`save_input`, `write_json`, `read_json`, `ensure_dirs`) simply raise `NotImplementedError` with clear messages.
- Nothing in `main.py` or the routes imports or uses this adapter yet.
- Existing runtime still uses the original `LocalStorage` implementation in `app/services/storage/local_disk.py`.

---

### 3.4 `app/infrastructure/clients/__init__.py`

**What it is**
- Package marker for external clients (OCR, LLM, etc.).

**Why needed**
- Separates HTTP clients and other external connections from the domain.

**How it works**
- Only a docstring; real clients live in `ocr_http.py` and `llm_http.py`.

---

### 3.5 `app/infrastructure/clients/ocr_http.py`

**What it is**
- Stub implementation of `OCRPort` named `OcrHttpClient`.

**Why needed**
- Ultimately, this class will:
  - call the real OCR HTTP API using `httpx`,
  - handle timeouts, SSL/verify flags, etc.
- For now, we only need the **shape** of this class so the architecture is ready.

**How it works (Phase 0)**
- Constructor parameters:
  - `base_url: str | None`
  - `timeout_seconds: int`
  - `verify_ssl: bool = True`
- Saves these values to instance fields.
- Methods:
  - `upload(self, pdf_path: Path) -> Any` – raises `NotImplementedError`.
  - `wait_result(self, job_id: str, timeout: float, poll_interval: float) -> dict` – raises `NotImplementedError`.
- No code imports or uses `OcrHttpClient` yet; it is scaffolding only.

---

### 3.6 `app/infrastructure/clients/llm_http.py`

**What it is**
- Stub implementation of `LLMPort` named `LlmHttpClient`.

**Why needed**
- This will eventually encapsulate the internal LLM HTTP endpoint logic.
- Keeping this separate:
  - decouples LLM usage from domain logic,
  - makes it easy to test domain with fake LLMs.

**How it works (Phase 0)**
- Constructor parameters:
  - `base_url: str | None`
  - `timeout_seconds: int`
  - `verify_ssl: bool = True`
- Stores them as attributes.
- Methods:
  - `classify_doc_type(self, pages_obj: dict) -> Any` – raises `NotImplementedError`.
  - `extract_fields(self, pages_obj: dict) -> Any` – raises `NotImplementedError`.
- Again, no runtime code uses this yet.

---

## 4. Configuration changes (`app/core/config.py`)

### 4.1 Existing structure (before Phase 0)

- Uses Pydantic Settings (when available) with env prefix `IDP_`.
- Fields:
  - `APP_NAME`
  - `ENV`
  - `LOG_LEVEL`
  - `RUNS_DIR` (defaulting to `.../idp-loan-deferment-service/runs`)
  - `TRACING_ENABLED`
- Has a minimal non‑Pydantic fallback class if Pydantic settings are unavailable.
- Provides `get_settings()` with `@lru_cache(maxsize=1)` for a singleton-like config.

### 4.2 New settings added in Phase 0

**What they are**
- New fields in the **Pydantic Settings** class:
  - `OCR_BASE_URL: str | None = None`
  - `OCR_TIMEOUT_SECONDS: int = 60`
  - `OCR_VERIFY_SSL: bool = True`
  - `LLM_BASE_URL: str | None = None`
  - `LLM_TIMEOUT_SECONDS: int = 60`
  - `LLM_VERIFY_SSL: bool = True`
  - `MAX_PDF_PAGES: int = 200`
  - `STAMP_ENABLED: bool = False`
- Equivalent fields in the **fallback Settings** class initialized from:
  - `IDP_OCR_BASE_URL`, `IDP_OCR_TIMEOUT_SECONDS`, `IDP_OCR_VERIFY_SSL`
  - `IDP_LLM_BASE_URL`, `IDP_LLM_TIMEOUT_SECONDS`, `IDP_LLM_VERIFY_SSL`
  - `IDP_MAX_PDF_PAGES`, `IDP_STAMP_ENABLED`

**Why needed**
- OCR configuration:
  - The OCR HTTP client (later phases) needs a base URL, timeout, and SSL behavior.
  - Having this in config/Settings keeps it environment‑driven and testable.
- LLM configuration:
  - Same reasoning for the LLM HTTP client.
- Limits & feature flags:
  - `MAX_PDF_PAGES` will help guard against huge documents.
  - `STAMP_ENABLED` allows enabling/disabling stamp checks at runtime.

**How it works (Phase 0)**
- Fields are **declared but not used** anywhere else yet.
- No code reads `OCR_BASE_URL`, `LLM_BASE_URL`, etc.
- This guarantees no behavior change.

### 4.3 RUNS_DIR (existing behavior, relevant for later)

**What it is**
- `RUNS_DIR` in Settings is the base directory where pipeline runs are stored.
- Default is `…/idp-loan-deferment-service/runs` (service‑local), computed via `_default_runs_dir()`.

**Why needed**
- Centralized place to store all artifacts for each `run_id`.
- Makes it easy to:
  - mount as a volume in Docker,
  - manage retention policies later,
  - debug by inspecting run folders.

**How it works**
- Existing logic (before Phase 0) remains unchanged.
- The `LocalStorage` implementation uses this directory via `get_settings().RUNS_DIR`.

---

## 5. Logging, RequestIdMiddleware (context from earlier phases)

Phase 0 did **not** change logging/middleware, but they are important for the overall architecture and future phases.

**What it is**
- A middleware that attaches a **request ID** to each incoming HTTP request and ensures logs include it.
- Logging is structured (key‑value), designed to be safe in async/concurrent environments.

**Why needed**
- Async servers handle many requests concurrently; without a request ID, logs from different requests can mix and become impossible to trace.
- A per‑request ID lets you:
  - follow one request through all logs and stages,
  - correlate logs with metrics and traces.

**How it works (high level)**
- The middleware runs for each request:
  - generates or propagates a request ID,
  - stores it in a context (e.g. `contextvars`) safe for async,
  - logging helpers read from this context and include `request_id` in log records.
- Because it uses async‑safe context storage, concurrent requests do not overwrite each other’s IDs.

Phase 0 did not change any of this; it remains as implemented earlier.

---

## 6. Summary – why Phase 0 matters

- **No behavior change:**
  - All new code is either unused stubs or simple re‑exports.
  - All existing tests passed after setting `PYTHONPATH=.`.
- **Architecture foundation:**
  - Clear layers: `application`, `domain`, `infrastructure`.
  - Ports for storage/OCR/LLM defined.
  - Domain pipeline skeleton in place.
  - Infrastructure stubs ready to be filled.
  - Config extended for future OCR/LLM and pipeline limits.
- **Future‑proofing:**
  - Later phases can plug in real logic stage by stage, with tests.
  - We can move behavior from `services` into `domain` and `application` without big rewrites.

Phase 0 sets the stage for Phase 1 (defining richer domain models and contracts) while keeping the running service completely stable.
