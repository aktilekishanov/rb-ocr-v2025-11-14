# Implementation Plan: Move Configuration to .env

## Goal
Refactor the `fastapi-service` to remove hardcoded credentials and URLs, moving them to environment variables loaded from a `.env` file. This improves security and configurability across environments (DEV, PROD).

## 1. Create `.env.example`
Create a template file `apps/fastapi-service/.env.example` with **real development credentials** (as requested) to serve as a default.

```bash
# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=rb_ocr_db
DB_USER=postgres
DB_PASSWORD=postgres

# S3 / MinIO Configuration
S3_ENDPOINT=s3-dev.fortebank.com:9443
S3_ACCESS_KEY=fyz13d2czRW7l4sBW8gD
S3_SECRET_KEY=1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A
S3_BUCKET=loan-statements-dev
S3_SECURE=True

# External Services
OCR_BASE_URL=https://ocr.fortebank.com/v2
LLM_ENDPOINT_URL=https://dl-ai-dev-app01-uv01.fortebank.com/openai/payment/out/completions

# Application Settings
LOG_LEVEL=INFO
```

## 2. Refactor `pipeline/core/config.py`
Remove the `S3Config` class entirely.

- **File:** `apps/fastapi-service/pipeline/core/config.py`
- **Changes:**
    - Delete `class S3Config` and `s3_config = S3Config()`.
    - Keep other constants (`MAX_PDF_PAGES`, etc.).

## 3. Refactor `services/processor.py` (and S3 Client usage)
Update `DocumentProcessor` to read S3 credentials directly from environment variables.

- **File:** `apps/fastapi-service/services/processor.py`
- **Changes:**
    - Import `os`.
    - Remove `from pipeline.core.config import s3_config`.
    - In `__init__`, initialize `S3Client` using `os.getenv()` for endpoint, keys, and bucket.

## 4. Refactor `pipeline/clients/llm_client.py`
Remove hardcoded LLM endpoint URL.

- **File:** `apps/fastapi-service/pipeline/clients/llm_client.py`
- **Changes:**
    - Import `os`.
    - Replace `url = "..."` with `url = os.getenv("LLM_ENDPOINT_URL", "...")`.

## 5. Refactor `pipeline/clients/tesseract_async_client.py`
Remove hardcoded OCR base URL.

- **File:** `apps/fastapi-service/pipeline/clients/tesseract_async_client.py`
- **Changes:**
    - Import `os`.
    - Update `__init__` and `ask_tesseract_async` defaults to use `os.getenv("OCR_BASE_URL", "...")`.

## 6. Update `main.py`
Ensure environment variables are loaded on application startup.

- **File:** `apps/fastapi-service/main.py`
- **Changes:**
    - Add `from dotenv import load_dotenv` and `load_dotenv()` at the very top of the file.

## 7. Verification
- Create a local `.env` file (copy of `.env.example`).
- Run the application/tests to ensure it still connects to services correctly.
