# API Response Design Evaluation

## TL;DR: Their Proposal is FLAWED ❌ - Your Current Design is BETTER ✅

**Recommendation**: Keep your current RFC 7807 approach with minor adjustments to include `request_id`.

---

## Their Proposed Schema (What They Expect)

```json
{
    "request_id": 123123,
    "status": "success,error",
    "err_code": 12, 
    "err_message": "some-error-description"
}
```

### ❌ Critical Problems

#### Problem 1: HTTP Status Code Confusion
**Issue**: What HTTP status should this return?

```
Scenario: Validation error
Their response: {"status": "error", "err_code": 12}
HTTP status: ??? (200? 400? 422?)
```

**Why it's bad:**
- HTTP clients can't distinguish errors without parsing body
- Breaks caching, retries, monitoring
- Violates REST principles

---

#### Problem 2: Mixed Success/Error Schema
**Issue**: Success and error responses share the same fields

```json
// Success case - what goes in err_code?
{
    "request_id": 123123,
    "status": "success",
    "err_code": ???,        // null? 0? omit?
    "err_message": ???      // null? empty string?
}

// Error case
{
    "request_id": 123123,
    "status": "error",
    "err_code": 12,
    "err_message": "Invalid IIN"
}
```

**Why it's bad:**
- Forces error fields to exist in success responses
- Client must check `status` before accessing other fields
- Leads to `null` pollution

---

#### Problem 3: No Business Validation Info
**Issue**: Where does business validation (`verdict`, `rule_errors`) go?

```
Scenario: FIO mismatch (HTTP 200, but business rule failed)
Their schema: ???
- status="success" or "error"?
- err_code = what?
```

**Why it's bad:**
- Conflates HTTP errors with business rule failures
- Can't distinguish "request failed" from "document invalid"

---

#### Problem 4: Integer Error Codes
**Issue**: `"err_code": 12` instead of string codes

**Why it's bad:**
- ❌ Not self-documenting (what is code 12?)
- ❌ Need lookup table to understand errors
- ❌ Hard to maintain (renumbering issues)
- ✅ Better: `"err_code": "IIN_INVALID"` (self-explanatory)

---

## Your Current Implementation (BETTER!)

### HTTP 200: VerifyResponse
```json
{
    "run_id": "550e8400-e29b-41d4-a716-446655440000",
    "verdict": true,
    "errors": [],
    "processing_time_seconds": 4.2,
    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

### HTTP 4xx/5xx: RFC 7807 ProblemDetail
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
    "trace_id": "xyz-789"
}
```

### ✅ Why Your Design is Better

1. **HTTP semantics**: Status codes match actual success/failure
2. **Type safety**: Different schemas for success/error
3. **RFC 7807 standard**: Industry-standard error format
4. **Clear separation**: Business validation vs HTTP errors
5. **String error codes**: Self-documenting

---

## Recommended Solution

### Option 1: Add `request_id` to Your Current Design (BEST ✅)

**HTTP 200 (Success or Business Validation Failed):**
```json
{
    "request_id": 123123,              // ← ADD THIS
    "run_id": "550e8400-...",
    "verdict": true,                    // or false if business rules failed
    "errors": [],                       // or ["FIO_MISMATCH"] if failed
    "processing_time_seconds": 4.2,
    "trace_id": "a1b2c3d4-..."
}
```

**HTTP 4xx/5xx (System/Client Error):**
```json
{
    "type": "/errors/VALIDATION_ERROR",
    "title": "Request validation failed",
    "status": 422,
    "code": "VALIDATION_ERROR",
    "category": "client_error",
    "retryable": false,
    "trace_id": "xyz-789",
    "request_id": 123123               // ← ADD THIS (optional but helpful)
}
```

**Changes needed:**
1. Add `request_id` field to `VerifyResponse` schema
2. Add `request_id` to `ProblemDetail` schema (optional)
3. Extract `request_id` from Kafka event and include in responses

---

### Option 2: Hybrid Approach (If They INSIST)

**Always return their schema structure, but use HTTP codes correctly:**

**HTTP 200 - Success:**
```json
{
    "request_id": 123123,
    "status": "success",
    "result": {
        "run_id": "550e8400-...",
        "verdict": true,
        "errors": []
    }
}
```

**HTTP 200 - Business Validation Failed:**
```json
{
    "request_id": 123123,
    "status": "success",
    "result": {
        "run_id": "550e8400-...",
        "verdict": false,
        "errors": ["FIO_MISMATCH", "DOC_DATE_TOO_OLD"]
    }
}
```

**HTTP 4xx/5xx - HTTP Error:**
```json
{
    "request_id": 123123,
    "status": "error",
    "err_code": "VALIDATION_ERROR",    // STRING not integer!
    "err_message": "iin: Must be exactly 12 digits"
}
```

**Why this is worse:**
- ❌ Non-standard (not RFC 7807)
- ❌ Loses detailed error info (category, retryable)
- ❌ Still has mixed schema issues
- ✅ Matches their expected structure

---

## HTTP Status Code Strategy

### When to Return What

| Scenario | HTTP Status | Response Schema | DB `status` |
|----------|-------------|-----------------|-------------|
| **Document passed all checks** | 200 OK | VerifyResponse `verdict=true` | `success` |
| **Document failed business rules** | 200 OK | VerifyResponse `verdict=false` | `success` |
| **Invalid request** | 422 Unprocessable Entity | RFC 7807 | `error` |
| **S3 file not found** | 404 Not Found | RFC 7807 | `error` |
| **OCR/LLM failure** | 502 Bad Gateway | RFC 7807 | `error` |
| **Unexpected error** | 500 Internal Server Error | RFC 7807 | `error` |

### Key Principle: HTTP 200 = "Request was processed"

```
HTTP 200 + verdict=true   → ✅ Document is valid
HTTP 200 + verdict=false  → ⚠️ Document is invalid (business rules)
HTTP 4xx                  → ❌ Client error (bad request)
HTTP 5xx                  → ❌ Server error (processing failed)
```

---

## Communication Strategy with "Them"

### If they push back on RFC 7807, show them this:

**Industry Standards:**
- ✅ Google Cloud APIs use similar patterns
- ✅ Stripe uses HTTP codes + detailed error objects
- ✅ GitHub uses HTTP codes + error details
- ✅ RFC 7807 is IETF standard (not custom)

**Benefits for them:**
- ✅ Standard HTTP client libraries work correctly
- ✅ Easier monitoring (HTTP status = quick health check)
- ✅ Automatic retries work (5xx = retry, 4xx = don't)
- ✅ API gateways handle errors correctly

**Compromise:**
If they need `request_id` at top level and `status` field:

```json
// HTTP 200
{
    "request_id": 123123,
    "status": "processed",           // Not "success" - ambiguous with verdict
    "result": {
        "run_id": "550e8400-...",
        "verdict": true,
        "errors": []
    }
}

// HTTP 4xx/5xx  
{
    "request_id": 123123,
    "status": "failed",              // Request failed, not processed
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "iin: Must be exactly 12 digits",
        "category": "client_error",
        "retryable": false
    }
}
```

---

## Code Changes for Option 1 (Recommended)

### 1. Update `VerifyResponse` Schema

```python
# api/schemas.py
class VerifyResponse(BaseModel):
    request_id: Optional[int] = Field(None, description="External request ID from Kafka event")
    run_id: str = Field(..., description="Unique run identifier (UUID)")
    verdict: bool = Field(..., description="True if all checks pass")
    errors: List[ErrorDetail] = Field(default_factory=list)
    processing_time_seconds: float = Field(...)
    trace_id: Optional[str] = Field(None)
```

### 2. Update Endpoint to Include `request_id`

```python
# main.py
@app.post("/v1/kafka/verify")
async def verify_kafka_event(request: Request, event: KafkaEventRequest):
    # ... existing code ...
    
    response = VerifyResponse(
        request_id=event.request_id,  # ← ADD THIS
        run_id=result["run_id"],
        verdict=result["verdict"],
        errors=result["errors"],
        processing_time_seconds=round(processing_time, 2),
        trace_id=trace_id,
    )
    return response
```

### 3. Add `request_id` to `ProblemDetail` (Optional)

```python
# api/schemas.py
class ProblemDetail(BaseModel):
    # ... existing fields ...
    request_id: Optional[int] = Field(None, description="External request ID if available")
```

```python
# api/middleware/exception_handler.py
except BaseError as e:
    # Try to extract request_id from request
    request_id = None
    if hasattr(request.state, 'event_data'):
        request_id = request.state.event_data.get('request_id')
    
    problem = ProblemDetail(
        **e.to_dict(),
        instance=request.url.path,
        trace_id=trace_id,
        request_id=request_id,  # ← ADD THIS
    )
```

---

## Example Responses

### Scenario 1: Success (All Checks Passed)
**HTTP 200 OK**
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

### Scenario 2: Business Validation Failed
**HTTP 200 OK** (request processed successfully, document invalid)
```json
{
    "request_id": 123123,
    "run_id": "550e8400-e29b-41d4-a716-446655440001",
    "verdict": false,
    "errors": [
        {"code": "FIO_MISMATCH"},
        {"code": "DOC_DATE_TOO_OLD"}
    ],
    "processing_time_seconds": 4.5,
    "trace_id": "b1c2d3e4-f5g6-7890-bcde-fg1234567890"
}
```

### Scenario 3: Invalid Request
**HTTP 422 Unprocessable Entity**
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

### Scenario 4: S3 File Not Found
**HTTP 404 Not Found**
```json
{
    "type": "/errors/RESOURCE_NOT_FOUND",
    "title": "S3 object not found",
    "status": 404,
    "instance": "/rb-ocr/api/v1/kafka/verify",
    "code": "RESOURCE_NOT_FOUND",
    "category": "client_error",
    "retryable": false,
    "trace_id": "d1e2f3g4-h5i6-7890-defg-hi1234567890",
    "request_id": 123123
}
```

### Scenario 5: OCR Service Failed
**HTTP 502 Bad Gateway**
```json
{
    "type": "/errors/OCR_FAILED",
    "title": "OCR service error",
    "status": 502,
    "detail": "Tesseract OCR timeout after 30 seconds",
    "instance": "/rb-ocr/api/v1/kafka/verify",
    "code": "OCR_FAILED",
    "category": "server_error",
    "retryable": true,
    "trace_id": "e1f2g3h4-i5j6-7890-efgh-ij1234567890",
    "request_id": 123123
}
```

---

## Decision Matrix

| Aspect | Their Proposal | Option 1 (Your Design + request_id) | Option 2 (Hybrid) |
|--------|----------------|--------------------------------------|-------------------|
| **HTTP semantics** | ❌ Broken | ✅ Correct | ⚠️ Acceptable |
| **Industry standard** | ❌ Custom | ✅ RFC 7807 | ❌ Custom |
| **Type safety** | ❌ Mixed schema | ✅ Separate schemas | ⚠️ Wrapped |
| **Error detail** | ❌ Minimal | ✅ Rich (category, retryable) | ⚠️ Moderate |
| **Client compatibility** | ⚠️ Needs parsing | ✅ Standard HTTP clients | ⚠️ Needs parsing |
| **Meets their request** | ✅ Exact match | ⚠️ Needs request_id | ✅ Close match |
| **Maintenance** | ❌ Hard | ✅ Easy | ⚠️ Moderate |

---

## Final Recommendation

### 1. **Negotiate with "Them"**

Show them this document and explain:
- HTTP status codes are not optional (they're part of HTTP spec)
- RFC 7807 is industry standard for REST APIs
- Your current design is superior for reliability

### 2. **Implement Option 1** (Add `request_id`)

```json
{
    "request_id": 123123,    // ← Their requirement
    "run_id": "...",         // Your tracking ID
    "verdict": true/false,   // Business validation
    "errors": [...],         // Business errors
    ...
}
```

### 3. **Keep RFC 7807 for HTTP Errors**

Don't break proper error handling for client convenience.

### 4. **Document API Contract**

Create OpenAPI/Swagger spec showing:
- When HTTP 200 is returned
- When HTTP 4xx/5xx is returned
- Example responses for each scenario

---

## Bottom Line

**Their proposal is fundamentally flawed** because it ignores HTTP semantics. Your current RFC 7807 design is architecturally sound.

**Best compromise:**
- Keep your RFC 7807 approach ✅
- Add `request_id` to both success and error responses ✅
- Use proper HTTP status codes ✅
- Educate "them" on why this is better ✅

If they still insist on their schema after seeing this analysis, they're making a mistake that will cost them in monitoring, debugging, and client integration complexity.

**Your reasoning is CORRECT** - don't let them break good API design! 🎯
