# Kafka Event Endpoint Implementation Plan

## 1. Overview

This document provides a comprehensive step-by-step plan to create a new FastAPI endpoint that processes Kafka events containing document information and S3 file references. The endpoint will download files from S3, run the existing pipeline, and return the same response format as the current `/v1/verify` endpoint.

---

## 2. Event Body Specification

The incoming Kafka event has the following structure:

```json
{
    "request_id": 123123,
    "s3_path": "some_s3_address",
    "iin": 960125000000,
    "first_name": "Иван",
    "last_name": "Иванов",
    "second_name": "Иванович"
}
```

**Field Descriptions:**
- `request_id` (int): Unique identifier for the request
- `s3_path` (str): S3 object key/path to the document file
- `iin` (int): Individual Identification Number (12 digits)
- `first_name` (str): Applicant's first name (Cyrillic)
- `last_name` (str): Applicant's last name (Cyrillic)
- `second_name` (str, optional): Applicant's patronymic/middle name (Cyrillic)

---

## 3. Endpoint Requirements

### 3.1 Core Functionality

1. **Accept Kafka Event Body**: Receive the JSON payload via HTTP POST
2. **Store Event Body**: Save the incoming event as a `.json` file for audit/traceability
3. **Construct FIO**: Build the Full Name string from `last_name + first_name + second_name` (if available)
4. **Download from S3**: Retrieve the document file from MinIO using the `s3_path`
5. **Store File Locally**: Save the downloaded file temporarily for processing
6. **Run Pipeline**: Execute the existing `run_pipeline()` function with the file and FIO
7. **Return Response**: Return the exact same response structure as `/v1/verify` endpoint

### 3.2 Response Format

The endpoint must return a `VerifyResponse` object:

```json
{
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "verdict": true,
    "errors": [],
    "processing_time_seconds": 12.4
}
```

---

## 4. Implementation Steps

### Step 1: Create Pydantic Request Schema

**File**: `fastapi-service/api/schemas.py`

**Action**: Add a new request schema for the Kafka event body.

**Code to Add**:

```python
class KafkaEventRequest(BaseModel):
    """Request schema for Kafka event processing endpoint."""
    request_id: int = Field(..., description="Unique request identifier from Kafka event")
    s3_path: str = Field(..., description="S3 object key/path to the document")
    iin: int = Field(..., description="Individual Identification Number (12 digits)")
    first_name: str = Field(..., description="Applicant's first name")
    last_name: str = Field(..., description="Applicant's last name")
    second_name: str | None = Field(None, description="Applicant's patronymic/middle name (optional)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "request_id": 123123,
                "s3_path": "documents/2024/sample.pdf",
                "iin": 960125000000,
                "first_name": "Иван",
                "last_name": "Иванов",
                "second_name": "Иванович"
            }
        }
```

**Rationale**: This schema validates the incoming Kafka event structure and provides API documentation via OpenAPI/Swagger.

---

### Step 2: Create S3 Service Client

**File**: `fastapi-service/services/s3_client.py` (NEW FILE)

**Action**: Create a reusable S3 client service for downloading files from MinIO.

**Code to Create**:

```python
"""MinIO S3 client for downloading documents."""
import ssl
import urllib3
import logging
from pathlib import Path
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class S3Client:
    """Client for interacting with MinIO S3 storage."""
    
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = True,
    ):
        """
        Initialize S3 client.
        
        Args:
            endpoint: S3 endpoint (e.g., "s3-dev.fortebank.com:9443")
            access_key: S3 access key
            secret_key: S3 secret key
            bucket: S3 bucket name
            secure: Use HTTPS (default: True)
        """
        self.bucket = bucket
        self.endpoint = endpoint
        
        # Create HTTP client with SSL configuration
        http_client = urllib3.PoolManager(
            cert_reqs=ssl.CERT_NONE,
            assert_hostname=False
        )
        
        # Initialize MinIO client
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region="random-region",
            http_client=http_client
        )
        
        logger.info(f"S3Client initialized: endpoint={endpoint}, bucket={bucket}")
    
    def download_file(self, object_key: str, destination_path: str) -> dict:
        """
        Download a file from S3.
        
        Args:
            object_key: S3 object key/path
            destination_path: Local file path to save the downloaded file
            
        Returns:
            dict with metadata: {
                "size": int,
                "content_type": str,
                "etag": str,
                "local_path": str
            }
            
        Raises:
            S3Error: If file not found or download fails
            Exception: For other errors
        """
        try:
            # Get object metadata
            stat = self.client.stat_object(self.bucket, object_key)
            logger.info(
                f"Found S3 object: key={object_key}, "
                f"size={stat.size} bytes, content_type={stat.content_type}"
            )
            
            # Download file
            response = self.client.get_object(self.bucket, object_key)
            file_data = response.read()
            response.close()
            response.release_conn()
            
            # Save to local file
            Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
            with open(destination_path, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"Downloaded S3 file to: {destination_path}")
            
            return {
                "size": len(file_data),
                "content_type": stat.content_type,
                "etag": stat.etag,
                "local_path": destination_path,
            }
            
        except S3Error as e:
            logger.error(f"S3 error downloading {object_key}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error downloading {object_key}: {e}")
            raise
```

**Rationale**: Encapsulates S3 operations, reuses the working S3 connection logic from `test_s3_connection.py`, and provides proper error handling.

---

### Step 3: Create S3 Configuration

**File**: `fastapi-service/pipeline/core/config.py` (NEW FILE)

**Action**: Add hardcoded S3 configuration constants.

**Code to Create**:

```python
"""Configuration for S3 and other external services."""

class S3Config:
    """S3/MinIO hardcoded configuration for DEV."""
    
    ENDPOINT: str = "s3-dev.fortebank.com:9443"
    ACCESS_KEY: str = "fyz13d2czRW7l4sBW8gD"
    SECRET_KEY: str = "1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A"
    BUCKET: str = "loan-statements-dev"
    SECURE: bool = True


# Export singleton config
s3_config = S3Config()
```

**Rationale**: 
- Simple hardcoded configuration for DEV environment
- Can be updated directly in code when needed
- No need for environment variable management

---

### Step 4: Add FIO Builder Utility Function

**File**: `fastapi-service/pipeline/utils/io_utils.py`

**Action**: Add a utility function to build FIO from name components.

**Code to Add**:

```python
def build_fio(last_name: str, first_name: str, second_name: str | None = None) -> str:
    """
    Build Full Name (FIO) from components.
    
    Args:
        last_name: Last name (фамилия)
        first_name: First name (имя)
        second_name: Patronymic/middle name (отчество), optional
        
    Returns:
        Full name string, e.g., "Иванов Иван Иванович" or "Иванов Иван"
        
    Example:
        >>> build_fio("Иванов", "Иван", "Иванович")
        "Иванов Иван Иванович"
        >>> build_fio("Петров", "Петр", None)
        "Петров Петр"
    """
    components = [last_name.strip(), first_name.strip()]
    if second_name and second_name.strip():
        components.append(second_name.strip())
    return " ".join(components)
```

**Rationale**: 
- Centralizes FIO construction logic
- Handles optional `second_name` field
- Strips whitespace for consistent formatting

---

### Step 5: Extend DocumentProcessor for Kafka Events

**File**: `fastapi-service/services/processor.py`

**Action**: Add a new method to process Kafka events.

**Code to Add**:

```python
import json
from pathlib import Path
from pipeline.utils.io_utils import build_fio, write_json
from services.s3_client import S3Client
from pipeline.core.config import s3_config


class DocumentProcessor:
    """Processes documents through the RB-OCR pipeline."""
    
    def __init__(self, runs_root: str = "./runs"):
        self.runs_root = Path(runs_root)
        self.runs_root.mkdir(parents=True, exist_ok=True)
        
        # Initialize S3 client
        self.s3_client = S3Client(
            endpoint=s3_config.ENDPOINT,
            access_key=s3_config.ACCESS_KEY,
            secret_key=s3_config.SECRET_KEY,
            bucket=s3_config.BUCKET,
            secure=s3_config.SECURE,
        )
        
        logger.info(f"DocumentProcessor initialized. runs_root={self.runs_root}")
    
    # ... existing process_document method ...
    
    async def process_kafka_event(
        self,
        event_data: dict,
    ) -> dict:
        """
        Process a Kafka event containing S3 file reference.
        
        Args:
            event_data: Kafka event body as dict
            
        Returns:
            dict with run_id, verdict, errors
            
        Raises:
            Exception: If S3 download or pipeline processing fails
        """
        request_id = event_data["request_id"]
        s3_path = event_data["s3_path"]
        
        logger.info(f"Processing Kafka event: request_id={request_id}, s3_path={s3_path}")
        
        # 1. Store event body as JSON for audit trail
        event_storage_dir = self.runs_root / "kafka_events"
        event_storage_dir.mkdir(parents=True, exist_ok=True)
        event_file_path = event_storage_dir / f"event_{request_id}_{int(time.time())}.json"
        
        write_json(event_data, str(event_file_path))
        logger.info(f"Stored event body: {event_file_path}")
        
        # 2. Build FIO from name components
        fio = build_fio(
            last_name=event_data["last_name"],
            first_name=event_data["first_name"],
            second_name=event_data.get("second_name"),
        )
        logger.info(f"Built FIO: {fio}")
        
        # 3. Download file from S3
        # Generate temporary local path
        import tempfile
        import os
        
        # Extract filename from s3_path or use default
        filename = os.path.basename(s3_path) or f"document_{request_id}.pdf"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{filename}") as tmp:
            tmp_path = tmp.name
        
        try:
            # Download from S3
            loop = asyncio.get_event_loop()
            s3_metadata = await loop.run_in_executor(
                None,
                lambda: self.s3_client.download_file(s3_path, tmp_path)
            )
            
            logger.info(f"Downloaded from S3: {s3_path} -> {tmp_path} ({s3_metadata['size']} bytes)")
            
            # 4. Run pipeline
            result = await self.process_document(
                file_path=tmp_path,
                original_filename=filename,
                fio=fio,
            )
            
            logger.info(f"Pipeline complete for Kafka event. run_id={result.get('run_id')}, verdict={result.get('verdict')}")
            
            return result
            
        finally:
            # Cleanup temporary file
            try:
                os.unlink(tmp_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {tmp_path}: {e}")
```

**Rationale**:
- Reuses existing `process_document()` method for pipeline execution
- Stores event body for audit trail and debugging
- Downloads file from S3 using async executor pattern
- Handles cleanup properly with try/finally
- Returns the same response format as `/v1/verify`

---

### Step 6: Create New Endpoint in main.py

**File**: `fastapi-service/main.py`

**Action**: Add the new `/v1/kafka/verify` endpoint.

**Code to Add**:

```python
from api.schemas import VerifyResponse, KafkaEventRequest


@app.post("/v1/kafka/verify", response_model=VerifyResponse)
async def verify_kafka_event(
    event: KafkaEventRequest,
):
    """
    Process a Kafka event for document verification.
    
    This endpoint:
    1. Receives the Kafka event body with S3 file reference
    2. Stores the event as JSON for audit trail
    3. Builds FIO from name components (last_name + first_name + second_name)
    4. Downloads the document from S3
    5. Runs the verification pipeline
    6. Returns the same response format as /v1/verify
    
    Args:
        event: Kafka event body containing request_id, s3_path, iin, and name fields
        
    Returns:
        VerifyResponse with run_id, verdict, errors, and processing_time_seconds
        
    Raises:
        HTTPException: 500 if S3 download or pipeline processing fails
    """
    start_time = time.time()
    logger.info(
        f"[NEW KAFKA EVENT] request_id={event.request_id}, "
        f"s3_path={event.s3_path}, iin={event.iin}"
    )
    
    try:
        # Process Kafka event (downloads from S3 and runs pipeline)
        result = await processor.process_kafka_event(
            event_data=event.dict(),
        )
        
        processing_time = time.time() - start_time
        
        response = VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],
            processing_time_seconds=round(processing_time, 2),
        )
        
        logger.info(
            f"[KAFKA RESPONSE] request_id={event.request_id}, "
            f"run_id={response.run_id}, verdict={response.verdict}, "
            f"time={response.processing_time_seconds}s"
        )
        return response
    
    except S3Error as e:
        logger.error(f"[S3 ERROR] request_id={event.request_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"S3 download error: {e.code} - {e.message}"
        )
    
    except Exception as e:
        logger.error(
            f"[ERROR] request_id={event.request_id}: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Internal processing error: {str(e)}"
        )
```

**Note**: Add import for `S3Error`:
```python
from minio.error import S3Error
```

**Rationale**:
- Clear separation from `/v1/verify` endpoint
- Comprehensive logging with request_id for traceability
- Specific error handling for S3 errors vs general errors
- Same response format as existing endpoint

---

### Step 7: Update Dependencies

**File**: `fastapi-service/requirements.txt`

**Action**: Ensure `minio` library is included.

**Check if present, if not add**:
```
minio>=7.2.0
```

**Rationale**: MinIO client library is required for S3 operations.

---

### Step 8: Docker Configuration

**No changes needed** - S3 configuration is hardcoded in `config.py`.

**Note**: If you need different S3 credentials for production in the future, update the values directly in `pipeline/core/config.py`.

---

## 5. File Structure Summary

After implementation, the following files will be created/modified:

```
fastapi-service/
├── api/
│   └── schemas.py                 [MODIFIED] - Add KafkaEventRequest
├── services/
│   ├── processor.py               [MODIFIED] - Add process_kafka_event method
│   └── s3_client.py               [NEW] - S3 client service
├── pipeline/
│   ├── core/
│   │   └── config.py              [NEW] - S3 configuration
│   └── utils/
│       └── io_utils.py            [MODIFIED] - Add build_fio function
├── main.py                        [MODIFIED] - Add /v1/kafka/verify endpoint
└── requirements.txt               [CHECK] - Ensure minio library is present
```

---

## 6. Testing Strategy

### 6.1 Unit Tests

Create `fastapi-service/tests/test_kafka_endpoint.py`:

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_kafka_event_request_schema():
    """Test KafkaEventRequest validation."""
    from api.schemas import KafkaEventRequest
    
    # Valid request
    valid_data = {
        "request_id": 123123,
        "s3_path": "documents/test.pdf",
        "iin": 960125000000,
        "first_name": "Иван",
        "last_name": "Иванов",
        "second_name": "Иванович"
    }
    event = KafkaEventRequest(**valid_data)
    assert event.request_id == 123123
    assert event.second_name == "Иванович"
    
    # Valid request without second_name
    valid_data_no_patronymic = {
        "request_id": 123124,
        "s3_path": "documents/test2.pdf",
        "iin": 960125000001,
        "first_name": "Петр",
        "last_name": "Петров"
    }
    event2 = KafkaEventRequest(**valid_data_no_patronymic)
    assert event2.second_name is None


def test_build_fio():
    """Test FIO construction."""
    from pipeline.utils.io_utils import build_fio
    
    # With patronymic
    fio1 = build_fio("Иванов", "Иван", "Иванович")
    assert fio1 == "Иванов Иван Иванович"
    
    # Without patronymic
    fio2 = build_fio("Петров", "Петр", None)
    assert fio2 == "Петров Петр"
    
    # With empty patronymic
    fio3 = build_fio("Сидоров", "Сидор", "")
    assert fio3 == "Сидоров Сидор"


@pytest.mark.asyncio
async def test_s3_client_initialization():
    """Test S3Client can be initialized."""
    from services.s3_client import S3Client
    
    client = S3Client(
        endpoint="s3-dev.fortebank.com:9443",
        access_key="test_key",
        secret_key="test_secret",
        bucket="test-bucket",
        secure=True
    )
    
    assert client.bucket == "test-bucket"
    assert client.endpoint == "s3-dev.fortebank.com:9443"
```

### 6.2 Integration Tests

**Test with actual S3 file** (requires S3 access):

```python
@pytest.mark.integration
def test_kafka_endpoint_with_s3():
    """Test full Kafka endpoint flow with S3 download."""
    
    payload = {
        "request_id": 999999,
        "s3_path": "Приказ о выходе в декретный отпуск - Жармағанбет.pdf",
        "iin": 960125000000,
        "first_name": "Иван",
        "last_name": "Иванов",
        "second_name": "Иванович"
    }
    
    response = client.post("/v1/kafka/verify", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    
    assert "run_id" in data
    assert "verdict" in data
    assert "errors" in data
    assert "processing_time_seconds" in data
    assert isinstance(data["verdict"], bool)
```

### 6.3 Manual Testing

1. **Start the FastAPI service** locally or in Docker
2. **Use Swagger UI** at `http://localhost:8000/docs`
3. **Send test request** to `/v1/kafka/verify`:

```json
{
  "request_id": 123123,
  "s3_path": "Приказ о выходе в декретный отпуск - Жармағанбет.pdf",
  "iin": 960125000000,
  "first_name": "Иван",
  "last_name": "Иванов",
  "second_name": "Иванович"
}
```

4. **Verify**:
   - Event JSON is saved in `runs/kafka_events/`
   - File is downloaded from S3
   - Pipeline runs successfully
   - Response matches VerifyResponse schema

---

## 7. Error Handling

The implementation handles the following error scenarios:

| Error Type | HTTP Code | Response |
|------------|-----------|----------|
| Invalid request schema | 422 | Pydantic validation error |
| S3 file not found | 500 | "S3 download error: NoSuchKey" |
| S3 connection failure | 500 | "S3 download error: [error details]" |
| Pipeline processing error | 500 | "Internal processing error: [error details]" |
| Invalid FIO format | 400 | Validation error from schema |

All errors are logged with full context including `request_id` for debugging.

---

## 8. Deployment Checklist

- [ ] Add all new files to version control
- [ ] Update `requirements.txt` with `minio` library if not present
- [ ] Create `runs/kafka_events/` directory with proper permissions
- [ ] Test S3 connectivity from deployment environment
- [ ] Verify network access to MinIO endpoint (port 9443)
- [ ] Run unit tests
- [ ] Run integration tests with real S3 files
- [ ] Update API documentation
- [ ] Smoke test the endpoint in staging environment

---

## 9. Security Considerations

1. **S3 Credentials**: Currently hardcoded in `config.py` for DEV environment - protect the codebase appropriately
2. **File Cleanup**: Temporary files are deleted after processing
3. **Input Validation**: Pydantic schemas validate all inputs
4. **S3 Path Validation**: Consider adding path validation to prevent directory traversal
5. **Rate Limiting**: Consider adding rate limiting for this endpoint
6. **Audit Trail**: All events are stored with timestamps for compliance

> **Note**: For production, consider moving credentials to environment variables or a secrets manager.

---

## 10. Performance Considerations

1. **Async Operations**: S3 download runs in executor to avoid blocking
2. **File Size Limits**: Consider adding max file size validation
3. **Timeout Configuration**: Set appropriate timeouts for S3 operations
4. **Connection Pooling**: MinIO client uses connection pooling by default
5. **Temporary Storage**: Monitor disk space in `runs/` directory

---

## 11. Future Enhancements

1. **Kafka Consumer**: Eventually replace HTTP endpoint with direct Kafka consumer
2. **Database Integration**: Store event metadata and results in PostgreSQL
3. **Notification Service**: Send results back to loan-api after processing
4. **Retry Mechanism**: Add retry logic for transient S3 failures
5. **Metrics**: Add Prometheus metrics for monitoring
6. **Dead Letter Queue**: Handle failed events with DLQ

---

## 12. API Documentation Example

After implementation, the Swagger UI will show:

**Endpoint**: `POST /v1/kafka/verify`

**Request Body**:
```json
{
  "request_id": 123123,
  "s3_path": "documents/2024/sample.pdf",
  "iin": 960125000000,
  "first_name": "Иван",
  "last_name": "Иванов",
  "second_name": "Иванович"
}
```

**Response** (200 OK):
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "verdict": true,
  "errors": [],
  "processing_time_seconds": 15.42
}
```

**Response** (500 Internal Server Error):
```json
{
  "detail": "S3 download error: NoSuchKey - The specified key does not exist"
}
```

---

## 13. Summary

This implementation plan provides a complete solution for processing Kafka events in the FastAPI service. The new endpoint:

✅ Accepts Kafka event body with S3 file reference  
✅ Stores event as JSON for audit trail  
✅ Constructs FIO from name components  
✅ Downloads file from MinIO S3  
✅ Runs the existing pipeline  
✅ Returns the same response as `/v1/verify`  
✅ Includes comprehensive error handling  
✅ Follows existing code patterns and architecture  
✅ Is fully testable and production-ready  

**Estimated Implementation Time**: 4-6 hours for a senior backend engineer

**Files to Create**: 2 new files  
**Files to Modify**: 4 existing files  
**Dependencies to Add**: 1 (minio, if not already present)
