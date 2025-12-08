# Kafka Consumer Integration Guide
## How to Consume RB-OCR API Responses

**Audience**: Backend Team Building Kafka Consumer  
**Purpose**: Standardized REST API integration pattern  
**Version**: 1.0  
**Date**: 2025-12-08

---

## Executive Summary

This guide defines the **correct** way to consume RB-OCR document verification API responses. Following these patterns ensures:
- ✅ Type-safe response handling
- ✅ Proper error handling and retries
- ✅ Standard REST API practices
- ✅ Maintainable, debuggable code

**Key Principle**: HTTP status codes determine response schema and handling logic.

---

## API Contract Overview

### Endpoint
```
POST /rb-ocr/api/v1/kafka/verify
```

### Request Body
```json
{
    "request_id": 123123,
    "s3_path": "documents/2024/sample.pdf",
    "iin": "021223504060",
    "first_name": "Иван",
    "last_name": "Иванов",
    "second_name": "Иванович"
}
```

### Response Types by HTTP Status

| HTTP Status | Response Schema | Meaning | Your Action |
|-------------|-----------------|---------|-------------|
| **200 OK** | `SuccessResponse` | Request processed (document may pass or fail validation) | Process result |
| **422 Unprocessable Entity** | `ErrorResponse` | Invalid request data | Log error, don't retry |
| **404 Not Found** | `ErrorResponse` | S3 file not found | Log error, don't retry |
| **502 Bad Gateway** | `ErrorResponse` | External service failure (OCR/LLM/S3) | Retry with backoff |
| **500 Internal Server Error** | `ErrorResponse` | Unexpected server error | Retry with backoff |

---

## Response Schemas

### HTTP 200: Success Response

**Use when:** Request was successfully processed (document verified, regardless of outcome)

```json
{
    "request_id": 123123,
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "verdict": true,
    "errors": [],
    "processing_time_seconds": 4.2,
    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Fields:**
- `request_id` (integer): Your original Kafka event request ID
- `run_id` (string): Unique pipeline execution ID for database queries
- `verdict` (boolean): **true** = document passed all checks, **false** = document failed validation
- `errors` (array[string]): Business validation error codes (empty if verdict=true)
- `processing_time_seconds` (float): Total processing time
- `trace_id` (string): Request correlation ID for log tracing

**Possible error codes** (when verdict=false):
- `FIO_MISMATCH` - Name doesn't match
- `DOC_DATE_TOO_OLD` - Document expired
- `DOC_DATE_MISSING` - Date not found
- `DOC_TYPE_UNKNOWN` - Document type not recognized
- `FIO_MISSING` - Name not found in document
- `MULTIPLE_DOCUMENTS` - File contains multiple document types

---

### HTTP 4xx/5xx: Error Response (RFC 7807)

**Use when:** Request failed before or during processing

```json
{
    "type": "/errors/VALIDATION_ERROR",
    "title": "Request validation failed",
    "status": 422,
    "detail": "iin: Must be exactly 12 digits",
    "instance": "/rb-ocr/api/v1/kafka/verify",
    "code": "VALIDATION_ERROR",
    "category": "client_error",
    "retryable": false,
    "trace_id": "c1d2e3f4-g5h6-7890-cdef-gh1234567890",
    "request_id": 123123
}
```

**Fields:**
- `code` (string): Machine-readable error code (use this for logic)
- `title` (string): Human-readable error summary
- `status` (integer): HTTP status code (matches response status)
- `category` (string): `"client_error"` or `"server_error"`
- `retryable` (boolean): Can this request be retried?
- `trace_id` (string): Request correlation ID
- `request_id` (integer): Your original request ID
- `detail` (string, optional): Additional error details
- `type`, `instance`: RFC 7807 standard fields

**Common error codes:**
- `VALIDATION_ERROR` - Invalid request parameters (422)
- `RESOURCE_NOT_FOUND` - S3 file not found (404)
- `S3_ERROR` - S3 service failure (502)
- `OCR_FAILED` - OCR service failure (502)
- `LLM_FILTER_PARSE_ERROR` - LLM response parsing failed (502)
- `INTERNAL_SERVER_ERROR` - Unexpected error (500)

---

## Implementation Guide

### Step 1: REST Client Setup

```python
import requests
from typing import Optional
from dataclasses import dataclass
from enum import Enum

API_BASE_URL = "https://your-api.com/rb-ocr/api"
TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
BACKOFF_SECONDS = 5

class DocumentVerdict(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING_FAILED = "processing_failed"

@dataclass
class VerificationResult:
    request_id: int
    verdict: DocumentVerdict
    run_id: Optional[str] = None
    errors: list[str] = None
    trace_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False
```

---

### Step 2: Response Handler

```python
def call_verification_api(event: dict) -> VerificationResult:
    """
    Call RB-OCR API and handle all response types correctly.
    
    Args:
        event: Kafka event with request_id, s3_path, iin, names
        
    Returns:
        VerificationResult with verdict and details
    """
    url = f"{API_BASE_URL}/v1/kafka/verify"
    
    try:
        response = requests.post(
            url,
            json=event,
            timeout=TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json"}
        )
        
        # Extract common fields
        request_id = event["request_id"]
        body = response.json()
        
        # ========================================
        # HTTP 200: Success - Process Result
        # ========================================
        if response.status_code == 200:
            return VerificationResult(
                request_id=request_id,
                verdict=(
                    DocumentVerdict.APPROVED 
                    if body["verdict"] 
                    else DocumentVerdict.REJECTED
                ),
                run_id=body["run_id"],
                errors=body.get("errors", []),
                trace_id=body.get("trace_id"),
                retryable=False  # Never retry 200 responses
            )
        
        # ========================================
        # HTTP 4xx: Client Error - Don't Retry
        # ========================================
        elif 400 <= response.status_code < 500:
            return VerificationResult(
                request_id=request_id,
                verdict=DocumentVerdict.PROCESSING_FAILED,
                trace_id=body.get("trace_id"),
                error_code=body.get("code"),
                error_message=body.get("title"),
                retryable=False  # Never retry client errors
            )
        
        # ========================================
        # HTTP 5xx: Server Error - Retry
        # ========================================
        elif response.status_code >= 500:
            return VerificationResult(
                request_id=request_id,
                verdict=DocumentVerdict.PROCESSING_FAILED,
                trace_id=body.get("trace_id"),
                error_code=body.get("code"),
                error_message=body.get("title"),
                retryable=body.get("retryable", True)  # Default to retryable
            )
        
        else:
            # Unexpected status code
            raise ValueError(f"Unexpected HTTP status: {response.status_code}")
            
    except requests.exceptions.Timeout:
        return VerificationResult(
            request_id=event["request_id"],
            verdict=DocumentVerdict.PROCESSING_FAILED,
            error_code="REQUEST_TIMEOUT",
            error_message="API request timed out",
            retryable=True
        )
    
    except requests.exceptions.ConnectionError:
        return VerificationResult(
            request_id=event["request_id"],
            verdict=DocumentVerdict.PROCESSING_FAILED,
            error_code="CONNECTION_ERROR",
            error_message="Failed to connect to API",
            retryable=True
        )
```

---

### Step 3: Kafka Consumer Logic

```python
import time
from kafka import KafkaConsumer

def process_kafka_event(event: dict) -> None:
    """
    Main Kafka consumer logic with retry handling.
    """
    max_attempts = MAX_RETRIES
    attempt = 0
    
    while attempt < max_attempts:
        attempt += 1
        
        # Call API
        result = call_verification_api(event)
        
        # ========================================
        # Success Cases (HTTP 200)
        # ========================================
        if result.verdict == DocumentVerdict.APPROVED:
            # Document passed all checks
            print(f"✅ Document approved: request_id={result.request_id}, run_id={result.run_id}")
            update_loan_application(
                request_id=result.request_id,
                status="approved",
                run_id=result.run_id
            )
            return  # Success - commit offset
        
        elif result.verdict == DocumentVerdict.REJECTED:
            # Document failed business validation
            print(f"⚠️ Document rejected: request_id={result.request_id}, errors={result.errors}")
            update_loan_application(
                request_id=result.request_id,
                status="rejected",
                rejection_reasons=result.errors,
                run_id=result.run_id
            )
            return  # Success - commit offset (rejection is valid outcome)
        
        # ========================================
        # Error Cases (HTTP 4xx/5xx)
        # ========================================
        elif result.verdict == DocumentVerdict.PROCESSING_FAILED:
            
            # Client errors - don't retry
            if not result.retryable:
                print(f"❌ Permanent error: {result.error_code} - {result.error_message}")
                update_loan_application(
                    request_id=result.request_id,
                    status="error",
                    error_code=result.error_code,
                    error_message=result.error_message
                )
                return  # Don't retry - commit offset
            
            # Server errors - retry with backoff
            else:
                if attempt < max_attempts:
                    backoff = BACKOFF_SECONDS * (2 ** (attempt - 1))  # Exponential backoff
                    print(f"⏳ Retry {attempt}/{max_attempts} after {backoff}s: {result.error_code}")
                    time.sleep(backoff)
                    continue  # Retry
                else:
                    print(f"❌ Max retries exceeded: {result.error_code}")
                    update_loan_application(
                        request_id=result.request_id,
                        status="error",
                        error_code=result.error_code,
                        error_message=f"Failed after {max_attempts} retries"
                    )
                    return  # Give up - commit offset

def update_loan_application(request_id: int, status: str, **kwargs):
    """Update your loan application database with result."""
    # Your database update logic here
    pass
```

---

### Step 4: Kafka Consumer Main Loop

```python
def run_kafka_consumer():
    """
    Main Kafka consumer loop.
    """
    consumer = KafkaConsumer(
        'rb-ocr-requests',
        bootstrap_servers=['kafka:9092'],
        group_id='rb-ocr-consumer',
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        enable_auto_commit=False  # Manual commit after processing
    )
    
    for message in consumer:
        event = message.value
        
        try:
            process_kafka_event(event)
            # Commit offset only after successful processing
            consumer.commit()
            
        except Exception as e:
            print(f"❌ Unexpected error processing event: {e}")
            # Log error but commit offset to avoid infinite retries
            log_error(event, str(e))
            consumer.commit()
```

---

## Decision Tree

```
Receive API Response
    │
    ├─ HTTP 200?
    │   ├─ verdict = true?
    │   │   └─ ✅ APPROVE loan application
    │   │      └─ Commit Kafka offset
    │   │
    │   └─ verdict = false?
    │       └─ ⚠️ REJECT loan application
    │          └─ Store rejection reasons (errors array)
    │          └─ Commit Kafka offset
    │
    ├─ HTTP 4xx (Client Error)?
    │   └─ ❌ PERMANENT ERROR
    │      └─ Log error (don't retry)
    │      └─ Mark application as error state
    │      └─ Commit Kafka offset
    │
    └─ HTTP 5xx (Server Error)?
        └─ retryable = true?
            ├─ Yes → ⏳ RETRY with exponential backoff
            │        └─ Max retries exceeded?
            │            └─ Mark as error, commit offset
            │
            └─ No  → ❌ Mark as error, commit offset
```

---

## Error Handling Matrix

| Error Code | HTTP Status | Category | Action | Retry? |
|------------|-------------|----------|--------|--------|
| `VALIDATION_ERROR` | 422 | Client | Log & skip | ❌ No |
| `RESOURCE_NOT_FOUND` | 404 | Client | Log & skip | ❌ No |
| `S3_ERROR` | 502 | Server | Retry | ✅ Yes |
| `OCR_FAILED` | 502 | Server | Retry | ✅ Yes |
| `LLM_FILTER_PARSE_ERROR` | 502 | Server | Retry | ✅ Yes |
| `INTERNAL_SERVER_ERROR` | 500 | Server | Retry | ✅ Yes |
| Network timeout | N/A | Network | Retry | ✅ Yes |
| Connection refused | N/A | Network | Retry | ✅ Yes |

---

## Logging Best Practices

### What to Log

```python
import logging

logger = logging.getLogger(__name__)

# On success (HTTP 200, verdict=true)
logger.info(
    "Document approved",
    extra={
        "request_id": result.request_id,
        "run_id": result.run_id,
        "trace_id": result.trace_id,
        "processing_time": result.processing_time_seconds
    }
)

# On rejection (HTTP 200, verdict=false)
logger.warning(
    "Document rejected",
    extra={
        "request_id": result.request_id,
        "run_id": result.run_id,
        "trace_id": result.trace_id,
        "errors": result.errors
    }
)

# On error (HTTP 4xx/5xx)
logger.error(
    "Processing failed",
    extra={
        "request_id": result.request_id,
        "trace_id": result.trace_id,
        "error_code": result.error_code,
        "error_message": result.error_message,
        "retryable": result.retryable
    }
)
```

### Correlation IDs

Always include these in logs:
- `request_id` - Your Kafka event ID
- `run_id` - RB-OCR pipeline execution ID (if available)
- `trace_id` - Request tracing ID (always available)

This enables:
1. Tracing requests across systems
2. Debugging failed requests
3. Correlating logs with RB-OCR service logs

---

## Monitoring & Alerts

### Metrics to Track

```python
# Success rate
success_rate = approved_count / total_processed

# Rejection rate (normal business outcome)
rejection_rate = rejected_count / total_processed

# Error rate (actual failures)
error_rate = error_count / total_processed

# Retry rate
retry_rate = retry_count / total_api_calls

# Processing time
p95_processing_time = percentile(processing_times, 95)
```

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Error rate | > 5% | > 10% |
| Retry rate | > 10% | > 25% |
| P95 processing time | > 30s | > 60s |
| API timeout rate | > 2% | > 5% |

---

## Testing Guide

### Test Cases

```python
import pytest
from unittest.mock import Mock, patch

def test_approved_document():
    """Test HTTP 200 with verdict=true."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "request_id": 123,
        "run_id": "550e8400-...",
        "verdict": True,
        "errors": [],
        "trace_id": "abc-123"
    }
    
    with patch('requests.post', return_value=mock_response):
        result = call_verification_api({"request_id": 123, ...})
        
    assert result.verdict == DocumentVerdict.APPROVED
    assert result.run_id is not None
    assert not result.retryable

def test_rejected_document():
    """Test HTTP 200 with verdict=false."""
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "request_id": 123,
        "run_id": "550e8400-...",
        "verdict": False,
        "errors": ["FIO_MISMATCH", "DOC_DATE_TOO_OLD"],
        "trace_id": "abc-123"
    }
    
    with patch('requests.post', return_value=mock_response):
        result = call_verification_api({"request_id": 123, ...})
        
    assert result.verdict == DocumentVerdict.REJECTED
    assert "FIO_MISMATCH" in result.errors
    assert not result.retryable

def test_validation_error():
    """Test HTTP 422 client error."""
    mock_response = Mock()
    mock_response.status_code = 422
    mock_response.json.return_value = {
        "code": "VALIDATION_ERROR",
        "title": "Invalid IIN",
        "category": "client_error",
        "retryable": False,
        "trace_id": "xyz-789"
    }
    
    with patch('requests.post', return_value=mock_response):
        result = call_verification_api({"request_id": 123, ...})
        
    assert result.verdict == DocumentVerdict.PROCESSING_FAILED
    assert result.error_code == "VALIDATION_ERROR"
    assert not result.retryable  # Don't retry client errors

def test_server_error_retry():
    """Test HTTP 502 server error with retry."""
    mock_response = Mock()
    mock_response.status_code = 502
    mock_response.json.return_value = {
        "code": "OCR_FAILED",
        "title": "OCR service timeout",
        "category": "server_error",
        "retryable": True,
        "trace_id": "def-456"
    }
    
    with patch('requests.post', return_value=mock_response):
        result = call_verification_api({"request_id": 123, ...})
        
    assert result.verdict == DocumentVerdict.PROCESSING_FAILED
    assert result.error_code == "OCR_FAILED"
    assert result.retryable  # Should retry
```

---

## Common Mistakes to Avoid

### ❌ DON'T: Ignore HTTP Status Codes

```python
# WRONG - Ignores HTTP status
response = requests.post(url, json=event)
body = response.json()

if body.get("verdict"):
    approve_document()  # What if HTTP was 500? This is wrong!
```

### ✅ DO: Check HTTP Status First

```python
# CORRECT - Check HTTP status
response = requests.post(url, json=event)

if response.status_code == 200:
    body = response.json()
    if body["verdict"]:
        approve_document()
elif response.status_code >= 500:
    retry_later()
```

---

### ❌ DON'T: Retry Client Errors (4xx)

```python
# WRONG - Retrying validation errors
if response.status_code == 422:
    time.sleep(5)
    return retry()  # Will fail again with same error!
```

### ✅ DO: Only Retry Server Errors (5xx)

```python
# CORRECT - Check retryable flag
body = response.json()
if body.get("retryable"):
    return retry_with_backoff()
else:
    log_permanent_error()
```

---

### ❌ DON'T: Use Integer Error Codes

```python
# WRONG - Hard to understand
if error_code == 12:
    handle_validation_error()
elif error_code == 15:
    handle_ocr_error()  # What is 15?
```

### ✅ DO: Use String Error Codes

```python
# CORRECT - Self-documenting
if error_code == "VALIDATION_ERROR":
    handle_validation_error()
elif error_code == "OCR_FAILED":
    handle_ocr_error()
```

---

## FAQ

### Q: Why do I get HTTP 200 for rejected documents?

**A**: HTTP 200 means "request processed successfully". Document rejection is a **valid business outcome**, not an error. The request succeeded - you got an answer (`verdict=false`).

- HTTP 200 + verdict=true → Document approved
- HTTP 200 + verdict=false → Document rejected (business decision)
- HTTP 4xx/5xx → Request failed (technical error)

---

### Q: Should I retry when verdict=false?

**A**: NO. `verdict=false` means the document legitimately failed validation (wrong name, expired date, etc.). Retrying won't change the outcome.

---

### Q: When should I use trace_id vs run_id?

- **trace_id**: For debugging ANY request (even failed ones)
- **run_id**: For querying RB-OCR database about specific document processing

If request failed validation (HTTP 422), you'll have `trace_id` but no `run_id`.

---

### Q: What if API times out?

**A**: Catch the timeout exception and retry:

```python
try:
    response = requests.post(url, json=event, timeout=60)
except requests.exceptions.Timeout:
    retry_with_backoff()
```

---

### Q: Should I store the response in my database?

**A**: Yes! Store at minimum:
- `request_id` (your ID)
- `run_id` (RB-OCR ID)
- `verdict` (true/false)
- `errors` (if any)
- `trace_id` (for debugging)

This enables audit trails and support queries.

---

## API Evolution / Versioning

If the API adds new fields in the future:
- ✅ Your code will still work (ignore unknown fields)
- ✅ New optional fields won't break existing logic
- ⚠️ Check API changelog for breaking changes
- ⚠️ Consider versioning your consumer code

---

## Support Contact

For API issues or questions:
1. Check `trace_id` in logs
2. Provide `request_id` and `trace_id` to support
3. Include HTTP status code and error code
4. Don't retry if `retryable=false`

---

## Appendix: Complete Example

```python
"""
Complete Kafka consumer implementation example.
"""

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import requests
from kafka import KafkaConsumer

# Configuration
API_BASE_URL = "https://api.example.com/rb-ocr/api"
KAFKA_TOPIC = "rb-ocr-requests"
KAFKA_SERVERS = ["kafka:9092"]
KAFKA_GROUP_ID = "rb-ocr-consumer"
TIMEOUT_SECONDS = 60
MAX_RETRIES = 3
BACKOFF_SECONDS = 5

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentVerdict(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSING_FAILED = "processing_failed"

@dataclass
class VerificationResult:
    request_id: int
    verdict: DocumentVerdict
    run_id: Optional[str] = None
    errors: Optional[list[str]] = None
    trace_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False
    processing_time_seconds: Optional[float] = None

def call_verification_api(event: dict) -> VerificationResult:
    """Call RB-OCR API and return structured result."""
    url = f"{API_BASE_URL}/v1/kafka/verify"
    request_id = event["request_id"]
    
    try:
        response = requests.post(
            url,
            json=event,
            timeout=TIMEOUT_SECONDS,
            headers={"Content-Type": "application/json"}
        )
        
        body = response.json()
        
        if response.status_code == 200:
            return VerificationResult(
                request_id=request_id,
                verdict=DocumentVerdict.APPROVED if body["verdict"] else DocumentVerdict.REJECTED,
                run_id=body["run_id"],
                errors=body.get("errors", []),
                trace_id=body.get("trace_id"),
                processing_time_seconds=body.get("processing_time_seconds")
            )
        else:
            return VerificationResult(
                request_id=request_id,
                verdict=DocumentVerdict.PROCESSING_FAILED,
                trace_id=body.get("trace_id"),
                error_code=body.get("code"),
                error_message=body.get("title"),
                retryable=body.get("retryable", response.status_code >= 500)
            )
            
    except requests.exceptions.Timeout:
        return VerificationResult(
            request_id=request_id,
            verdict=DocumentVerdict.PROCESSING_FAILED,
            error_code="REQUEST_TIMEOUT",
            error_message="API request timed out",
            retryable=True
        )
    except Exception as e:
        logger.exception("Unexpected error calling API")
        return VerificationResult(
            request_id=request_id,
            verdict=DocumentVerdict.PROCESSING_FAILED,
            error_code="UNKNOWN_ERROR",
            error_message=str(e),
            retryable=True
        )

def process_kafka_event(event: dict) -> None:
    """Process single Kafka event with retry logic."""
    for attempt in range(1, MAX_RETRIES + 1):
        result = call_verification_api(event)
        
        if result.verdict == DocumentVerdict.APPROVED:
            logger.info(
                "Document approved",
                extra={"request_id": result.request_id, "run_id": result.run_id, "trace_id": result.trace_id}
            )
            # Update your database
            return
        
        elif result.verdict == DocumentVerdict.REJECTED:
            logger.warning(
                "Document rejected",
                extra={"request_id": result.request_id, "errors": result.errors, "trace_id": result.trace_id}
            )
            # Update your database
            return
        
        elif not result.retryable:
            logger.error(
                "Permanent error",
                extra={"request_id": result.request_id, "error_code": result.error_code, "trace_id": result.trace_id}
            )
            # Update your database with error
            return
        
        elif attempt < MAX_RETRIES:
            backoff = BACKOFF_SECONDS * (2 ** (attempt - 1))
            logger.warning(f"Retrying after {backoff}s (attempt {attempt}/{MAX_RETRIES})")
            time.sleep(backoff)
        else:
            logger.error("Max retries exceeded")
            # Update your database with error
            return

def main():
    """Main Kafka consumer loop."""
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_SERVERS,
        group_id=KAFKA_GROUP_ID,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        enable_auto_commit=False
    )
    
    logger.info("Kafka consumer started")
    
    for message in consumer:
        try:
            process_kafka_event(message.value)
            consumer.commit()
        except Exception as e:
            logger.exception("Error processing message")
            consumer.commit()  # Commit to avoid reprocessing

if __name__ == "__main__":
    main()
```

---

**Document Version**: 1.0  
**Last Updated**: 2025-12-08  
**Contact**: RB-OCR API Team
