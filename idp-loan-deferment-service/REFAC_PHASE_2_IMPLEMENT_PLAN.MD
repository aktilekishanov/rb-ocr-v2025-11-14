# Refactor Phase 2 – Infrastructure Adapters (No Behavior Change Yet)

Goal of Phase 2: implement **real infrastructure adapters** for storage and external services **behind the ports** defined in Phase 1, while still **not switching the live service** to use them.

You should be able to:
- Construct fully working adapters for:
  - local disk storage (implements `StoragePort`)
  - OCR HTTP client (implements `OCRPort`)
  - LLM HTTP client (implements `LLMPort`)
- Unit test these adapters against dev/stub endpoints or mocks.
- Keep existing runtime behavior unchanged (FastAPI routes still use existing `services` code).

No imports from `apps/main-dev`. Security/auth retention still out of scope.

---

## 0. Constraints & success criteria

- **No wiring changes** to:
  - `app/main.py`
  - `app/api/v1/*`
  - `app/services/*`
- New adapters must conform to domain ports from Phase 1.
- OCR/LLM URLs, timeouts, and flags come from `core.config.Settings`.
- Tests pass with `PYTHONPATH=. pytest`.

At the end of Phase 2, adapters will be ready but not yet used by live endpoints.

---

## 1. Local disk storage adapter implementation

File: `app/infrastructure/storage/local_disk_adapter.py`

### 1.1 Design goals

- Implement `StoragePort` using the same directory layout that `LocalStorage` currently uses:
  - `runs/YYYY-MM-DD/<run_id>/input/...`
  - `runs/YYYY-MM-DD/<run_id>/meta/...`
- Keep behavior **equivalent** to the existing local storage in `app/services/storage/local_disk.py`.

### 1.2 Implementation steps

1. **Study the existing implementation** in `app/services/storage/local_disk.py`:
   - How it computes base dir from `RUNS_DIR`.
   - How it organizes `input/` and `meta/` folders.
   - How it names input document and JSON artifacts.

2. **Fill in adapter methods**:

   ```python
   class LocalDiskStorageAdapter(StoragePort):
       def __init__(self, base_dir: Path) -> None:
           self._base_dir = base_dir
   ```

   - Implement a private helper `_base_dir_for(run_id: str) -> Path` that mirrors the logic in `LocalStorage` (date-based path plus `run_id`).

   - Implement `ensure_dirs`:
     - For a given `run_id` and list of relative directories (e.g. `"input"`, `"meta"`):
       - Create them under the run base dir (`mkdir(parents=True, exist_ok=True)`).

   - Implement `save_input`:
     - Accept `src_path: Path`.
     - Use `_base_dir_for(run_id)` and create `input/` + `meta/` dirs.
     - Copy file to `input/document<ext>` similar to existing `LocalStorage`.
     - Return the destination `Path`.

   - Implement `write_json`:
     - Combine run base dir with `rel_path` (using `/` operator on `Path`).
     - Ensure parent directory exists.
     - Serialize `obj` as JSON with UTF‑8 encoding.
     - Return the path.

   - Implement `read_json`:
     - Build path as above and parse JSON into a `dict`.
     - Raise `FileNotFoundError` or propagate errors as is (domain stages will handle them later).

3. **Do not change any imports or references in runtime code**:
   - `LocalDiskStorageAdapter` should only be used in tests and later phases.

### 1.3 Tests for storage adapter

- Add tests in `tests/test_storage_adapter.py` (name suggestion):
  - Use a temporary directory (e.g., via `tmp_path` fixture) as `base_dir`.
  - Instantiate `LocalDiskStorageAdapter(base_dir=tmp_path)`. 
  - Verify:
    - `save_input` copies file to expected location.
    - `write_json` writes JSON and `read_json` reads back the same content.
    - `ensure_dirs` creates nested directories without error.

- Do not involve FastAPI or `LocalStorage`; these tests are pure adapter tests.

---

## 2. OCR HTTP client adapter implementation

File: `app/infrastructure/clients/ocr_http.py`

### 2.1 Design goals

- Implement `OCRPort` using **httpx** and configuration from `Settings`:
  - `OCR_BASE_URL`
  - `OCR_TIMEOUT_SECONDS`
  - `OCR_VERIFY_SSL`
- Support a typical async or sync pattern (choose one pattern and stick to it within the adapter; domain remains agnostic):
  - For a HTTP API that exposes endpoints such as `/upload` and `/result/{job_id}`.
- In Phase 2, it is acceptable to target your dev OCR endpoint behaviorally, without importing main-dev code.

### 2.2 Implementation outline

1. **Choose httpx style**
   - Implement **sync** methods for simplicity, since the port uses plain `def` and returns Pydantic models:
     - use `httpx.Client` under the hood.
   - Make sure to configure timeouts and SSL verification from settings passed into the constructor.

2. **Constructor and helpers**

   ```python
   class OcrHttpClient(OCRPort):
       def __init__(self, base_url: str | None, timeout_seconds: int, verify_ssl: bool = True) -> None:
           self._base_url = base_url
           self._timeout_seconds = timeout_seconds
           self._verify_ssl = verify_ssl
   ```

   - Add a private helper to build the httpx client:
     - `def _client(self) -> httpx.Client:` returning a client with base URL, timeout, and verify options.

3. **Implement `upload`**

   - Endpoint shape will be based on your actual OCR API; typical pattern:
     - `POST {base_url}/upload` with multipart `file`.
   - Steps:
     - Open `pdf_path` in binary mode.
     - `client.post("/upload", files={"file": (pdf_path.name, f, "application/pdf")})`.
     - Check HTTP status (raise or map to error later; for now, raise if non‑2xx).
     - Extract a job id from JSON, e.g. `resp.json()["job_id"]`.
     - Return the job id (type `str`).

4. **Implement `wait_result`**

   - Polling pattern:
     - `GET {base_url}/result/{job_id}` within a loop until success or timeout.
   - Steps:
     - Track elapsed time and compare against `timeout` argument.
     - Sleep for `poll_interval` between requests (e.g. use `time.sleep` in sync code).
     - On each response:
       - If job not finished, continue polling.
       - If finished with success, parse JSON payload into `OcrResult`:
         - Build `OcrPage` instances for each page.
         - Put raw payload into `OcrResult.raw` (optional).
       - If finished with failure or HTTP error, raise an exception (`OcrError` in later phases; for now raising a generic `RuntimeError` is acceptable inside this adapter, since domain is not yet wired).

5. **Keep adapter unused by runtime**

- Do not import `OcrHttpClient` from `main.py` or routes.
- The adapter is only constructed in adapter tests for now.

### 2.3 Tests for OCR adapter

- New file: `tests/test_ocr_adapter.py`.
- Options:
  - If you have a dev OCR endpoint available, use environment variables to conditionally run integration tests.
  - Otherwise, use `httpx.MockTransport` to mock responses.

- Test scenarios:
  - `upload` returns a string job id when server responds 200 with JSON.
  - `wait_result` converts JSON into `OcrResult` with expected number of pages.
  - Error responses (e.g., 500/404) raise an exception.

In Phase 2, don’t worry about mapping adapter errors to domain errors yet; just ensure adapter behavior is correct.

---

## 3. LLM HTTP client adapter implementation

File: `app/infrastructure/clients/llm_http.py`

### 3.1 Design goals

- Implement `LLMPort` using **httpx** with config from `Settings`:
  - `LLM_BASE_URL`
  - `LLM_TIMEOUT_SECONDS`
  - `LLM_VERIFY_SSL`
- Keep logic simple and explicit; this adapter should:
  - send OCR text/pages to LLM endpoints (e.g., `/doc-type`, `/extract`),
  - parse structured results into `DocTypeResult` and `ExtractionResult`.

### 3.2 Implementation outline

1. **Constructor & httpx client helper**

   ```python
   class LlmHttpClient(LLMPort):
       def __init__(self, base_url: str | None, timeout_seconds: int, verify_ssl: bool = True) -> None:
           self._base_url = base_url
           self._timeout_seconds = timeout_seconds
           self._verify_ssl = verify_ssl
   ```

   - Add `_client()` helper similar to `OcrHttpClient`.

2. **Implement `classify_doc_type`**

   - Accepts `pages_obj: OcrResult`.
   - Build a request payload, e.g.:

     ```python
     payload = {"pages": [p.text for p in pages_obj.pages]}
     ```

   - POST to `/doc-type` or equivalent endpoint.
   - Parse response JSON to build `DocTypeResult`:
     - `doc_type` from a key like `"doc_type"`.
     - `confidence` from e.g. `"confidence"` (if available).
     - `raw` as full JSON payload.

3. **Implement `extract_fields`**

   - Similar pattern; maybe call `/extract` endpoint.
   - Payload can reuse `pages_obj` or `doc_type` hints.
   - Parse response JSON into `ExtractionResult`:
     - `fields` from a mapping key, like `"fields"`.
     - `raw` as full JSON payload.

4. **Keep adapter unused by runtime**

- As with OCR, do not wire `LlmHttpClient` into endpoints yet.

### 3.3 Tests for LLM adapter

- New file: `tests/test_llm_adapter.py`.
- Use `httpx.MockTransport` or a dev LLM endpoint:
  - Ensure JSON responses convert to the expected Pydantic DTOs.
  - Verify edge cases (missing fields) raise appropriate errors or default values.

Again, mapping to domain errors is for a later phase; for now, correctness and structure are the focus.

---

## 4. Adapter construction helpers (optional, no wiring)

To keep wiring clean in later phases, you can add **factory functions** that build adapters from `Settings`, without using them yet.

### 4.1 New module suggestion: `app/application/services/factories.py`

- Define functions:

  ```python
  from app.core.config import get_settings
  from app.infrastructure.storage.local_disk_adapter import LocalDiskStorageAdapter
  from app.infrastructure.clients.ocr_http import OcrHttpClient
  from app.infrastructure.clients.llm_http import LlmHttpClient


  def build_storage_adapter() -> LocalDiskStorageAdapter:
      settings = get_settings()
      return LocalDiskStorageAdapter(base_dir=settings.RUNS_DIR)


  def build_ocr_client() -> OcrHttpClient:
      s = get_settings()
      return OcrHttpClient(
          base_url=s.OCR_BASE_URL,
          timeout_seconds=s.OCR_TIMEOUT_SECONDS,
          verify_ssl=s.OCR_VERIFY_SSL,
      )


  def build_llm_client() -> LlmHttpClient:
      s = get_settings()
      return LlmHttpClient(
          base_url=s.LLM_BASE_URL,
          timeout_seconds=s.LLM_TIMEOUT_SECONDS,
          verify_ssl=s.LLM_VERIFY_SSL,
      )
  ```

- **Do not** call these factories from `main.py` or routes yet.
- They are purely preparatory; they will simplify Phase 3/4 wiring.

---

## 5. No behavior changes checklist

While implementing Phase 2, ensure you **do not**:

- Change any existing calls in:
  - `app/services/pipeline_runner.py`
  - `app/services/jobs.py`
  - `app/services/storage/local_disk.py`
- Modify `app/api/v1/routes_process.py` or `routes_jobs.py` to use new adapters.
- Change the `runs/` directory structure or filenames currently written by the service.

Adapters and factories must be **added**, not used in live paths yet.

---

## 6. Phase 2 tests and acceptance criteria

### 6.1 Tests to run

- Unit tests:
  - `tests/test_storage_adapter.py`
  - `tests/test_ocr_adapter.py`
  - `tests/test_llm_adapter.py`
  - Existing tests: `tests/test_domain_contracts.py`, `tests/test_smoke.py`, `tests/test_metrics.py`

- Command:

  ```bash
  PYTHONPATH=. pytest
  ```

### 6.2 Acceptance criteria

- [ ] `LocalDiskStorageAdapter` fully implements `StoragePort` and passes its tests.
- [ ] `OcrHttpClient` implements `OCRPort` and passes adapter tests (mock or real dev endpoint).
- [ ] `LlmHttpClient` implements `LLMPort` and passes adapter tests (mock or dev endpoint).
- [ ] Optional factories exist to build adapters from `Settings`, but are unused by runtime.
- [ ] No imports from `apps/main-dev` anywhere.
- [ ] No changes to FastAPI routes, existing `services` modules, or `runs/` layout.
- [ ] `PYTHONPATH=. pytest` passes without public behavior changes.

Once all criteria are met, you will have a **fully implemented infrastructure layer** ready to be plugged into the domain orchestrator in Phase 3, while your service remains stable in production.
