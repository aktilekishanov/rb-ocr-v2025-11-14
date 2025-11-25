# Refactor Phase 0 – Scaffolding & No‑Behavior‑Change Setup

Goal of Phase 0: prepare the new architecture skeleton (directories, modules, and interfaces) **without changing existing runtime behavior** of `idp-loan-deferment-service`.

You should be able to:
- Run the app and all current tests exactly as before.
- Have new `application/`, `domain/`, and `infrastructure/` packages in place.
- Have ports/interfaces defined but not yet fully used by the live endpoints.

Security note: per guide `## 7) Security (SKIP FOR NOW)`, **do not** implement auth/PII/retention in this phase.

---

## 1. Current baseline (what must NOT break)

- Existing FastAPI app in `app/main.py`.
- Existing routers under `app/api/v1/` (`routes_process.py`, `routes_jobs.py`, `routes_health.py`).
- Existing storage abstraction (`app/services/storage/local_disk.py`) and `pipeline_runner.py` behavior.
- Existing observability (`app/observability/*`), metrics tests, and Docker build.

During Phase 0 you may **add** files and imports, but avoid:
- Changing request/response schemas.
- Changing endpoint behavior.
- Changing storage layout under `runs/`.

---

## 2. Create high‑level packages

In `app/`, create the following directories and `__init__.py` files:

- `app/application/__init__.py`
  - `app/application/usecases/__init__.py`
  - `app/application/services/__init__.py`
- `app/domain/__init__.py`
  - `app/domain/pipeline/__init__.py`
  - `app/domain/pipeline/stages/__init__.py`
  - `app/domain/ports/__init__.py`
- `app/infrastructure/__init__.py`
  - `app/infrastructure/storage/__init__.py`
  - `app/infrastructure/clients/__init__.py`

Do **not** move existing code yet. Only create empty modules and packages.

---

## 3. Define domain ports (interfaces) – skeleton only

Create the following files under `app/domain/ports/`:

- `storage_port.py`
- `ocr_port.py`
- `llm_port.py`

Each file defines typed Protocols with minimal signatures, e.g.:

- `storage_port.py`:
  - `StoragePort` with methods:
    - `save_input(run_id: str, src_path: str) -> Path`
    - `write_json(run_id: str, rel_path: str, obj: dict) -> Path`
    - `read_json(run_id: str, rel_path: str) -> dict`
    - `ensure_dirs(run_id: str, *rel_dirs: str) -> None`

- `ocr_port.py`:
  - `OCRPort` with:
    - `upload(pdf_path: Path) -> str | dict`
    - `wait_result(job_id: str, timeout: float, poll_interval: float) -> dict`

- `llm_port.py`:
  - `LLMPort` with:
    - `classify_doc_type(pages_obj: dict) -> dict`
    - `extract_fields(pages_obj: dict) -> dict`

These are **contracts only**; no implementation, no imports from `main-dev`.

Note: it is okay if some return types are still `dict`/`Any` in Phase 0; we will tighten them in later phases.

---

## 4. Define core domain pipeline skeleton

In `app/domain/pipeline/` create:

- `constants.py` – empty placeholders for now (e.g. filenames, limits).
- `models.py` – empty Pydantic model stubs for pipeline DTOs (we will fill later).
- `errors.py` – define a few base domain error classes / enums, but keep them unused for now.
- `orchestrator.py` – define the function signature only:
  - `async def run_pipeline(...):` or sync `def run_pipeline(...):` (align with your plan), but **raise NotImplementedError`** inside so it cannot be accidentally used.

Do **not** wire this orchestrator into the live app yet.

---

## 5. Application layer scaffolding

In `app/application/usecases/` create:

- `process_document.py` – define a placeholder use‑case function, e.g.:
  - `async def process_document(...): raise NotImplementedError`

In `app/application/services/`:

- Create `pipeline_runner.py` as a **thin forwarder** that will, in a later phase, call the domain orchestrator.
- For Phase 0, you may:
  - Either leave this file as a stub with `NotImplementedError` (and keep using the existing `app/services/pipeline_runner.py` in production code).
  - Or re‑export the existing implementation from **within this service only**, for example:
    - `from app.services.pipeline_runner import run_sync_pipeline as run_sync_pipeline`.
    - **Do not import anything from `apps/main-dev` here or anywhere else in this project.**

Key point: the running service should still use the existing `app/services/pipeline_runner.py` in Phase 0. Any new code must be clearly unused or only thin re‑exports.

---

## 6. Infrastructure layer scaffolding

In `app/infrastructure/storage/`:

- Create `local_disk_adapter.py` with a stub class `LocalDiskStorageAdapter(StoragePort)`.
  - For Phase 0, it is enough to:
    - Import `StoragePort` for type checking.
    - Declare method signatures matching `StoragePort` and raise `NotImplementedError`.
  - Do **not** replace current `app/services/storage/local_disk.py` yet.

In `app/infrastructure/clients/`:

- Create `ocr_http.py` and `llm_http.py` with stub classes `OcrHttpClient(OCRPort)` and `LlmHttpClient(LLMPort)`.
  - Methods should only raise `NotImplementedError`.
  - No httpx calls yet.

Nothing in `main.py` or the routers should import or use these new adapters in Phase 0.

---

## 7. Config preparation (no behavior changes)

Open `app/core/config.py` and **only** add new settings with safe defaults, without using them anywhere yet:

- `OCR_BASE_URL: str | None = None`
- `OCR_TIMEOUT_SECONDS: int = 60`
- `OCR_VERIFY_SSL: bool = True`
- `LLM_BASE_URL: str | None = None`
- `LLM_TIMEOUT_SECONDS: int = 60`
- `LLM_VERIFY_SSL: bool = True`
- `MAX_PDF_PAGES: int = 200`
- `STAMP_ENABLED: bool = False`

Do not change any existing settings or logic. Do not wire these into clients yet.

---

## 8. Keep security and retention out of scope

Per the refactor guide:

- **Skip** adding auth (JWT, mTLS), access control, or PII redaction in Phase 0.
- **Skip** retention/cleanup jobs for `runs/`.

You may leave TODO comments in future phases, but no runtime behavior must change in this phase.

---

## 9. Tests to run in Phase 0

After all scaffolding is in place:

- Run existing test suite, e.g.:
  - `pytest`
- Run basic manual checks:
  - `uvicorn app.main:app --reload`
  - Call `/health`, `/ready`, `/metrics`, `/v1/process` (with a small sample file), `/v1/jobs` flow.

All outcomes should match pre‑Phase‑0 behavior.

If anything changes:
- Back out the behavioral change; Phase 0 must be **architecture‑only scaffolding**.

---

## 10. Acceptance criteria for Phase 0

- New packages exist: `application/`, `domain/`, `infrastructure/`, `domain/ports`, `domain/pipeline/*`.
- Ports/interfaces are defined for storage, OCR, and LLM.
- Core pipeline/domain files (`constants.py`, `models.py`, `errors.py`, `orchestrator.py`) exist but are not yet wired into production.
- New infrastructure adapter stubs exist for storage and clients, unused by runtime.
- New config fields added with safe defaults and **no change** in current logic.
- All tests pass exactly as before; endpoints and Docker build behave identically.

Once Phase 0 is accepted, you can safely proceed to **Phase 1 – Define domain contracts and models** without fear of breaking current production behavior.
