# Refactor Phase 2 – Explanation

Goal of Phase 2: implement **real infrastructure adapters** for storage and external services (OCR, LLM), fully tested and aligned with the domain ports from Phase 1, while keeping the **running FastAPI service behavior unchanged**.

This document explains every Phase 2 change:
- What each component is
- Why it is needed
- How it works (and how it is kept out of the live execution path)

Security/auth/retention still out of scope.

---

## 1. Local disk storage adapter

File: `app/infrastructure/storage/local_disk_adapter.py`

### 1.1 What it is

- A **concrete implementation** of the `StoragePort` interface that uses the local filesystem.
- It mirrors the behavior and directory layout of the existing `LocalStorage` in `app/services/storage/local_disk.py`.

### 1.2 Why needed

- Domain code talks via `StoragePort` and should not depend on how/where files are stored.
- To plug the domain pipeline into real storage later, we need a `StoragePort` implementation that:
  - preserves the current `runs/YYYY-MM-DD/<run_id>/...` layout,
  - can be swapped for another implementation (e.g., S3/MinIO) without changing domain code.
- In Phase 2, we just implement it and test it; runtime still uses the old storage layer.

### 1.3 How it works

Key imports and structure:

- Imports: `json`, `shutil`, `datetime`, `Path`, `StoragePort`.
- Class: `LocalDiskStorageAdapter(StoragePort)`.

#### 1.3.1 `_base_dir_for`

```python
def _base_dir_for(self, run_id: str) -> Path:
    date_str = datetime.now().strftime("%Y-%m-%d")
    return Path(self._base_dir) / date_str / run_id
```

- Exactly like `LocalStorage._base_dir_for`, this creates:
  - `<base_dir>/<YYYY-MM-DD>/<run_id>`
- This keeps compatibility with existing runs layout.

#### 1.3.2 `save_input`

```python
def save_input(self, run_id: str, src_path: Path) -> Path:
    base_dir = self._base_dir_for(run_id)
    input_dir = base_dir / "input"
    meta_dir = base_dir / "meta"
    input_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)

    src = Path(src_path)
    target_name = "document" + (src.suffix or "")
    dest = input_dir / target_name
    shutil.copy2(src, dest)
    return dest
```

- Creates the `input/` and `meta/` directories.
- Copies the source file into `input/document<ext>`.
- Returns a `Path` instead of `str`, consistent with `StoragePort`.
- Behavior is equivalent to existing `LocalStorage.save_input_file`.

#### 1.3.3 `write_json`

```python
def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path:
    base_dir = self._base_dir_for(run_id)
    dest = base_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return dest
```

- Writes JSON under the run directory at the given relative path (e.g., `meta/final_result.json`).
- Uses UTF‑8, human‑readable indent, same style as existing code.

#### 1.3.4 `read_json`

```python
def read_json(self, run_id: str, rel_path: str) -> dict:
    base_dir = self._base_dir_for(run_id)
    src = base_dir / rel_path
    with src.open("r", encoding="utf-8") as f:
        return json.load(f)
```

- Reads and returns the JSON as a `dict`.
- Propagates standard IO/JSON errors; domain will handle them later.

#### 1.3.5 `ensure_dirs`

```python
def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None:
    base_dir = self._base_dir_for(run_id)
    for d in rel_dirs:
        (base_dir / d).mkdir(parents=True, exist_ok=True)
```

- Ensures any relative subdirectories (e.g., `"meta"`, `"output"`) exist for a given run.

### 1.4 Tests for storage adapter

File: `tests/test_storage_adapter.py`

**What it is**
- A unit test that validates round‑trip behavior of `LocalDiskStorageAdapter`.

**Why needed**
- Ensures that the new adapter:
  - creates directories correctly,
  - saves input files correctly,
  - writes and reads JSON correctly.
- Gives confidence that swapping to this adapter later will preserve behavior.

**How it works**
- Uses `tmp_path` fixture as base directory.
- Creates a small fake PDF file.
- Calls `save_input`, asserts the destination exists and is named like `document*.pdf`.
- Calls `ensure_dirs` and `write_json`, asserts JSON file exists.
- Calls `read_json`, checks that the payload matches the original dict.

---

## 2. OCR HTTP adapter

File: `app/infrastructure/clients/ocr_http.py`

### 2.1 What it is

- A **sync httpx-based** implementation of `OCRPort`.
- Designed to talk to an OCR service with endpoints:
  - `POST /upload` → returns `{ "job_id": "..." }`
  - `GET /result/{job_id}` → returns status and page text.

### 2.2 Why needed

- Domain expects `OCRPort` to:
  - upload a PDF and get back a job id,
  - wait for completion and return an `OcrResult`.
- Having this adapter:
  - decouples domain from any HTTP/httpx specifics,
  - centralizes error handling for OCR calls,
  - makes it easy to adapt to different OCR services via configuration.

### 2.3 How it works

Key parts:

- Imports: `httpx`, `time`, `Path`, `OCRPort`, `OcrResult`, `OcrPage`.
- Class: `OcrHttpClient(OCRPort)`.

#### 2.3.1 Constructor and `_client`

```python
def __init__(
    self,
    base_url: str | None,
    timeout_seconds: int,
    verify_ssl: bool = True,
    transport: httpx.BaseTransport | None = None,
) -> None:
    self._base_url = base_url
    self._timeout_seconds = timeout_seconds
    self._verify_ssl = verify_ssl
    self._transport = transport
```

- Stores configuration from `Settings` (later wired via factories).
- `transport` parameter allows using `httpx.MockTransport` in tests.

```python
def _client(self) -> httpx.Client:
    if not self._base_url:
        raise RuntimeError("OCR base_url is not configured")
    return httpx.Client(
        base_url=self._base_url,
        timeout=self._timeout_seconds,
        verify=self._verify_ssl,
        transport=self._transport,
    )
```

- Centralized httpx client creation using the configured base URL and timeout.

#### 2.3.2 `upload`

```python
def upload(self, pdf_path: Path) -> str:
    with self._client() as client:
        with pdf_path.open("rb") as f:
            files = {"file": (pdf_path.name, f, "application/pdf")}
            resp = client.post("/upload", files=files)
        resp.raise_for_status()
        data = resp.json()
        job_id = data.get("job_id")
        if not isinstance(job_id, str) or not job_id:
            raise RuntimeError("OCR upload response missing job_id")
        return job_id
```

- Sends the file as multipart form data to `/upload`.
- Validates `job_id` presence and type.
- Raises runtime errors if response is invalid; domain still doesn’t see these yet.

#### 2.3.3 `wait_result`

```python
def wait_result(self, job_id: str, timeout: float, poll_interval: float) -> OcrResult:
    deadline = time.time() + timeout
    with self._client() as client:
        while True:
            resp = client.get(f"/result/{job_id}")
            resp.raise_for_status()
            data = resp.json()
            status = str(data.get("status", "")).lower()
            ...
```

- Polls `/result/{job_id}` until one of:
  - status `pending`/`processing` → sleep and retry.
  - status `succeeded` → parse pages into `OcrPage` and build `OcrResult`.
  - status `failed` → raise `RuntimeError`.
  - unknown status with timeout → raise `RuntimeError`.

Parsing path:

```python
pages_data = data.get("pages")
if pages_data is None and isinstance(data.get("result"), dict):
    pages_data = data["result"].get("pages")
...
for p in pages_data:
    page_number = int(p.get("page_number"))
    text = str(p.get("text", ""))
    pages.append(OcrPage(page_number=page_number, text=text))
return OcrResult(pages=pages, raw=data)
```

- Supports JSON with `pages` at top level or under `result.pages`.
- Wraps each page into `OcrPage`; attaches the full raw JSON.

### 2.4 OCR adapter tests

File: `tests/test_ocr_adapter.py`

**What it is**
- A test suite that exercises `OcrHttpClient` behavior using `httpx.MockTransport`.

**Why needed**
- Ensures the adapter correctly:
  - sends requests,
  - parses responses,
  - handles success and failure cases.
- Does not depend on a real OCR service; fully local.

**How it works**
- Defines a `handler(request: httpx.Request) -> httpx.Response` to emulate the server.
- First test (`test_ocr_adapter_upload_and_wait_success`):
  - For `POST /upload`: returns job id `job-123`.
  - For `GET /result/job-123`: returns status `succeeded` with two pages.
  - Verifies `upload` returns job id and `wait_result` returns an `OcrResult` with 2 pages.
- Second test (`test_ocr_adapter_wait_failed_raises`):
  - `GET /result/job-err` returns status `failed`.
  - Asserts `wait_result` raises `RuntimeError`.

---

## 3. LLM HTTP adapter

File: `app/infrastructure/clients/llm_http.py`

### 3.1 What it is

- A **sync httpx-based** implementation of `LLMPort`.
- It calls two LLM endpoints:
  - `/doc-type` – document type classification.
  - `/extract` – field extraction.

### 3.2 Why needed

- Domain expects `LLMPort` to:
  - classify document type based on OCR text,
  - extract structured fields for downstream validation and final decisions.
- Centralizing this in `LlmHttpClient` keeps LLM details away from domain and API layers.

### 3.3 How it works

Key parts:

- Imports: `httpx`, `LLMPort`, `OcrResult`, `DocTypeResult`, `ExtractionResult`.
- Class: `LlmHttpClient(LLMPort)`.

#### 3.3.1 Constructor and `_client`

```python
def __init__(
    self,
    base_url: str | None,
    timeout_seconds: int,
    verify_ssl: bool = True,
    transport: httpx.BaseTransport | None = None,
) -> None:
    self._base_url = base_url
    self._timeout_seconds = timeout_seconds
    self._verify_ssl = verify_ssl
    self._transport = transport
```

```python
def _client(self) -> httpx.Client:
    if not self._base_url:
        raise RuntimeError("LLM base_url is not configured")
    return httpx.Client(
        base_url=self._base_url,
        timeout=self._timeout_seconds,
        verify=self._verify_ssl,
        transport=self._transport,
    )
```

- Same pattern as OCR adapter; supports test `MockTransport`.

#### 3.3.2 `classify_doc_type`

```python
def classify_doc_type(self, pages_obj: OcrResult) -> DocTypeResult:
    payload = {"pages": [p.text for p in pages_obj.pages]}
    with self._client() as client:
        resp = client.post("/doc-type", json=payload)
        resp.raise_for_status()
        data = resp.json()
        doc_type = data.get("doc_type")
        ...
        return DocTypeResult(doc_type=doc_type, confidence=conf_val, raw=data)
```

- Sends only text (not metadata) from pages.
- Expects JSON with at least `doc_type` and optional `confidence`.
- Converts `confidence` to float if present; otherwise `None`.
- Wraps full payload in `raw` for debugging.
- Raises `RuntimeError` if `doc_type` is missing or invalid.

#### 3.3.3 `extract_fields`

```python
def extract_fields(self, pages_obj: OcrResult) -> ExtractionResult:
    payload = {"pages": [p.text for p in pages_obj.pages]}
    with self._client() as client:
        resp = client.post("/extract", json=payload)
        resp.raise_for_status()
        data = resp.json()
        fields = data.get("fields", {})
        if not isinstance(fields, dict):
            raise RuntimeError("LLM extract_fields missing fields dict")
        return ExtractionResult(fields=fields, raw=data)
```

- Expects JSON with `fields` as a dictionary.
- Raises `RuntimeError` if `fields` is missing or not a dict.

### 3.4 LLM adapter tests

File: `tests/test_llm_adapter.py`

**What it is**
- Tests for `LlmHttpClient` using `httpx.MockTransport`.

**Why needed**
- Ensures classification and extraction logic is correct and robust to malformed responses.

**How it works**

- `test_llm_adapter_classify_and_extract_success`:
  - Mocks:
    - `/doc-type` → `{ "doc_type": "loan_deferment", "confidence": 0.92 }`.
    - `/extract` → `{ "fields": {"fio": "Jane Doe", "amount": 123} }`.
  - Asserts:
    - `classify_doc_type` returns `DocTypeResult` with expected `doc_type` and non‑None `confidence`.
    - `extract_fields` returns `ExtractionResult` with correct fields.

- `test_llm_adapter_errors`:
  - `/doc-type` responds without `doc_type`.
  - `/extract` responds with non‑dict `fields`.
  - Asserts both methods raise `RuntimeError`.

---

## 4. Adapter factories (not wired yet)

File: `app/application/services/factories.py`

### 4.1 What it is

- A small module that builds **configured adapter instances** from `Settings`.

### 4.2 Why needed

- Centralizes adapter construction so that later phases can:
  - inject adapters into use‑cases and orchestrator via dependency injection,
  - avoid duplicating `get_settings()` calls and configuration logic.
- Keeping this in `application/services` keeps it out of domain and avoids direct config reads in lower layers.

### 4.3 How it works

```python
from app.core.config import get_settings
from app.infrastructure.storage.local_disk_adapter import LocalDiskStorageAdapter
from app.infrastructure.clients.ocr_http import OcrHttpClient
from app.infrastructure.clients.llm_http import LlmHttpClient


def build_storage_adapter() -> LocalDiskStorageAdapter:
    s = get_settings()
    return LocalDiskStorageAdapter(base_dir=s.RUNS_DIR)


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

- Uses existing `Settings` fields from Phase 0.
- Not imported anywhere in `main.py` or routes; they are purely preparatory helpers.

---

## 5. Dependencies (`requirements.txt`)

### 5.1 What changed

- Added:

```text
httpx>=0.27,<1.0
```

**Why needed**
- Both OCR and LLM adapters use `httpx.Client` and `httpx.MockTransport`.
- httpx is the modern, async‑ready HTTP client library; we use its sync API here for simplicity.

**How it works**
- Installed via `pip install -r requirements.txt`.
- Already present and working in your environment.

---

## 6. Behavior and tests summary

### 6.1 Behavior

- No wiring changes to:
  - `app/main.py`
  - `app/api/v1/*`
  - `app/services/*` (existing storage and pipeline still in use)
- No changes to `runs/` directory structure as seen by the live service.
- Adapters and factories are **implemented and tested**, but not used in production paths yet.

### 6.2 Tests

- Full test suite now includes:
  - `tests/test_domain_contracts.py`
  - `tests/test_storage_adapter.py`
  - `tests/test_ocr_adapter.py`
  - `tests/test_llm_adapter.py`
  - `tests/test_metrics.py`
  - `tests/test_smoke.py`
- All pass with:

```bash
PYTHONPATH=. pytest
# 12 passed
```

Phase 2 gives you a **ready-to-use infrastructure layer** that conforms to domain contracts and is fully tested, without changing any external behavior. This sets you up for Phase 3, where you’ll rebuild the domain pipeline stages using these ports, and Phase 4, where you’ll finally wire everything into the FastAPI endpoints.
