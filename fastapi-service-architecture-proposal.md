# FastAPI Service Architecture Proposal v3 (Simplified)

## Executive Summary
A **minimal FastAPI wrapper** around the existing pipeline that exposes a single endpoint: `POST /v1/verify` accepting a file and FIO, returning verdict and errors.

---

## 1. Answers to Your Questions

### Q1: Can we remove `checks` and `artifacts` from response?
**YES, absolutely.**

**Rationale**:
- **`checks`**: Redundant. The `errors[]` array already contains all failed checks (e.g., `FIO_MISMATCH`, `DOC_DATE_TOO_OLD`). If `errors` is empty, all checks passed.
- **`artifacts`**: Internal implementation detail. API consumers don't need file paths to debug JSONs.

**Simplified Response** (see Section 2 for full spec):
```json
{
  "run_id": "20251126_140523_abc12",
  "verdict": true,
  "errors": [],
  "processing_time_seconds": 12.4
}
```

### Q2: Can we remove Kafka integration?
**YES.** You just need a simple HTTP endpoint for now. Kafka consumer can be a separate Python script that calls your API when needed.

### Q3: No migration needed?
**Correct.** Streamlit and FastAPI can coexist. No cutover needed.

---

## 2. API Specification

### Endpoint: `POST /v1/verify`

**Request**:
```http
POST /v1/verify HTTP/1.1
Content-Type: multipart/form-data

file: <binary PDF/image>
fio: "Иванов Иван Иванович"
```

**Response (Success - All checks passed)**:
```json
{
  "run_id": "20251126_140523_abc12",
  "verdict": true,
  "errors": [],
  "processing_time_seconds": 12.4
}
```

**Response (Failure - Some checks failed)**:
```json
{
  "run_id": "20251126_140530_def34",
  "verdict": false,
  "errors": [
    {
      "code": "FIO_MISMATCH",
      "message": "ФИО не совпадает"
    },
    {
      "code": "DOC_DATE_TOO_OLD",
      "message": "Устаревшая дата документа"
    }
  ],
  "processing_time_seconds": 8.2
}
```

**Response (Processing Error)**:
```json
{
  "run_id": "20251126_140535_ghi78",
  "verdict": false,
  "errors": [
    {
      "code": "OCR_FAILED",
      "message": "Ошибка распознавания OCR"
    }
  ],
  "processing_time_seconds": 2.1
}
```

---

## 3. Architecture

### 3.1 Directory Structure
```
apps/fastapi-service/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── main.py                    # FastAPI app entry
├── api/
│   ├── routes.py              # POST /v1/verify
│   └── schemas.py             # Pydantic models
├── services/
│   └── processor.py           # Wrapper around run_pipeline
└── pipeline/                  # SYMLINK to ../main-dev/rb-ocr/pipeline
    └── (orchestrator.py, processors/, etc.)
```

### 3.2 Data Flow
```
┌──────────────┐
│   Client     │
│  (curl/app)  │
└──────┬───────┘
       │ POST /v1/verify
       │ {file, fio}
       ▼
┌──────────────────────┐
│   FastAPI Service    │
│  ┌────────────────┐  │
│  │  routes.py     │  │
│  │  ↓             │  │
│  │  processor.py  │  │
│  │  ↓             │  │
│  │  run_pipeline  │  │
│  └────────────────┘  │
└──────────────────────┘
       │
       ▼
┌──────────────────────┐
│  Tesseract (OCR)     │
│  LLM (Classification)│
│  Stamp Detector (CV) │
└──────────────────────┘
       │
       ▼
    {verdict, errors}
```

---

## 4. Implementation

### 4.1 Minimal Code

#### `main.py`
```python
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from api.schemas import VerifyResponse, ErrorDetail
from services.processor import DocumentProcessor
import tempfile
import logging
import time

app = FastAPI(
    title="RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents"
)

processor = DocumentProcessor()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.post("/v1/verify", response_model=VerifyResponse)
async def verify_document(
    file: UploadFile = File(..., description="PDF or image file"),
    fio: str = Form(..., description="Applicant's full name (FIO)"),
):
    """
    Verify a loan deferment document.
    
    Returns:
    - `verdict`: True if all checks pass, False otherwise
    - `errors`: List of failed checks (empty if verdict=True)
    - `run_id`: Unique identifier for this request
    - `processing_time_seconds`: Total processing duration
    """
    start_time = time.time()
    logger.info(f"Verification request for FIO: {fio}, file: {file.filename}")
    
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=fio,
        )
        
        processing_time = time.time() - start_time
        
        return VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],
            processing_time_seconds=round(processing_time, 2),
        )
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal processing error: {str(e)}"
        )


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "service": "rb-ocr-api"}
```

#### `api/schemas.py`
```python
from pydantic import BaseModel, Field
from typing import List


class ErrorDetail(BaseModel):
    """Represents a single validation error."""
    code: str = Field(..., description="Error code (e.g., FIO_MISMATCH)")
    message: str | None = Field(None, description="Human-readable error message in Russian")


class VerifyResponse(BaseModel):
    """Response from document verification endpoint."""
    run_id: str = Field(..., description="Unique run identifier")
    verdict: bool = Field(..., description="True if document is valid, False otherwise")
    errors: List[ErrorDetail] = Field(
        default_factory=list,
        description="List of validation errors (empty if verdict=True)"
    )
    processing_time_seconds: float = Field(..., description="Total processing time")
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "20251126_140523_abc12",
                "verdict": True,
                "errors": [],
                "processing_time_seconds": 12.4
            }
        }
```

#### `services/processor.py`
```python
from pipeline.orchestrator import run_pipeline
from pathlib import Path
import asyncio


class DocumentProcessor:
    """Wrapper around the pipeline orchestrator."""
    
    def __init__(self, runs_root: str = "./runs"):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
    
    async def process_document(
        self,
        file_path: str,
        original_filename: str,
        fio: str,
    ) -> dict:
        """
        Process a document through the pipeline.
        
        Returns a dict with:
        - run_id: str
        - verdict: bool
        - errors: list of {code, message} dicts
        """
        # Run pipeline (it's currently synchronous, so run in executor)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: run_pipeline(
                fio=fio,
                source_file_path=file_path,
                original_filename=original_filename,
                content_type=None,
                runs_root=self.runs_root,
            )
        )
        
        # Extract only the fields we need for the API response
        return {
            "run_id": result.get("run_id"),
            "verdict": result.get("verdict", False),
            "errors": result.get("errors", []),
        }
```

#### `requirements.txt`
```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
gunicorn==21.2.0
python-multipart==0.0.6
pydantic==2.5.0

# Pipeline dependencies (reuse from main-dev)
httpx==0.25.1
rapidfuzz==3.5.2
pypdf==3.17.1
pillow==10.1.0
```

#### `Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create symlink to pipeline (assumes main-dev is at ../main-dev)
RUN ln -s /app/../main-dev/rb-ocr/pipeline /app/pipeline || true

# Create runs directory with proper permissions
RUN mkdir -p /app/runs && chmod 777 /app/runs

# Expose port
EXPOSE 8000

# Run with Gunicorn + Uvicorn workers
CMD ["gunicorn", "main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

#### `docker-compose.yml`
```yaml
version: '3.8'

services:
  api:
    build: .
    container_name: rb-ocr-api
    ports:
      - "8000:8000"
    volumes:
      - ./runs:/app/runs
      - ../main-dev/rb-ocr/pipeline:/app/pipeline:ro
    environment:
      - STAMP_ENABLED=true
      - LOG_LEVEL=INFO
    restart: unless-stopped
```

---

## 5. Setup & Deployment

### Step 1: Create Directory Structure
```bash
cd apps/
mkdir -p fastapi-service/{api,services}
cd fastapi-service
```

### Step 2: Copy Files
Copy the code from Section 4.1 into respective files.

### Step 3: Test Locally (Without Docker)
```bash
# Install dependencies
pip install -r requirements.txt

# Create symlink to existing pipeline
ln -s ../main-dev/rb-ocr/pipeline ./pipeline

# Run with uvicorn (single worker for dev)
uvicorn main:app --reload --port 8000
```

### Step 4: Test with curl
```bash
# Success case
curl -X POST http://localhost:8000/v1/verify \
  -F "file=@sample.pdf" \
  -F "fio=Иванов Иван Иванович"

# Expected response (if document is valid):
{
  "run_id": "20251126_223045_a1b2c",
  "verdict": true,
  "errors": [],
  "processing_time_seconds": 14.2
}
```

### Step 5: Deploy with Docker
```bash
# Build image
docker-compose build

# Start service
docker-compose up -d

# Check logs
docker-compose logs -f

# Test
curl -X POST http://localhost:8000/v1/verify \
  -F "file=@sample.pdf" \
  -F "fio=Иванов Иван Иванович"
```

### Step 6: Production Deployment (systemd)
```bash
# Create systemd service
sudo cp system/rb-ocr-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rb-ocr-api
sudo systemctl start rb-ocr-api

# Check status
sudo systemctl status rb-ocr-api
```

#### `system/rb-ocr-api.service`
```ini
[Unit]
Description=RB-OCR FastAPI Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/rb_admin2/apps/fastapi-service
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

---

## 6. API Documentation

Once deployed, FastAPI automatically generates interactive API docs at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

You can test the API directly from the browser at `/docs`.

---

## 7. Next Steps

### Immediate (Week 1)
1. Create `fastapi-service/` directory
2. Copy code from Section 4.1
3. Test locally with `uvicorn main:app --reload`
4. Verify with sample documents

### Optional (Future)
- Add Prometheus metrics (`/metrics` endpoint)
- Add request logging to PostgreSQL
- Add cache for repeated documents
- Add batch processing endpoint

---

## 8. Comparison: Before & After

| Aspect | Streamlit (Current) | FastAPI (New) |
|--------|---------------------|---------------|
| Interface | Web UI (manual) | HTTP API (programmatic) |
| Input | Upload + form | POST with multipart/form-data |
| Output | HTML page | JSON response |
| Use Case | Manual testing, demos | Automation, integration |
| Deployment | Single instance | Docker, scalable |
| Documentation | None | Auto-generated (Swagger) |

**Key Benefit**: Both can run simultaneously. Streamlit for demos, FastAPI for automation.
