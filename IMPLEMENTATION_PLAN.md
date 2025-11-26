# IMPLEMENTATION PLAN: FastAPI Service for RB-OCR

## Overview
Transform the existing Streamlit-based `main-dev` application into a production-ready FastAPI service without using symlinks. Each phase is designed to be sync-able and testable on the offline server.

**Constraints**:
- Server: Debian 12, Python 3.11, **NO internet access**
- Strategy: Copy/reorganize files from `main-dev/rb-ocr/` (no symlinks)
- Incremental: Test after each phase before continuing

---

## PHASE 0: Pre-Flight Preparation (MacBook)

### Objectives
- Prepare all dependencies offline
- Create clean directory structure
- Set up testing environment

### Tasks

#### 0.1 Download All Dependencies (CRITICAL for offline server)

> **⚠️ IMPORTANT**: We use Docker to download **Linux-compatible wheels** (not macOS wheels).
> Server is Debian 12 x86_64, so we need `manylinux_2_17_x86_64` wheels.

```bash
# On MacBook (with internet and Docker running):
cd ~/Downloads
rm -rf rb-ocr-dependencies  # Clean up if exists
mkdir rb-ocr-dependencies

# Use Docker with Debian 12 + Python 3.11 to download Linux x86_64 wheels
# --platform linux/amd64 is CRITICAL for Apple Silicon Macs
docker run --rm \
  --platform linux/amd64 \
  -v $(pwd)/rb-ocr-dependencies:/deps \
  python:3.11-slim-bookworm \
  /bin/bash -c "
    pip download \
      fastapi==0.104.1 \
      'uvicorn[standard]==0.24.0' \
      gunicorn==21.2.0 \
      python-multipart==0.0.6 \
      pydantic==2.5.0 \
      httpx==0.25.1 \
      rapidfuzz==3.5.2 \
      pypdf==3.17.1 \
      pillow==10.1.0 \
      -d /deps
  "

# Verify you have x86_64 Linux wheels (not aarch64 or macOS!)
echo "🔍 Verifying x86_64 Linux wheels..."
echo "First 3 compiled wheels:"
ls rb-ocr-dependencies/*.whl | grep manylinux | head -3
echo ""
echo "Should see: ...-manylinux_2_17_x86_64.whl (NOT aarch64!)"
echo "Pure Python wheels (any platform):"
ls rb-ocr-dependencies/*.whl | grep "py3-none-any" | head -3

# Count total files
echo "📦 Total packages downloaded: $(ls rb-ocr-dependencies/*.whl 2>/dev/null | wc -l)"

# Create requirements.txt
cat > rb-ocr-dependencies/requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn[standard]==0.24.0
gunicorn==21.2.0
python-multipart==0.0.6
pydantic==2.5.0
httpx==0.25.1
rapidfuzz==3.5.2
pypdf==3.17.1
pillow==10.1.0
EOF

# Tar the dependencies for transfer
tar -czf rb-ocr-dependencies.tar.gz rb-ocr-dependencies/

echo "✅ Created: rb-ocr-dependencies.tar.gz ($(du -h rb-ocr-dependencies.tar.gz | cut -f1))"
```

**Deliverable**: `rb-ocr-dependencies.tar.gz` containing **Linux x86_64 wheels** ready to copy to server

**Why Docker?**
- macOS `pip download` downloads macOS ARM64/x86_64 wheels
- Server needs Linux x86_64 wheels (`manylinux_2_17_x86_64.whl`)
- Docker container `python:3.11-slim-bookworm` = exact match to Debian 12 server
- Guarantees compatibility


-------


#### 0.2 Create Directory Structure
```bash
cd apps/
mkdir -p fastapi-service/{api,services,pipeline,runs,system}
cd fastapi-service
```

**Deliverable**: Empty directory structure in `apps/fastapi-service/`

#### 0.3 Backup main-dev
```bash
cd apps/
cp -r main-dev main-dev-backup-$(date +%Y%m%d)
```

### Sync to Server (Manual Copy-Paste Workflow)

Since you don't have direct MacBook-to-Server connection, follow this workflow:

#### Step 1: Copy to Windows PC
1. **On MacBook**: Copy `apps/` directory to USB drive or shared folder
2. **On Windows PC**: Paste to a temporary location (e.g., `C:\temp\apps\`)

#### Step 2: Transfer Dependencies
3. **On MacBook**: Copy `~/Downloads/rb-ocr-dependencies.tar.gz` to the same location

#### Step 3: Upload to Server via VS Code SSH
4. Open **VS Code** on Windows PC
5. Connect to server via **Remote-SSH extension**
6. Open folder `/home/rb_admin2/` in VS Code
7. **Drag and drop** or **copy-paste** files from Windows to server:
   - `C:\temp\apps\` → `/home/rb_admin2/apps/`
   - `rb-ocr-dependencies.tar.gz` → `/home/rb_admin2/`

> **Tip**: In VS Code, you can right-click in Explorer → "Upload..." to transfer files.

**Alternative**: Use WinSCP or FileZilla on Windows to upload to server.

### Validation on Server
```bash
# On server:
ls -la /home/rb_admin2/apps/fastapi-service/
ls -la /home/rb_admin2/rb-ocr-dependencies.tar.gz
python3 --version  # Should be 3.11
```

**✅ Phase 0 Complete**: Directory structure exists, dependencies ready, Python 3.11 confirmed

---

## PHASE 1: Copy Pipeline Code

### Objectives
- Copy all pipeline logic from `main-dev` to `fastapi-service`
- Preserve directory structure
- No modifications yet

### Tasks

#### 1.1 Copy Pipeline Directory
```bash
cd apps/fastapi-service/

# Copy entire pipeline/ directory
cp -r ../main-dev/rb-ocr/pipeline/ ./pipeline/

# Verify structure
tree -L 3 pipeline/
```

**Expected Structure**:
```
fastapi-service/pipeline/
├── __init__.py
├── orchestrator.py
├── clients/
│   ├── __init__.py
│   ├── llm_client.py
│   ├── tesseract_async_client.py
│   └── textract_client.py
├── core/
│   ├── config.py
│   ├── dates.py
│   ├── errors.py
│   ├── settings.py
│   └── validity.py
├── models/
│   └── dto.py
├── processors/
│   ├── __init__.py
│   ├── agent_doc_type_checker.py
│   ├── agent_extractor.py
│   ├── filter_llm_generic_response.py
│   ├── filter_ocr_response.py
│   ├── fio_matching.py
│   ├── image_to_pdf_converter.py
│   ├── merge_outputs.py
│   ├── stamp_check.py
│   └── validator.py
├── prompts/
│   ├── README.md
│   ├── dtc/
│   │   └── v1.prompt.txt
│   └── extractor/
│       └── v1.prompt.txt
└── utils/
    ├── __init__.py
    ├── artifacts.py
    ├── io_utils.py
    └── timing.py
```

#### 1.2 Verify Imports Work
```bash
cd apps/fastapi-service/
python3 << 'EOF'
import sys
sys.path.insert(0, '.')
from pipeline.orchestrator import run_pipeline
from pipeline.core.config import MAX_PDF_PAGES
print(f"✅ Pipeline imports OK. MAX_PDF_PAGES={MAX_PDF_PAGES}")
EOF
```

**Expected Output**: `✅ Pipeline imports OK. MAX_PDF_PAGES=3`

### Sync to Server
```bash
# From MacBook:
rsync -av --exclude '__pycache__' \
    apps/fastapi-service/pipeline/ \
    user@server:/home/rb_admin2/apps/fastapi-service/pipeline/
```

### Validation on Server
```bash
# On server:
cd /home/rb_admin2/apps/fastapi-service/
python3 -c "from pipeline.orchestrator import run_pipeline; print('OK')"
```

**✅ Phase 1 Complete**: Pipeline code copied, imports functional







----------- (personal comment: the above is fully implemented and tested on server) ---------------











## PHASE 2: FastAPI Core Files

### Objectives
- Create minimal FastAPI application
- Add Pydantic schemas
- Add processor service wrapper

### Tasks

#### 2.1 Create `api/schemas.py`
```bash
cd apps/fastapi-service/
cat > api/schemas.py << 'EOF'
"""Pydantic request/response schemas for API endpoints."""
from pydantic import BaseModel, Field
from typing import List


class ErrorDetail(BaseModel):
    """Represents a single validation error."""
    code: str = Field(..., description="Error code (e.g., FIO_MISMATCH)")
    message: str | None = Field(None, description="Human-readable message in Russian")


class VerifyResponse(BaseModel):
    """Response from document verification endpoint."""
    run_id: str = Field(..., description="Unique run identifier")
    verdict: bool = Field(..., description="True if all checks pass")
    errors: List[ErrorDetail] = Field(
        default_factory=list,
        description="List of validation errors"
    )
    processing_time_seconds: float = Field(..., description="Processing duration")

    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "20251126_140523_abc12",
                "verdict": True,
                "errors": [],
                "processing_time_seconds": 12.4
            }
        }
EOF
```

#### 2.2 Create `services/processor.py`
```bash
cat > services/processor.py << 'EOF'
"""Wrapper around pipeline orchestrator for FastAPI."""
from pipeline.orchestrator import run_pipeline
from pathlib import Path
import asyncio
import logging

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Processes documents through the RB-OCR pipeline."""
    
    def __init__(self, runs_root: str = "./runs"):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"DocumentProcessor initialized. runs_root={self.runs_root}")
    
    async def process_document(
        self,
        file_path: str,
        original_filename: str,
        fio: str,
    ) -> dict:
        """
        Process a document through the pipeline.
        
        Args:
            file_path: Temporary file path
            original_filename: Original uploaded filename
            fio: Applicant's full name
            
        Returns:
            dict with run_id, verdict, errors
        """
        logger.info(f"Processing: {original_filename} for FIO: {fio}")
        
        # Run pipeline in executor (it's synchronous)
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
        
        logger.info(f"Pipeline complete. run_id={result.get('run_id')}, verdict={result.get('verdict')}")
        
        # Return only API-relevant fields
        return {
            "run_id": result.get("run_id"),
            "verdict": result.get("verdict", False),
            "errors": result.get("errors", []),
        }
EOF
```

#### 2.3 Create `main.py`
```bash
cat > main.py << 'EOF'
"""FastAPI application entry point."""
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from api.schemas import VerifyResponse
from services.processor import DocumentProcessor
import tempfile
import logging
import time
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Initialize processor
processor = DocumentProcessor(runs_root="./runs")


@app.post("/v1/verify", response_model=VerifyResponse)
async def verify_document(
    file: UploadFile = File(..., description="PDF or image file"),
    fio: str = Form(..., description="Applicant's full name (FIO)"),
):
    """
    Verify a loan deferment document.
    
    **Returns**:
    - `verdict`: True if all checks pass, False otherwise
    - `errors`: List of failed checks (empty if verdict=True)
    - `run_id`: Unique identifier for this request
    - `processing_time_seconds`: Total processing duration
    """
    start_time = time.time()
    logger.info(f"[NEW REQUEST] FIO={fio}, file={file.filename}")
    
    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file.filename}") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    
    try:
        # Process document
        result = await processor.process_document(
            file_path=tmp_path,
            original_filename=file.filename,
            fio=fio,
        )
        
        processing_time = time.time() - start_time
        
        response = VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],
            processing_time_seconds=round(processing_time, 2),
        )
        
        logger.info(f"[RESPONSE] run_id={response.run_id}, verdict={response.verdict}, time={response.processing_time_seconds}s")
        return response
    
    except Exception as e:
        logger.error(f"[ERROR] {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal processing error: {str(e)}"
        )
    
    finally:
        # Cleanup temp file
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "rb-ocr-api",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "service": "RB-OCR Document Verification API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
    }
EOF
```

#### 2.4 Create `requirements.txt`
```bash
cat > requirements.txt << 'EOF'
# FastAPI and server
fastapi==0.104.1
uvicorn[standard]==0.24.0
gunicorn==21.2.0
python-multipart==0.0.6
pydantic==2.5.0

# Pipeline dependencies (from main-dev)
httpx==0.25.1
rapidfuzz==3.5.2
pypdf==3.17.1
pillow==10.1.0
EOF
```

### Sync to Server
```bash
# From MacBook:
rsync -av \
    apps/fastapi-service/{main.py,api/,services/,requirements.txt} \
    user@server:/home/rb_admin2/apps/fastapi-service/
```

### Validation on Server

#### Install Dependencies (OFFLINE)
```bash
# On server:
cd /home/rb_admin2/
tar -xzf rb-ocr-dependencies.tar.gz

# Create venv
cd /home/rb_admin2/apps/fastapi-service/
python3 -m venv .venv
source .venv/bin/activate

# Install from offline wheels
pip install --no-index --find-links /home/rb_admin2/rb-ocr-dependencies/ -r requirements.txt
```

#### Test Import
```bash
python3 << 'EOF'
from fastapi import FastAPI
from api.schemas import VerifyResponse
from services.processor import DocumentProcessor
print("✅ All imports successful")
EOF
```

"""personal comment:
Test Imports on Server
bash
# On server:
cd /home/rb_admin2/apps/fastapi-service/
source .venv/bin/activate

# Test imports
python3 << 'EOF'
from fastapi import FastAPI
from api.schemas import VerifyResponse
from services.processor import DocumentProcessor
print("✅ All FastAPI imports successful")
EOF
Expected: ✅
"""


**✅ Phase 2 Complete**: FastAPI core files created, dependencies installed offline





----------- (personal comment: the above is fully implemented and tested on server) ---------------






## PHASE 3: Local Testing (MacBook)

### Objectives
- Run FastAPI locally
- Test with sample document
- Verify response format

### Tasks

#### 3.1 Install Dependencies Locally
```bash
cd apps/fastapi-service/
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 3.2 Run FastAPI Server
```bash
uvicorn main:app --reload --port 8000
```

**Expected Output**:
```
INFO: Uvicorn running on http://127.0.0.1:8000
INFO: Application startup complete.
```

#### 3.3 Test Endpoints

**Test 1: Health Check**
```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy","service":"rb-ocr-api","version":"1.0.0"}
```

**Test 2: API Docs**
Open browser: `http://localhost:8000/docs`
- Should see Swagger UI
- Try "POST /v1/verify" endpoint

**Test 3: Verify Document (if you have a sample PDF)**
```bash
curl -X POST http://localhost:8000/v1/verify \
  -F "file=@/path/to/sample.pdf" \
  -F "fio=Иванов Иван Иванович"
```

**Expected Response**:
```json
{
  "run_id": "20251126_...",
  "verdict": true,
  "errors": [],
  "processing_time_seconds": 14.2
}
```

### Troubleshooting
If errors occur:
1. Check logs in terminal
2. Verify `runs/` directory is created
3. Check pipeline imports: `python3 -c "from pipeline.orchestrator import run_pipeline"`

**✅ Phase 3 Complete**: FastAPI running locally, endpoints tested




----------- (personal comment: phase 3 is skipped) ---------------





## PHASE 4: Deployment Configuration

### Objectives
- Create Dockerfile (for future)
- Create systemd service
- Create deployment scripts

### Tasks

#### 4.1 Create `Dockerfile` (Optional - for future containerization)
```bash
cat > Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create runs directory
RUN mkdir -p /app/runs && chmod 777 /app/runs

EXPOSE 8000

# Run with Gunicorn
CMD ["gunicorn", "main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
EOF
```

#### 4.2 Create systemd Service
```bash
cat > system/rb-ocr-fastapi.service << 'EOF'
[Unit]
Description=RB-OCR FastAPI Service
After=network.target

[Service]
Type=simple
User=rb_admin2
WorkingDirectory=/home/rb_admin2/apps/fastapi-service
Environment="PATH=/home/rb_admin2/apps/fastapi-service/.venv/bin"
ExecStart=/home/rb_admin2/apps/fastapi-service/.venv/bin/gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8001 \
    --timeout 60 \
    --access-logfile /var/log/rb-ocr-api/access.log \
    --error-logfile /var/log/rb-ocr-api/error.log
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

#### 4.3 Create Deployment Script
```bash
cat > deploy.sh << 'EOF'
#!/bin/bash
set -e

echo "🚀 Deploying RB-OCR FastAPI Service..."

# Activate venv
source .venv/bin/activate

# Verify dependencies
echo "📦 Verifying dependencies..."
pip check

# Test import
echo "🧪 Testing imports..."
python3 -c "from pipeline.orchestrator import run_pipeline; from api.schemas import VerifyResponse; print('✅ Imports OK')"

# Create log directory
sudo mkdir -p /var/log/rb-ocr-api
sudo chown rb_admin2:rb_admin2 /var/log/rb-ocr-api

# Install systemd service
echo "⚙️  Installing systemd service..."
sudo cp system/rb-ocr-fastapi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable rb-ocr-fastapi
sudo systemctl restart rb-ocr-fastapi

# Check status
sleep 2
sudo systemctl status rb-ocr-fastapi --no-pager

echo "✅ Deployment complete!"
echo "🔍 Check logs: sudo journalctl -u rb-ocr-fastapi -f"
echo "🌐 API Docs: http://localhost:8001/docs"
EOF

chmod +x deploy.sh
```

### Sync to Server
```bash
# From MacBook:
rsync -av \
    apps/fastapi-service/{Dockerfile,system/,deploy.sh} \
    user@server:/home/rb_admin2/apps/fastapi-service/
```

**✅ Phase 4 Complete**: Deployment configuration ready









---








## PHASE 5: Server Deployment

### Objectives
- Deploy to server
- Start service
- Verify it's running

### Tasks (On Server)

#### 5.1 Run Deployment Script
```bash
cd /home/rb_admin2/apps/fastapi-service/
./deploy.sh
```

#### 5.2 Verify Service Status
```bash
sudo systemctl status rb-ocr-fastapi
```

**Expected Output**: `Active: active (running)`

#### 5.3 Test Endpoints on Server
```bash
# Health check
curl http://localhost:8001/health

# Root endpoint
curl http://localhost:8001/
```

#### 5.4 Test Document Verification
```bash
# If you have a sample document:
curl -X POST http://localhost:8001/v1/verify \
  -F "file=@/path/to/sample.pdf" \
  -F "fio=Тестовый Пользователь"
```

### Troubleshooting

**Issue**: Service fails to start
```bash
# Check logs
sudo journalctl -u rb-ocr-fastapi -n 50 --no-pager

# Check port availability
sudo netstat -tlnp | grep 8001

# Manually test
cd /home/rb_admin2/apps/fastapi-service/
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8001
```

**Issue**: Import errors
```bash
# Verify Python path
source .venv/bin/activate
python3 -c "import sys; print('\n'.join(sys.path))"

# Test imports one by one
python3 -c "from pipeline.orchestrator import run_pipeline"
python3 -c "from api.schemas import VerifyResponse"
```

**✅ Phase 5 Complete**: Service running on server, accessible via HTTP

---

## PHASE 6: Integration Testing

### Objectives
- Test with real documents
- Validate error handling
- Performance benchmarking

### Tasks

#### 6.1 Prepare Test Documents
Create test cases:
1. **Valid document** (FIO matches, date valid, stamp present)
2. **FIO mismatch** (different name)
3. **Expired document** (old date)
4. **Invalid file** (not PDF/image)

#### 6.2 Run Test Suite
```bash
# Test 1: Valid document
curl -X POST http://localhost:8001/v1/verify \
  -F "file=@valid_document.pdf" \
  -F "fio=Иванов Иван Иванович" \
  | jq .

# Test 2: FIO mismatch
curl -X POST http://localhost:8001/v1/verify \
  -F "file=@valid_document.pdf" \
  -F "fio=Петров Петр Петрович" \
  | jq .

# Test 3: Invalid file
curl -X POST http://localhost:8001/v1/verify \
  -F "file=@random.txt" \
  -F "fio=Иванов Иван Иванович" \
  | jq .
```

#### 6.3 Performance Test
```bash
# Install apache bench (if available)
ab -n 10 -c 2 -p post_data.json -T 'multipart/form-data' \
  http://localhost:8001/v1/verify

# Or simple sequential test
for i in {1..10}; do
  time curl -X POST http://localhost:8001/v1/verify \
    -F "file=@sample.pdf" \
    -F "fio=Test User"
done
```

#### 6.4 Log Monitoring
```bash
# Watch logs in real-time
sudo journalctl -u rb-ocr-fastapi -f

# Check for errors
sudo grep -i error /var/log/rb-ocr-api/error.log
```

**✅ Phase 6 Complete**: Integration tests passed, performance acceptable

---

## PHASE 7: Documentation & Handoff

### Objectives
- Document API usage
- Create troubleshooting guide
- Update cheatsheet

### Tasks

#### 7.1 Create API Usage Guide
```bash
cat > API_USAGE.md << 'EOF'
# RB-OCR API Usage Guide

## Endpoints

### POST /v1/verify
Verify a loan deferment document.

**Request**:
```bash
curl -X POST http://localhost:8001/v1/verify \
  -F "file=@document.pdf" \
  -F "fio=Иванов Иван Иванович"
```

**Response**:
```json
{
  "run_id": "20251126_140523_abc12",
  "verdict": true,
  "errors": [],
  "processing_time_seconds": 12.4
}
```

### GET /health
Health check for monitoring.

### GET /docs
Interactive API documentation (Swagger UI).

## Error Codes

| Code | Message | Meaning |
|------|---------|---------|
| `FIO_MISMATCH` | ФИО не совпадает | Name doesn't match |
| `DOC_DATE_TOO_OLD` | Устаревшая дата документа | Document expired |
| `DOC_TYPE_UNKNOWN` | Тип документа не распознан | Unknown document type |
| `OCR_FAILED` | Ошибка OCR | OCR processing failed |

## Service Management

```bash
# Start service
sudo systemctl start rb-ocr-fastapi

# Stop service
sudo systemctl stop rb-ocr-fastapi

# Restart service
sudo systemctl restart rb-ocr-fastapi

# Check status
sudo systemctl status rb-ocr-fastapi

# View logs
sudo journalctl -u rb-ocr-fastapi -f
```
EOF
```

#### 7.2 Update Cheatsheet
Add to `apps/cheatsheet.md`:
```markdown
## FastAPI Service

### Service Management
```bash
sudo systemctl restart rb-ocr-fastapi
sudo systemctl status rb-ocr-fastapi
sudo journalctl -u rb-ocr-fastapi -f
```

### Testing
```bash
curl http://localhost:8001/health
curl http://localhost:8001/docs
```
```

**✅ Phase 7 Complete**: Documentation complete

---

## Success Criteria

### Phase Completion Checklist
- [ ] Phase 0: Dependencies downloaded, directory structure created
- [ ] Phase 1: Pipeline code copied, imports verified
- [ ] Phase 2: FastAPI files created, dependencies installed offline
- [ ] Phase 3: Service tested locally on MacBook
- [ ] Phase 4: Deployment files created
- [ ] Phase 5: Service deployed and running on server
- [ ] Phase 6: Integration tests passed
- [ ] Phase 7: Documentation complete

### Final Validation
1. **Service is running**: `sudo systemctl status rb-ocr-fastapi` shows `active`
2. **Health check passes**: `curl http://localhost:8001/health` returns `200 OK`
3. **Document processing works**: Test document returns valid JSON response
4. **Logs are clean**: No critical errors in logs
5. **Performance acceptable**: Processing time <30 seconds per document

---

## Appendix A: Quick Reference Commands

### MacBook (Development)
```bash
# Run locally
cd apps/fastapi-service
source .venv/bin/activate
uvicorn main:app --reload --port 8000

# Sync to server
rsync -av --exclude '__pycache__' --exclude '.venv' \
    apps/fastapi-service/ \
    user@server:/home/rb_admin2/apps/fastapi-service/
```

### Server (Production)
```bash
# Service control
sudo systemctl start|stop|restart|status rb-ocr-fastapi

# View logs
sudo journalctl -u rb-ocr-fastapi -f
tail -f /var/log/rb-ocr-api/error.log

# Test endpoint
curl http://localhost:8001/health
```

---

## Appendix B: Rollback Plan

If something goes wrong:

### Rollback to Streamlit
```bash
# Stop FastAPI
sudo systemctl stop rb-ocr-fastapi

# Restart Streamlit
sudo systemctl restart streamlit-dev

# Verify Streamlit works
curl http://localhost:8006/
```

### Restore from Backup
```bash
cd /home/rb_admin2/apps/
rm -rf fastapi-service
cp -r main-dev-backup-YYYYMMDD main-dev
```

---

## Appendix C: Offline Dependency Management

### Update Dependencies (MacBook with internet)
```bash
# Download new packages
pip download <package>==<version> -d ~/Downloads/rb-ocr-dependencies/

# Re-tar
tar -czf rb-ocr-dependencies.tar.gz rb-ocr-dependencies/

# Transfer to server
scp rb-ocr-dependencies.tar.gz user@server:/home/rb_admin2/
```

### Install on Server
```bash
tar -xzf rb-ocr-dependencies.tar.gz
pip install --no-index --find-links rb-ocr-dependencies/ <package>
```
