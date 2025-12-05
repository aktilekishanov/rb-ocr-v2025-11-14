# AS-IS: Current Error Handling Architecture

## Executive Summary

The RB-OCR FastAPI service currently implements a **mixed error handling approach** with:
- **Verification errors** (business logic failures) handled via structured error codes
- **System errors** (infrastructure failures) caught and converted to HTTP 500 responses
- Limited HTTP status code diversity (only 500 is used)
- No custom exception hierarchy

---

## 1. Error Classification Pattern

### 1.1 Verification Errors (Business Logic)

**Location**: [`pipeline/core/errors.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/errors.py)

These represent **expected failure scenarios** where the document validation fails:

```python
ERROR_MESSAGES_RU: dict[str, str] = {
    # Acquisition/UI
    "PDF_TOO_MANY_PAGES": "PDF должен содержать не более 3 страниц",
    "FILE_SAVE_FAILED": "Не удалось сохранить файл",
    
    # OCR
    "OCR_FAILED": "Ошибка распознавания OCR",
    "OCR_FILTER_FAILED": "Ошибка обработки страниц OCR",
    "OCR_EMPTY_PAGES": "Не удалось получить текст страниц из OCR",
    
    # Doc-type check (LLM)
    "DTC_FAILED": "Ошибка проверки типа документа",
    "MULTIPLE_DOCUMENTS": "Файл содержит несколько типов документов",
    "DTC_PARSE_ERROR": "Некорректный ответ проверки типа документа",
    
    # Extraction (LLM)
    "EXTRACT_FAILED": "Ошибка извлечения данных LLM",
    "LLM_FILTER_PARSE_ERROR": "Ошибка фильтрации ответа LLM",
    "EXTRACT_SCHEMA_INVALID": "Некорректная схема данных извлечения",
    
    # Merge/Validation
    "MERGE_FAILED": "Ошибка при формировании итогового JSON",
    "VALIDATION_FAILED": "Ошибка валидации",
    "UNKNOWN_ERROR": "Неизвестная ошибка",
    
    # Check-derived
    "FIO_MISMATCH": "ФИО не совпадает",
    "FIO_MISSING": "Не удалось извлечь ФИО из документа",
    "DOC_TYPE_UNKNOWN": "Не удалось определить тип документа",
    "DOC_DATE_TOO_OLD": "Устаревшая дата документа",
    "DOC_DATE_MISSING": "Не удалось распознать дату документа",
    "SINGLE_DOC_TYPE_INVALID": "Файл содержит несколько типов документов",
}
```

**Characteristics**:
- Predefined error codes
- Russian-language messages
- Returned as structured data in API response (`errors` array)
- Do NOT cause HTTP 5xx responses
- Pipeline continues to completion even with errors

---

### 1.2 System Errors (Infrastructure Failures)

**Locations**: 
- [`main.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/main.py) (lines 75-80, 163-178)
- [`pipeline/clients/llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py) (lines 12-30)

These represent **unexpected infrastructure or system failures**:

#### Example: Generic Error Handler in `main.py`
```python
except Exception as e:
    logger.error(f"[ERROR] {e}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail=f"Internal processing error: {str(e)}"
    )
```

#### Example: S3 Error Handler in `main.py`
```python
except S3Error as e:
    logger.error(f"[S3 ERROR] request_id={event.request_id}: {e}", exc_info=True)
    raise HTTPException(
        status_code=500,
        detail=f"S3 download error: {e.code} - {e.message}"
    )
```

**Characteristics**:
- Always result in HTTP 500 status
- Logged with full stack trace
- Message exposed in HTTP response body
- Pipeline execution stops immediately

---

## 2. HTTP Status Code Usage

### Current State: **MONOLITHIC 500 APPROACH**

All errors result in **HTTP 500 Internal Server Error**, regardless of the actual failure cause.

| Error Type | Current Status Code | Example |
|------------|---------------------|---------|
| Invalid file format | 500 | User uploads .txt instead of PDF |
| Missing request parameter | 500 | Missing `fio` field |
| S3 file not found | 500 | `s3_path` points to non-existent object |
| S3 authentication failure | 500 | Invalid credentials |
| LLM timeout | 500 | LLM takes >30s to respond |
| OCR service unavailable | 500 | OCR endpoint is down |
| Pipeline processing error | 500 | Any exception during processing |

**Issue**: All errors are categorized as server failures, even when they are client errors (e.g., invalid input).

---

## 3. Error Propagation Flow

### 3.1 Pipeline Orchestrator Pattern

**Location**: [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py)

The orchestrator uses a **graceful degradation** pattern:

```python
def run_pipeline(...) -> dict[str, Any]:
    # Sequential stages
    for stage in (
        stage_acquire,
        stage_ocr,
        stage_doc_type_check,
        stage_extract,
        stage_merge,
        stage_validate_and_finalize,
    ):
        res = stage(ctx)
        if res is not None:  # Stage returned error
            return res  # Stop and return error result
    
    return fail_and_finalize("UNKNOWN_ERROR", None, ctx)
```

**How it works**:
1. Each stage returns `None` on success
2. Each stage returns `dict` (via `fail_and_finalize()`) on failure
3. First failure stops the pipeline
4. Error is written to JSON artifacts
5. **Pipeline returns a valid response** (verdict=False, errors=[...])

### 3.2 Stage-Level Error Handling

Each stage catches exceptions and converts them to error codes:

```python
def stage_ocr(ctx: PipelineContext) -> dict[str, Any] | None:
    with stage_timer(ctx, "ocr"):
        ocr_result = ask_tesseract(...)
    
    if not ocr_result.get("success"):
        return fail_and_finalize("OCR_FAILED", str(ocr_result.get("error")), ctx)
    
    try:
        filtered_pages_path = filter_ocr_response(...)
        # ... processing ...
        return None  # Success
    except Exception as e:
        return fail_and_finalize("OCR_FILTER_FAILED", str(e), ctx)
```

### 3.3 FastAPI Layer Error Handling

**Location**: [`main.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/main.py)

```python
@app.post("/v1/verify", response_model=VerifyResponse)
async def verify_document(...):
    try:
        result = await processor.process_document(...)
        
        response = VerifyResponse(
            run_id=result["run_id"],
            verdict=result["verdict"],
            errors=result["errors"],  # Verification errors
            processing_time_seconds=round(processing_time, 2),
        )
        return response
    
    except Exception as e:  # System errors
        logger.error(f"[ERROR] {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal processing error: {str(e)}")
```

**Key Insight**: 
- Pipeline errors → Structured response with `verdict=False`
- System exceptions → HTTP 500 + unstructured error message

---

## 4. Client-Level Error Handling

### 4.1 LLM Client

**Location**: [`pipeline/clients/llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py)

**Custom Exception Hierarchy**:
```python
class LLMClientError(Exception):
    """Base exception for LLM client errors."""

class LLMNetworkError(LLMClientError):
    """Raised when network/connection errors occur."""

class LLMHTTPError(LLMClientError):
    """Raised when HTTP errors occur (4xx, 5xx)."""

class LLMResponseError(LLMClientError):
    """Raised when response parsing fails."""
```

**Error Handlers**:
```python
try:
    with urllib.request.urlopen(req, context=context, timeout=30) as response:
        raw = response.read().decode("utf-8")
        return raw
except urllib.error.HTTPError as e:
    raise LLMHTTPError(f"HTTP {e.code} error from LLM endpoint: {e.reason}. Body: {error_body}")
except urllib.error.URLError as e:
    raise LLMNetworkError(f"Network error connecting to LLM endpoint: {e.reason}")
except ssl.SSLError as e:
    raise LLMNetworkError(f"SSL error connecting to LLM endpoint: {e}")
except UnicodeDecodeError as e:
    raise LLMResponseError(f"Failed to decode LLM response as UTF-8: {e}")
except Exception as e:
    raise LLMClientError(f"Unexpected error calling LLM endpoint: {e}")
```

**Issue**: These custom exceptions are **never caught specifically** in the orchestrator. They bubble up and get converted to generic error codes (`DTC_FAILED`, `EXTRACT_FAILED`).

### 4.2 OCR Client

**Location**: [`pipeline/clients/tesseract_async_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/tesseract_async_client.py)

**No Custom Exceptions**: Returns success/error dict pattern:
```python
return {
    "success": success,
    "error": error,
    "id": file_id,
    "upload": upload_resp,
    "result": result_obj,
}
```

**httpx exceptions** (HTTPStatusError, RequestError, TimeoutException) are **not caught** - they propagate as generic exceptions.

### 4.3 S3 Client

**Location**: [`services/s3_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/services/s3_client.py)

```python
try:
    stat = self.client.stat_object(self.bucket, object_key)
    response = self.client.get_object(self.bucket, object_key)
    # ... download logic ...
except S3Error as e:
    logger.error(f"S3 error downloading {object_key}: {e}")
    raise  # Re-raised as-is
except Exception as e:
    logger.error(f"Error downloading {object_key}: {e}")
    raise  # Re-raised as-is
```

**Caught in main.py**:
```python
except S3Error as e:
    raise HTTPException(status_code=500, detail=f"S3 download error: {e.code} - {e.message}")
```

---

## 5. Edge Cases and Gaps

### 5.1 Unconsidered Edge Cases

| Edge Case | Current Behavior | Issue |
|-----------|------------------|-------|
| **OCR timeout** | httpx.TimeoutException → HTTP 500 | No specific error code, unclear to user |
| **S3 file not found** | S3Error.code="NoSuchKey" → HTTP 500 | Should be 404, not server error |
| **S3 auth failure** | S3Error → HTTP 500 | Should be 500, but could be more specific |
| **LLM rate limiting** | LLMHTTPError(429) → HTTP 500 | Should indicate retry-ability |
| **LLM timeout** | socket.timeout → HTTP 500 | Generic error, no retry guidance |
| **Invalid PDF structure** | Could fail at OCR or page count | Error location varies |
| **Missing FIO parameter** | **Not validated** | No 400 error |
| **Invalid IIN format** | **Not validated** | No 400 error |
| **Concurrent request overload** | No rate limiting | Potential DoS |
| **Disk space full** | Generic exception → HTTP 500 | Infrastructure issue, unclear |
| **Network partition** | Varies by service | No circuit breaker pattern |

### 5.2 Error Message Exposure

**Security Issue**: Internal exception messages are exposed in HTTP responses:
```python
detail=f"Internal processing error: {str(e)}"
```

This can leak:
- Stack traces
- File paths (`/Users/.../pipeline/...`)
- Internal service URLs
- Configuration details

---

## 6. Response Schema

### Current Schema

**Location**: [`api/schemas.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/api/schemas.py)

```python
class ErrorDetail(BaseModel):
    code: str = Field(..., description="Error code (e.g., FIO_MISMATCH)")
    message: str | None = Field(None, description="Human-readable message in Russian")

class VerifyResponse(BaseModel):
    run_id: str
    verdict: bool
    errors: List[ErrorDetail]  # Only for verification errors
    processing_time_seconds: float
```

**Limitations**:
- No `details` field for additional context
- No error severity levels
- No guidance on whether error is retryable
- No error timestamps
- No trace IDs for debugging

---

## 7. Logging Strategy

### Current Logging

```python
logger.info(f"[NEW REQUEST] FIO={fio}, file={file.filename}")
logger.error(f"[ERROR] {e}", exc_info=True)
logger.info(f"[RESPONSE] run_id={response.run_id}, verdict={response.verdict}")
```

**Strengths**:
- Structured log prefixes (`[NEW REQUEST]`, `[ERROR]`, etc.)
- Full stack traces for errors (`exc_info=True`)
- Request/response correlation via `run_id`

**Weaknesses**:
- No log levels for different error types
- No structured logging (JSON format)
- No distributed tracing support
- No correlation IDs across services

---

## 8. Summary of Current State

### ✅ What Works Well

1. **Clear separation** between verification errors and system errors at the pipeline level
2. **Graceful degradation** - pipeline completes even with errors
3. **Structured error codes** for verification failures
4. **Comprehensive error messages** in Russian for end-users
5. **Custom exception hierarchy** in LLM client (though underutilized)

### ❌ Critical Issues

1. **No HTTP status code diversity** - everything is 500
2. **No input validation** - missing 400 errors for bad requests
3. **Custom exceptions not leveraged** - LLMClientError, etc. not caught specifically
4. **Error message exposure** - internal details leak to clients
5. **No retry guidance** - clients don't know if retries will help
6. **No timeout differentiation** - timeouts vs. permanent failures treated the same
7. **No circuit breaker** - repeated failures to external services not handled
8. **No rate limiting** - vulnerable to abuse

---

## 9. Error Flow Diagram

```mermaid
flowchart TD
    A[Client Request] --> B{Input Valid?}
    B -->|No| C[❌ HTTP 500<br/>Generic Error]
    B -->|Yes| D[Pipeline Orchestrator]
    
    D --> E[Stage: Acquire]
    E -->|Error| F[fail_and_finalize<br/>verdict=False]
    E -->|Success| G[Stage: OCR]
    
    G -->|Error| F
    G -->|Success| H[Stage: Doc Type Check]
    
    H -->|Error| F
    H -->|Success| I[Stage: Extract]
    
    I -->|Error| F
    I -->|Success| J[Stage: Merge]
    
    J -->|Error| F
    J -->|Success| K[Stage: Validate]
    
    K --> L{Checks Pass?}
    L -->|All Pass| M[✅ HTTP 200<br/>verdict=True]
    L -->|Some Fail| N[✅ HTTP 200<br/>verdict=False<br/>errors=[...]]
    
    F --> N
    
    D -.Exception.-> O[❌ HTTP 500<br/>Internal Error]
    
    style C fill:#ff6b6b
    style M fill:#51cf66
    style N fill:#ff922b
    style O fill:#ff6b6b
```

---

## 10. Code References

| Component | File | Lines |
|-----------|------|-------|
| Error codes | [`pipeline/core/errors.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/errors.py) | 10-37 |
| API error handling | [`main.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/main.py) | 75-80, 163-178 |
| Pipeline orchestrator | [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py) | 168-199, 232-252 |
| LLM client exceptions | [`pipeline/clients/llm_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/llm_client.py) | 12-98 |
| OCR client | [`pipeline/clients/tesseract_async_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/clients/tesseract_async_client.py) | 81-118 |
| S3 client | [`services/s3_client.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/services/s3_client.py) | 54-108 |
| Response schemas | [`api/schemas.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/api/schemas.py) | 6-31 |
