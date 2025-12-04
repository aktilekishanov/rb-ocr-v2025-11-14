# Forte FX Complex - Project Inspection Report

## Executive Summary

**Project Name:** forte-fx-complex (Exchange Control API)  
**Purpose:** Валютный контроль (Currency/Foreign Exchange Control) - An automated document processing system for validating foreign exchange contracts  
**Architecture:** Microservices-based FastAPI application with asynchronous task processing  
**Primary Language:** Python 3.13  
**Deployment:** Docker containerized with multi-stage builds

---

## 1. Project Overview

### 1.1 What It Does

The **forte-fx-complex** project is a **document verification and extraction system** specifically designed for **foreign exchange control compliance**. It:

1. **Receives business documents** (contracts, applications) via REST API
2. **Downloads files from S3 storage** using MinIO client
3. **Processes documents** through an OCR + GPT pipeline to extract structured data
4. **Validates extracted data** against source data from ForteBank (FB) systems
5. **Performs compliance checks** against regulatory requirements
6. **Stores results** in PostgreSQL database
7. **Sends callbacks** to frontend/notification systems

### 1.2 How It Works

**Workflow:**

```
1. Frontend/System → POST /api/v1/contracts (with document metadata + S3 paths)
2. API saves metadata to PostgreSQL → Enqueues Celery task
3. Celery Worker:
   a. Downloads files from S3 (MinIO)
   b. Preprocesses images (denoise, upscale, contrast adjustment)
   c. Runs OCR (Tesseract) on documents
   d. Sends OCR text + schema to GPT-4.1 via DMZ proxy
   e. Extracts structured fields from GPT response
   f. Cross-checks extracted data vs. FB source data
   g. Runs compliance control validation
   h. Saves results to database
   i. Sends callback to frontend
4. Frontend polls GET /api/v1/contracts/{id}/status and retrieves results
```

### 1.3 Why It's Needed

**Business Problem:** Manual verification of foreign exchange contracts is:
- Time-consuming and error-prone
- Requires expert knowledge of regulations
- Difficult to scale during high-volume periods

**Solution:** This system automates:
- Data extraction from scanned/PDF documents
- Cross-validation against bank's internal systems
- Compliance checking against regulatory rules
- Audit trail and correction tracking

---

## 2. Technology Stack

### 2.1 Core Framework
- **FastAPI 0.116.1** - Modern async web framework
- **Python 3.13** - Latest Python with performance improvements
- **Uvicorn 0.35.0** - ASGI server (4 workers in production)

### 2.2 Database & Caching
- **PostgreSQL** (via asyncpg 0.30.0) - Primary data store
- **SQLAlchemy 2.0.42** - Async ORM
- **Alembic 1.16.4** - Database migrations
- **Redis 6.3.0** - Celery broker and result backend

### 2.3 Task Queue
- **Celery 5.5.3** - Distributed task queue
  - Worker pool: `prefork` (5 concurrent workers)
  - Max tasks per child: 50 (prevents memory leaks)
  - Max memory per child: ~800 MB
  - Task timeout: 1800s (30 min hard limit)

### 2.4 Document Processing
- **Tesseract OCR** (pytesseract 0.3.13)
  - Languages: Kazakh, Russian, English
- **OpenCV 4.12.0.88** - Image preprocessing
- **pdf2image 1.17.0** - PDF to image conversion
- **Pillow 11.3.0** - Image manipulation
- **python-docx 1.2.0** - Word document handling

### 2.5 AI/ML Components
- **GPT-4.1** (via DMZ proxy) - Structured data extraction
- **scikit-learn 1.7.1** - Similarity checking
- **numpy 2.2.6** - Numerical operations

### 2.6 Storage
- **MinIO 7.2.16** - S3-compatible object storage client
- Custom SSL handling for internal certificate authorities

### 2.7 Infrastructure
- **Docker** - Multi-stage builds for optimization
- **Docker Compose** - Orchestration (dev, db-only, prod configs)
- **Proxy Support** - Corporate proxy configuration (headproxy03.fortebank.com:8080)

---

## 3. Architecture & Components

### 3.1 Application Structure

```
src/
├── main.py                 # FastAPI app entry point
├── core/                   # Core infrastructure
│   ├── config.py          # Settings (DB, Redis, S3, App)
│   ├── database.py        # Async DB session management
│   ├── s3.py              # S3Client (MinIO wrapper)
│   ├── celery_app.py      # Celery configuration
│   └── logging.py         # Logging setup
├── contracts/             # Main business domain
│   ├── router.py          # API endpoints (11 routes)
│   ├── service.py         # Business logic layer
│   ├── tasks.py           # Celery background tasks
│   ├── models.py          # SQLAlchemy models
│   ├── schemas.py         # Pydantic request/response models
│   ├── dependencies.py    # FastAPI dependencies
│   ├── exceptions.py      # Custom exceptions
│   └── constants.py       # Status codes, error codes
└── common/                # Shared utilities
    ├── file_s3.py         # S3 file loading helper
    ├── callback.py        # Frontend callback sender
    ├── compliance_control.py  # Compliance API client
    ├── gpt/               # GPT client & prompts
    ├── ocr/               # OCR wrapper
    ├── pipeline/          # Document processing pipeline
    ├── image_preprocessing/  # Image enhancement
    ├── similarity_check/  # Data comparison logic
    └── pydantic_models/   # Shared data models
```

### 3.2 Database Schema

**Table: `contracts`**
```sql
- id (PK)
- document_id (unique) - Business identifier
- status - Processing state (uploaded/done/failed)
- data_json (JSONB) - Source data from ForteBank
- docs_json (JSONB) - File references (DocumentBasic, ApplicationDocument)
- result_json (JSONB) - Raw extraction results with coordinates
- flat_result_json (JSONB) - Flattened key-value extraction
- cross_check_json (JSONB) - Validation results
- compliance_check_json (JSONB) - Compliance validation
- error_message (TEXT) - Error details if failed
- retry_count (INT) - Retry attempts
- created_at, updated_at (TIMESTAMP)
```

**Table: `field_corrections`**
```sql
- document_id (FK, PK)
- field_name (PK)
- current_value (JSONB) - Extracted value
- correct_value (JSONB) - User-corrected value
- created_at (PK) - Correction timestamp
```

### 3.3 API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/contracts/` | Submit document for processing |
| GET | `/api/v1/contracts/{id}/status` | Get processing status |
| GET | `/api/v1/contracts/{id}/result` | Get extraction results |
| GET | `/api/v1/contracts/{id}/files` | Get file references |
| GET | `/api/v1/contracts/{id}/coordinates` | Get field coordinates (for UI highlighting) |
| GET | `/api/v1/contracts/{id}/cross-check` | Get validation results |
| GET | `/api/v1/contracts/{id}/compliance-check` | Get compliance results |
| GET | `/api/v1/contracts/{id}/fb-data` | Get source FB data |
| GET | `/api/v1/contracts/{id}/download` | Download file from S3 |
| POST | `/api/v1/contracts/{id}/corrections` | Submit field correction |

---

## 4. Key Features

### 4.1 Asynchronous Processing
- Non-blocking API endpoints using `async/await`
- Background task processing via Celery
- Immediate 202 Accepted response on submission

### 4.2 Retry & Resilience
- Exponential backoff for GPT API calls (4 attempts, max 12s wait)
- Celery task retries with memory limits
- Worker process recycling to prevent memory leaks

### 4.3 Data Validation
- **Cross-checking:** Compares extracted data vs. source data using similarity algorithms
- **Compliance control:** External API validation against regulatory rules
- **Field corrections:** Tracks user corrections for ML improvement

### 4.4 Audit Trail
- All processing stages stored in database
- Timestamps for creation and updates
- Error messages preserved for debugging

### 4.5 Structured Output
- GPT-4.1 with JSON Schema mode (strict validation)
- Pydantic models for type safety
- Coordinate tracking for UI highlighting

---

## 5. Configuration & Environment

### 5.1 Required Environment Variables

**Database:**
```
POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD
POSTGRES_HOST, POSTGRES_PORT
```

**Redis:**
```
REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
```

**S3/MinIO:**
```
MINIO_ENDPOINT - S3 server address
MINIO_ACCESS_KEY - Access key ID
MINIO_SECRET_KEY - Secret access key
MINIO_SECURE - Use HTTPS (true/false)
MINIO_BUCKET - Bucket name
MINIO_VERIFY_SSL - SSL verification (path to CA cert or false)
```

**Application:**
```
FRONTEND_CALLBACK_URL - Callback endpoint for notifications
DMZ_URL - GPT API proxy endpoint
COMPLIANCE_CONTROL_URL - Compliance validation API
VERIFY_SSL - SSL verification for external APIs
```

### 5.2 Docker Deployment

**Multi-stage Build:**
1. **Builder stage:** Installs system dependencies (Tesseract, poppler, OpenCV libs)
2. **Production stage:** Copies only necessary artifacts, runs as non-root user

**Services (docker-compose.dev.yml):**
- `db` - PostgreSQL with health checks
- `redis` - Redis with password auth
- `backend` - FastAPI application (port 8000)
- `worker` - Celery worker (contracts queue)

---

## 6. S3 Integration - Complete Analysis

### 6.1 S3 Overview

The project uses **MinIO** (S3-compatible object storage) to store and retrieve document files. Files are **NOT uploaded through this API** - they are pre-uploaded to S3 by external systems, and this API receives only the S3 object keys (paths).

### 6.2 S3 Configuration

**Location:** `src/core/config.py`

```python
class S3Settings(BaseSettings):
    MINIO_ENDPOINT: str          # e.g., "s3.example.com:9000"
    MINIO_ACCESS_KEY: str        # Access key ID
    MINIO_SECRET_KEY: str        # Secret key
    MINIO_SECURE: bool           # Use HTTPS
    MINIO_BUCKET: str            # Bucket name
    MINIO_VERIFY_SSL: str | bool # CA cert path or False
```

**Loaded from `.env` file** using Pydantic Settings with automatic validation.

### 6.3 S3 Client Implementation

**Location:** `src/core/s3.py`

**Class:** `S3Client`

**Initialization:**
```python
def __init__(self):
    # Custom SSL handling
    http_client = None
    
    # Option 1: Custom CA certificate
    if isinstance(s3_settings.MINIO_VERIFY_SSL, str):
        ctx = ssl.create_default_context(cafile=s3_settings.MINIO_VERIFY_SSL)
        http_client = urllib3.PoolManager(ssl_context=ctx)
    
    # Option 2: Disable SSL verification (dev/test)
    elif not s3_settings.MINIO_VERIFY_SSL:
        http_client = urllib3.PoolManager(
            cert_reqs=ssl.CERT_NONE,
            assert_hostname=False
        )
    
    # Create MinIO client
    self.client = Minio(
        s3_settings.MINIO_ENDPOINT,
        access_key=s3_settings.MINIO_ACCESS_KEY,
        secret_key=s3_settings.MINIO_SECRET_KEY,
        secure=s3_settings.MINIO_SECURE,
        region="random-place-in-ekibastuz",  # Custom region
        http_client=http_client
    )
    self.bucket = s3_settings.MINIO_BUCKET
```

**Key Method:** `download_bytes(key: str) -> bytes | None`

```python
def download_bytes(self, key: str) -> bytes | None:
    k = self._normalize_key(key)  # Clean up key format
    resp = self.client.get_object(self.bucket, k)
    try:
        return resp.read()  # Read entire object into memory
    finally:
        resp.close()
        resp.release_conn()  # Proper connection cleanup
```

**Helper Method:** `_normalize_key(key: str) -> str`

Defensive key normalization:
- Strips leading/trailing whitespace
- Removes leading slashes
- Removes accidental bucket prefix if present

### 6.4 S3 Usage Flow

**Step 1: Document Submission**

Frontend sends POST request with S3 keys:
```json
{
  "Document": {
    "Document_id": "DOC123",
    "Data": [...],
    "DocumentBasic": [
      {"Truename": "contract.pdf", "Document": "path/to/contract.pdf"}
    ],
    "ApplicationDocument": [
      {"Truename": "app.pdf", "Document": "path/to/app.pdf"}
    ]
  }
}
```

**Step 2: Metadata Storage**

API saves `docs_json` to database:
```python
docs = {
    "DocumentBasic": [{"Truename": "...", "Document": "s3_key"}],
    "ApplicationDocument": [...]
}
contract.docs_json = docs  # Stored in PostgreSQL JSONB
```

**Step 3: Celery Task Downloads Files**

**Location:** `src/common/file_s3.py`

```python
def load_entries_from_s3(entries: List[Dict[str, str]]) -> Dict[str, bytes]:
    s3 = S3Client()
    file_map: Dict[str, bytes] = {}
    
    for entry in entries:
        key = entry["Document"]       # S3 object key
        filename = entry["Document"]  # Filename for processing
        content = s3.download_bytes(key)
        file_map[filename] = content  # In-memory bytes
    
    return file_map
```

**Called in:** `src/contracts/tasks.py`

```python
extractor = Pipeline(
    main_file_dict=load_entries_from_s3(main_path),      # DocumentBasic
    extra_file_dict=load_entries_from_s3(optional_paths), # ApplicationDocument
    ...
)
```

**Step 4: Processing Pipeline**

Files are processed **entirely in memory** (no disk writes):
1. PDF → Images (pdf2image)
2. Image preprocessing (OpenCV)
3. OCR (Tesseract)
4. GPT extraction
5. Results stored in database

**Step 5: File Download Endpoint**

Users can download original files via API:

**Endpoint:** `GET /api/v1/contracts/{document_id}/download?document={s3_key}`

**Implementation:** `src/contracts/service.py`

```python
async def download_file(self, document_id: str, key: str) -> tuple[str, BytesIO]:
    contract = await self._get_contract(document_id)
    
    # Search for key in stored metadata
    for section in ("DocumentBasic", "ApplicationDocument"):
        for entry in contract.docs_json.get(section, []):
            if entry.get("Document") == key:
                data = self.storage.download_bytes(key)  # Download from S3
                if data is None:
                    raise FileKeyNotFoundError(...)
                
                buf = BytesIO(data)  # Create in-memory buffer
                buf.seek(0)
                return entry["Truename"], buf  # Return filename + buffer
    
    raise FileKeyNotFoundError(...)
```

Returns `StreamingResponse` with proper Content-Disposition headers.

### 6.5 S3 Security

**SSL/TLS:**
- Supports custom CA certificates for internal PKI
- Can disable verification for development (not recommended for prod)

**Access Control:**
- Credentials stored in environment variables (not in code)
- Separate access key per environment

**Connection Management:**
- Proper connection pooling via urllib3
- Explicit connection release to prevent leaks

### 6.6 S3 Error Handling

**Missing Files:**
- `download_bytes()` returns `None` if object not found
- Service layer raises `FileKeyNotFoundError`
- API returns 404 with error code

**Network Errors:**
- MinIO client handles retries internally
- Connection timeouts propagate to Celery task
- Task can retry with exponential backoff

### 6.7 S3 Limitations & Considerations

**Memory Usage:**
- Files loaded entirely into RAM (no streaming)
- Worker memory limit: 800 MB per child process
- Large files (>100 MB) may cause OOM

**No Upload Support:**
- This API only **downloads** from S3
- External systems must handle uploads
- API receives pre-uploaded S3 keys

**No Lifecycle Management:**
- Files remain in S3 indefinitely
- No automatic cleanup or archival
- Manual S3 bucket policies needed

**Single Bucket:**
- All documents in one bucket
- No multi-bucket support
- Relies on S3 key prefixes for organization

### 6.8 S3 Data Flow Diagram

```
┌─────────────┐
│  Frontend   │
│   System    │
└──────┬──────┘
       │ 1. Upload files
       ↓
┌─────────────┐
│  S3/MinIO   │◄────────────────┐
│   Storage   │                 │
└──────┬──────┘                 │
       │                        │
       │ 2. Send S3 keys        │ 4. Download files
       ↓                        │
┌─────────────┐                 │
│  FastAPI    │                 │
│     API     │                 │
└──────┬──────┘                 │
       │                        │
       │ 3. Enqueue task        │
       ↓                        │
┌─────────────┐                 │
│   Celery    │─────────────────┘
│   Worker    │
└──────┬──────┘
       │ 5. Process in memory
       ↓
┌─────────────┐
│ PostgreSQL  │
│  Database   │
└─────────────┘
```

### 6.9 S3 Configuration Example

**Development (.env):**
```env
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET=contracts
MINIO_VERIFY_SSL=false
```

**Production (.env):**
```env
MINIO_ENDPOINT=s3.internal.fortebank.com:9000
MINIO_ACCESS_KEY=prod_access_key
MINIO_SECRET_KEY=prod_secret_key
MINIO_SECURE=true
MINIO_BUCKET=exchange-control-prod
MINIO_VERIFY_SSL=/etc/ssl/certs/forte-ca.crt
```

### 6.10 S3 Dependency Injection

**Location:** `src/contracts/dependencies.py`

```python
async def get_s3_client() -> S3Client:
    """Get S3 client instance."""
    return S3Client()

async def get_contract_service(
    session: AsyncSession = Depends(get_db),
    s3_client: S3Client = Depends(get_s3_client),
) -> ContractService:
    return ContractService(session, storage_client=s3_client)
```

**Benefits:**
- Testable (can inject mock S3 client)
- Singleton pattern (one client per request)
- Clean separation of concerns

---

## 7. Processing Pipeline

### 7.1 Pipeline Components

**Location:** `src/common/pipeline/pipeline.py`

**Adapters:**
- `ImagePreprocessAdapter` - Image enhancement (denoise, upscale, contrast)
- `OCRAdapter` - Tesseract wrapper
- `LLMAdapter` - GPT-4.1 client wrapper

**Input:**
- `main_file_dict` - Primary documents (contracts)
- `extra_file_dict` - Supporting documents (applications)
- `client_data` - Source data from ForteBank (FbData model)

**Output:**
- `raw` - Full extraction with coordinates
- `fb_json` - Flattened key-value pairs
- `skk_json` - Additional structured data

### 7.2 GPT Integration

**Location:** `src/common/gpt/dmz_client.py`

**DMZClient Features:**
- Structured output with JSON Schema validation
- Retry logic (4 attempts, exponential backoff)
- Token usage logging
- Pydantic model validation

**Request Format:**
```python
payload = {
    "Model": "gpt-4.1",
    "Content": json.dumps(messages),
    "MaxTokens": 32767,
    "Temperature": 0.1,
    "response_format": {
        "type": "json_schema",
        "json_schema": {
            "name": "ParsingResults",
            "strict": True,
            "schema": pydantic_schema_dict(ParsingResults)
        }
    }
}
```

**Response Parsing:**
- Extracts OpenAI response from DMZ wrapper
- Validates against Pydantic schema
- Returns typed model instance

---

## 8. Deployment & Operations

### 8.1 Build Process

```bash
# Build image
docker build -t exchange-control .

# Save for transfer
docker save exchange-control > exchange-control.tar

# Transfer to server
scp exchange-control.tar dladmin@10.0.94.205:/home/dladmin/fxcomplex/docker-images
```

### 8.2 Database Migrations

```bash
# Enter container
docker exec -it app_exchange_control sh

# Run migrations
alembic upgrade head
```

### 8.3 Monitoring Points

**Health Checks:**
- PostgreSQL: `pg_isready`
- Redis: `redis-cli ping`
- API: HTTP 200 on root endpoint

**Metrics to Monitor:**
- Celery queue length
- Task processing time
- Worker memory usage
- Database connection pool
- S3 download failures
- GPT API errors

---

## 9. Security Considerations

### 9.1 Current Security Measures
- Non-root Docker user (`appuser`)
- Environment variable secrets
- SSL/TLS for S3 and external APIs
- Database connection encryption (asyncpg)

### 9.2 Potential Improvements
- API authentication/authorization (currently none)
- Rate limiting on endpoints
- Input validation on S3 keys (path traversal prevention)
- Secrets management (Vault, AWS Secrets Manager)
- Audit logging for sensitive operations

---

## 10. Testing

**Location:** `tests/` directory (21 test files)

**Test Configuration:** `pytest.ini`

**Coverage Areas:**
- Unit tests for individual components
- Integration tests for pipeline
- Mock S3 client for testing

---

## 11. Key Findings & Recommendations

### 11.1 Strengths
✅ Well-structured codebase with clear separation of concerns  
✅ Async/await for performance  
✅ Comprehensive error handling  
✅ Database migrations with Alembic  
✅ Retry logic for external dependencies  
✅ Memory management in Celery workers  

### 11.2 Areas for Improvement

**Performance:**
- Consider streaming large files instead of loading into memory
- Implement caching for frequently accessed documents
- Add database query optimization (indexes on status, created_at)

**Reliability:**
- Add dead letter queue for failed tasks
- Implement circuit breaker for external APIs
- Add health check endpoint for API

**Security:**
- Add API authentication (JWT, API keys)
- Implement role-based access control
- Add request validation middleware
- Sanitize S3 keys to prevent path traversal

**Observability:**
- Add structured logging (JSON format)
- Implement distributed tracing (OpenTelemetry)
- Add metrics export (Prometheus)
- Create dashboards for monitoring

**S3 Specific:**
- Add support for multipart uploads (if upload feature added)
- Implement S3 presigned URLs for direct downloads
- Add file size validation before download
- Consider S3 lifecycle policies for old documents

---

## 12. Dependencies Summary

**Total Dependencies:** 60+ packages

**Critical Dependencies:**
- FastAPI, Uvicorn - Web framework
- SQLAlchemy, asyncpg - Database
- Celery, Redis - Task queue
- MinIO - S3 client
- Tesseract, OpenCV - OCR
- Requests - HTTP client
- Pydantic - Data validation

**Development Dependencies:**
- pytest - Testing
- mypy - Type checking
- ruff - Linting

---

## Conclusion

The **forte-fx-complex** project is a production-ready document processing system with robust S3 integration for foreign exchange control compliance. It demonstrates modern Python development practices with async processing, containerization, and AI-powered data extraction. The S3 integration is well-implemented with proper error handling, SSL support, and connection management, though it could benefit from streaming support for large files and enhanced security measures.
