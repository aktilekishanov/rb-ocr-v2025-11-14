# Kafka + S3 Integration Approach - Evaluation

**Date**: 2024-12-04  
**Status**: Pre-Implementation Review

---

## TL;DR

✅ **Overall Assessment**: **GOOD APPROACH** with some recommended improvements  
⭐ **Rating**: 7/10 (solid foundation, needs architectural refinements)

**Key Strengths**:
- Incremental testing strategy
- Separation of concerns (manual vs Kafka endpoint)
- Working S3 connectivity proven

**Key Improvements Needed**:
- Add database persistence earlier
- Implement proper async S3 operations
- Add retry and error handling mechanisms
- Consider filesystem storage strategy

---

## Detailed Evaluation

### 1. Architecture Analysis

#### ✅ **What Works Well**

##### 1.1 Incremental Testing Strategy
```
✓ Test S3 connectivity first ✓ DONE
→ Create Kafka-compatible endpoint → NEXT
→ Test without actual Kafka
→ Integrate with real Kafka later
```

**Why Good**: 
- Reduces integration risk
- Allows parallel development
- Each component can be tested independently
- Matches agile/iterative methodology

##### 1.2 Endpoint Separation
Your plan to keep both endpoints:
- `/v1/verify` (existing, manual file upload)
- `/v1/kafka-verify` (new, accepts Kafka event body)

**Why Good**:
- Maintains backward compatibility
- Allows A/B testing
- Facilitates gradual migration
- Keeps manual testing capability

##### 1.3 S3 Connectivity Proven
- Successfully connected to `s3-dev.fortebank.com`
- Tested download with Cyrillic/Kazakh filenames
- Verified file integrity with MD5 hashing

**Why Good**: De-risks the critical path

---

### 2. Concerns & Improvements

#### ⚠️ **CONCERN 1: Database Integration Timing**

**Your Current Plan**:
```
Receive event → Store in DB → Download from S3 → Process
```

**Issue**: You mentioned "store somehow in db" very vaguely

**Recommendation**: ✅ **Define database schema NOW, not later**

**Why Critical**:
- Database design affects API contract
- Need to track request lifecycle (received, processing, completed, failed)
- Kafka events should be idempotent (handle duplicates)
- Need audit trail for compliance

**Proposed Database Schema**:

```sql
-- Requests table
CREATE TABLE ocr_requests (
    id SERIAL PRIMARY KEY,
    request_id BIGINT UNIQUE NOT NULL,  -- From Kafka event
    s3_path VARCHAR(500) NOT NULL,
    iin VARCHAR(12) NOT NULL,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    second_name VARCHAR(100),
    
    -- Processing status
    status VARCHAR(50) NOT NULL,  -- 'received', 'downloading', 'processing', 'completed', 'failed'
    run_id VARCHAR(36),  -- Links to existing run system
    
    -- Results
    verdict BOOLEAN,
    errors JSONB,
    
    -- Timestamps
    received_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    
    -- Metadata
    processing_time_seconds DECIMAL(10, 2),
    error_message TEXT,
    retry_count INTEGER DEFAULT 0
);

CREATE INDEX idx_request_id ON ocr_requests(request_id);
CREATE INDEX idx_status ON ocr_requests(status);
CREATE INDEX idx_iin ON ocr_requests(iin);
```

---

#### ⚠️ **CONCERN 2: S3 Download Strategy**

**Your Plan**: "downloaded it somehow (might be tmp or local storage)"

**Issue**: Too vague for production

**Recommendation**: ✅ **Choose explicit storage strategy**

**Option A**: Temporary Files (Recommended for start)
```python
# Pros: Simple, auto-cleanup
# Cons: Doesn't survive crashes

import tempfile
import os

# Download to temp
# Determine file extension from S3 path
file_ext = os.path.splitext(s3_path)[1] or '.bin'  # .pdf, .jpg, .png, etc.
with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
    s3_client.download_file(bucket, s3_path, tmp.name)
    local_path = tmp.name

try:
    # Process file
    result = process_document(local_path, ...)
finally:
    # Clean up
    os.unlink(local_path)
```

**Option B**: Persistent Storage with Cleanup
```python
# Pros: Can resume after crash, better debugging
# Cons: Need cleanup job

downloads_dir = "/app/downloads"
local_path = f"{downloads_dir}/{request_id}_{filename}"

# Download
s3_client.download_file(bucket, s3_path, local_path)

try:
    # Process
    result = process_document(local_path, ...)
finally:
    # Cleanup after processing (or keep for X hours)
    cleanup_after_hours(local_path, hours=24)
```

**My Recommendation**: Start with Option A (temp files), migrate to Option B if needed

---

#### ⚠️ **CONCERN 3: Async/Await for S3 Operations**

**Current S3 Script**: Synchronous (blocking)
```python
# Current (blocks FastAPI event loop)
response = client.get_object(bucket, key)
data = response.read()  # BLOCKS!
```

**Recommendation**: ✅ **Use async S3 client**

**Why Critical**: Your FastAPI endpoint is `async`, but S3 operations are blocking

**Solution**: Use `aioboto3` or run blocking I/O in executor

```python
# Option 1: aioboto3 (proper async)
import aioboto3

async def download_from_s3(bucket: str, key: str) -> bytes:
    session = aioboto3.Session()
    async with session.client('s3', ...) as s3:
        response = await s3.get_object(Bucket=bucket, Key=key)
        async with response['Body'] as stream:
            return await stream.read()

# Option 2: Run blocking in executor
from concurrent.futures import ThreadPoolExecutor
import asyncio

executor = ThreadPoolExecutor(max_workers=4)

async def download_from_s3_sync(bucket: str, key: str) -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        executor, 
        _sync_download,  # Your current MinIO client code
        bucket, 
        key
    )
```

---

#### ⚠️ **CONCERN 4: Error Handling & Retries**

**Your Plan**: Not mentioned

**Recommendation**: ✅ **Implement robust error handling**

**Typical Failures**:
1. S3 file not found (`NoSuchKey`)
2. S3 network timeout
3. File is not a valid document format (unsupported PDF or image type)
4. Processing pipeline fails

**Recommended Strategy**:

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def download_with_retry(bucket: str, key: str):
    try:
        return await download_from_s3(bucket, key)
    except S3Error as e:
        if e.code == "NoSuchKey":
            # Don't retry - file doesn't exist
            raise FileNotFoundError(f"File not found in S3: {key}")
        # Retry on other S3 errors
        raise

async def process_kafka_event(event: KafkaEvent):
    try:
        # 1. Store event in DB
        db_record = await save_event_to_db(event)
        
        # 2. Download from S3
        await update_status(db_record.id, "downloading")
        file_data = await download_with_retry(S3_BUCKET, event.s3_path)
        
        # 3. Process
        await update_status(db_record.id, "processing")
        result = await process_document(file_data, event.fio)
        
        # 4. Save result
        await update_status(db_record.id, "completed", result=result)
        return result
        
    except FileNotFoundError as e:
        await update_status(db_record.id, "failed", error=str(e))
        raise HTTPException(404, detail=str(e))
    
    except Exception as e:
        await update_status(db_record.id, "failed", error=str(e))
        logger.error(f"Processing failed for request {event.request_id}: {e}")
        raise HTTPException(500, detail="Processing failed")
```

---

#### ⚠️ **CONCERN 5: Kafka Event Idempotency**

**Scenario**: What if Kafka delivers the same event twice?

**Recommendation**: ✅ **Use `request_id` as idempotency key**

```python
async def process_kafka_event(event: KafkaEvent):
    # Check if already processed
    existing = await db.get_request_by_id(event.request_id)
    
    if existing:
        if existing.status == "completed":
            logger.info(f"Request {event.request_id} already completed")
            return existing.result  # Return cached result
        
        elif existing.status == "processing":
            logger.warning(f"Request {event.request_id} already processing")
            raise HTTPException(409, "Already processing")
        
        elif existing.status == "failed" and existing.retry_count < 3:
            logger.info(f"Retrying failed request {event.request_id}")
            # Continue processing
        else:
            raise HTTPException(400, "Max retries exceeded")
    
    # Process new request
    ...
```

---

### 3. Proposed Endpoint Design

#### Recommended API Contract

```python
from pydantic import BaseModel, Field

class KafkaEventRequest(BaseModel):
    """Incoming Kafka event body"""
    request_id: int = Field(..., description="Unique request ID from Kafka")
    s3_path: str = Field(..., description="S3 object key (path to file)")
    iin: str = Field(..., description="Individual Identification Number")
    first_name: str = Field(..., description="Applicant first name")
    last_name: str = Field(..., description="Applicant last name")
    second_name: str = Field(..., description="Applicant patronymic name")
    
    @property
    def fio(self) -> str:
        """Construct FIO from components"""
        return f"{self.last_name} {self.first_name} {self.second_name}"

class KafkaEventResponse(BaseModel):
    """Response for Kafka event processing"""
    request_id: int
    status: str  # "received", "processing", "completed", "failed"
    run_id: str | None = None
    verdict: bool | None = None
    errors: list[str] = []
    processing_time_seconds: float | None = None
    message: str = "Request received and queued for processing"
```

#### Endpoint Implementation

```python
@app.post("/v1/kafka-verify", response_model=KafkaEventResponse)
async def verify_from_kafka(event: KafkaEventRequest):
    """
    Process document verification from Kafka event.
    
    This endpoint:
    1. Stores the event in database
    2. Downloads file from S3 using event.s3_path
    3. Processes the document
    4. Returns verification result
    """
    logger.info(f"[KAFKA EVENT] request_id={event.request_id}, s3_path={event.s3_path}")
    
    try:
        # Check idempotency
        existing = await check_existing_request(event.request_id)
        if existing:
            return existing  # Return cached result
        
        # Store event
        db_record = await store_event(event)
        
        # Download from S3
        logger.info(f"[S3 DOWNLOAD] Fetching {event.s3_path}")
        file_data = await download_from_s3(S3_BUCKET, event.s3_path)
        
        # Save to temp file
        # Determine file extension from S3 path
        file_ext = os.path.splitext(event.s3_path)[1] or '.bin'
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            tmp.write(file_data)
            tmp_path = tmp.name
        
        try:
            # Process document (reuse existing pipeline)
            result = await processor.process_document(
                file_path=tmp_path,
                original_filename=event.s3_path.split('/')[-1],  # Extract filename
                fio=event.fio,
            )
            
            # Update database
            await update_request_result(
                request_id=event.request_id,
                run_id=result["run_id"],
                verdict=result["verdict"],
                errors=result["errors"],
            )
            
            return KafkaEventResponse(
                request_id=event.request_id,
                status="completed",
                run_id=result["run_id"],
                verdict=result["verdict"],
                errors=result["errors"],
                message="Processing completed successfully"
            )
            
        finally:
            os.unlink(tmp_path)
    
    except FileNotFoundError:
        await mark_request_failed(event.request_id, "File not found in S3")
        raise HTTPException(404, detail=f"File not found: {event.s3_path}")
    
    except Exception as e:
        await mark_request_failed(event.request_id, str(e))
        logger.error(f"[ERROR] request_id={event.request_id}: {e}", exc_info=True)
        raise HTTPException(500, detail="Processing failed")
```

---

### 4. Testing Strategy

#### Phase 1: Unit Testing (Current)
```bash
# Test S3 connectivity ✓ DONE
python tests/s3-test/test_s3_connection.py
```

#### Phase 2: API Testing (Next)
```bash
# Test new endpoint with mock Kafka event
curl -X POST http://localhost:8000/v1/kafka-verify \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": 1234567,
    "s3_path": "Приказ о выходе в декретный отпуск - Жармағанбет.pdf",
    "iin": "960125000000",
    "first_name": "Иван",
    "last_name": "Иванов",
    "second_name": "Иванович"
  }'
```

#### Phase 3: Integration Testing
1. Set up local Kafka (Docker Compose)
2. Publish test events
3. Verify end-to-end flow

#### Phase 4: Production
1. Connect to real Kafka brokers (`10.0.94.86-88:9092`)
2. Monitor with health checks
3. Set up alerts

---

### 5. Implementation Checklist

#### Immediate (Before Coding)
- [ ] Define database schema
- [ ] Choose S3 download strategy (temp vs persistent)
- [ ] Decide on async library (`aioboto3` recommended)

#### Phase 1: Core Functionality
- [ ] Create S3 client wrapper (async)
- [ ] Implement database models
- [ ] Create `/v1/kafka-verify` endpoint
- [ ] Add request_id deduplication

#### Phase 2: Robustness
- [ ] Add retry logic for S3 downloads
- [ ] Implement error handling
- [ ] Add logging and monitoring
- [ ] Create health check for S3 connectivity

#### Phase 3: Testing
- [ ] Unit tests for S3 download
- [ ] Integration tests for endpoint
- [ ] Load testing with multiple events
- [ ] Test idempotency (duplicate events)

#### Phase 4: Kafka Integration
- [ ] Set up Kafka consumer
- [ ] Configure group ID (`nohd_MSB`)
- [ ] Test with real Kafka topic
- [ ] Monitor offset commits

---

### 6. Architecture Diagram

```
┌─────────────┐         ┌──────────────────┐
│ Mobile App  │────────→│ Kafka Topic      │
└─────────────┘         │ dl-loan-delay... │
                        └────────┬─────────┘
                                 │
                                 ↓
                        ┌─────────────────┐
                        │ Your Service    │
                        │ (Kafka Consumer)│
                        └────────┬────────┘
                                 │
                 ┌───────────────┼───────────────┐
                 │               │               │
                 ↓               ↓               ↓
         ┌─────────────┐ ┌─────────────┐ ┌────────────┐
         │ Database    │ │ S3 (MinIO)  │ │ FastAPI    │
         │ (Save Event)│ │ (Download)  │ │ /v1/verify │
         └─────────────┘ └─────────────┘ └─────┬──────┘
                                               │
                                               ↓
                                        ┌──────────────┐
                                        │ OCR Pipeline │
                                        │ (Process)    │
                                        └──────┬───────┘
                                               │
                                               ↓
                                        ┌──────────────┐
                                        │ Save Results │
                                        │ to Database  │
                                        └──────────────┘
```

---

### 7. Risk Assessment

#### HIGH RISK ⚠️
1. **S3 file not found**: Event references non-existent file
   - **Mitigation**: Proper error handling, notify upstream
2. **Database connection**: DB down during processing
   - **Mitigation**: Connection pooling, retries, health checks

#### MEDIUM RISK ⚙️
1. **Kafka duplicate events**: Same event processed twice
   - **Mitigation**: Idempotency via `request_id`
2. **S3 network issues**: Timeout or connection failure
   - **Mitigation**: Retry logic with exponential backoff

#### LOW RISK ✅
1. **File format issues**: S3 file is corrupted or unsupported format (non-PDF/image)
   - **Mitigation**: Already handled by existing pipeline error handling

---

### 8. Final Recommendations

#### 🎯 **DO THIS**:
1. ✅ Design database schema before writing code
2. ✅ Use async S3 client (`aioboto3`)
3. ✅ Implement idempotency checks
4. ✅ Add comprehensive logging
5. ✅ Test with mock events first
6. ✅ Keep both endpoints (`/v1/verify` and `/v1/kafka-verify`)

#### ❌ **AVOID THIS**:
1. ❌ Don't mix sync and async code (breaks FastAPI)
2. ❌ Don't skip database persistence
3. ❌ Don't ignore duplicate event handling
4. ❌ Don't hard-code S3 credentials (use env vars)
5. ❌ Don't process without logging the request first

#### 📋 **OPTIONAL BUT RECOMMENDED**:
1. Add metrics (Prometheus)
2. Add distributed tracing (Jaeger)
3. Implement circuit breaker for S3
4. Add rate limiting
5. Create admin dashboard to view requests

---

## Conclusion

### Overall Grade: **7/10** 

**Strengths** ⭐⭐⭐⭐:
- Solid incremental approach
- Good separation of concerns
- S3 connectivity proven

**Needs Improvement** ⚠⚠:
- Database integration vague
- Async handling not considered
- Error handling undefined
- No idempotency strategy

### Next Steps

1. **Day 1**: Define database schema and models
2. **Day 2**: Implement async S3 client wrapper
3. **Day 3**: Create `/v1/kafka-verify` endpoint with DB integration
4. **Day 4**: Add error handling and retries
5. **Day 5**: Test with mock Kafka events
6. **Week 2**: Kafka consumer integration

---

**Your approach is fundamentally sound.** With the improvements outlined above, you'll have a production-ready system. The key is to not rush the database design and error handling - these are critical for reliability.

Good luck! 🚀
