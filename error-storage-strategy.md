# Error Storage Strategy for PostgreSQL

## Questions Answered

1. **How to store multiple check failures** (fio_mismatch, doc_date_invalid, multiple_doc_types, doc_type_unknown)
2. **How to differentiate and store RFC 7807 errors** (client vs server vs business validation errors)

---

## TL;DR Recommendations

### For Question 1: Check Results Storage
**Use a hybrid approach**: Individual boolean fields + JSON array for errors

```sql
-- Individual check fields (for fast queries)
check_fio_match BOOLEAN,
check_doc_date_valid BOOLEAN,
check_doc_type_known BOOLEAN,
check_single_doc_type BOOLEAN,

-- Aggregated error list (for complete context)
errors JSONB DEFAULT '[]'::jsonb,
```

### For Question 2: RFC 7807 Error Storage
**Use separate columns for error taxonomy**:

```sql
-- Overall status
status VARCHAR(20) NOT NULL,  -- 'success', 'business_error', 'client_error', 'server_error'

-- Business validation errors (HTTP 200 with verdict=false)
verdict BOOLEAN NOT NULL,
errors JSONB DEFAULT '[]'::jsonb,  -- [{"code": "FIO_MISMATCH"}, ...]

-- System/Client errors (HTTP 4xx/5xx)
error_category VARCHAR(20),  -- 'client_error', 'server_error', NULL if success
error_code VARCHAR(100),     -- 'VALIDATION_ERROR', 'S3_ERROR', 'OCR_FAILED', etc.
error_message TEXT,          -- Human-readable error
error_retryable BOOLEAN,     -- Can client retry?
```

---

## Deep Dive: Question 1 - Multiple Check Failures

### The Problem

Your validation can fail in **multiple ways simultaneously**:

```python
# From validator.py
checks = {
    "fio_match": False,           # ❌ FIO doesn't match
    "doc_type_known": False,      # ❌ Unknown document type
    "doc_date_valid": False,      # ❌ Document too old
    "single_doc_type_valid": True # ✅ Single document
}
# Result: 3 failures at once!
```

Current schema (your proposal):
```sql
check_fio_match BOOLEAN,
check_doc_date_valid BOOLEAN,
check_doc_type_known BOOLEAN,
check_single_doc_type BOOLEAN,
```

**Issue**: Individual booleans are great for queries, but you also accumulate errors:

```python
# From orchestrator.py lines 384-403
check_errors: list[dict[str, Any]] = []
if fm is False:
    check_errors.append(make_error("FIO_MISMATCH"))
elif fm is None:
    check_errors.append(make_error("FIO_MISSING"))
if dtk is False or dtk is None:
    check_errors.append(make_error("DOC_TYPE_UNKNOWN"))
if dv is False:
    check_errors.append(make_error("DOC_DATE_TOO_OLD"))
# ...
ctx.errors.extend(check_errors)
```

### Solution: Hybrid Approach (BEST)

**Store both**: Individual fields for queries + JSON array for complete error context

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE,
    
    -- ... external fields ...
    
    -- Individual check booleans (fast queries, indexable)
    check_fio_match BOOLEAN,
    check_doc_date_valid BOOLEAN,
    check_doc_type_known BOOLEAN,
    check_single_doc_type BOOLEAN,
    
    -- Aggregated error list (complete context)
    errors JSONB DEFAULT '[]'::jsonb,
    
    -- Overall verdict
    verdict BOOLEAN NOT NULL,
    
    -- ... other fields ...
);
```

**Example row**:
```json
{
  "run_id": "550e8400-e29b-41d4-a716-446655440000",
  "check_fio_match": false,
  "check_doc_date_valid": false,
  "check_doc_type_known": true,
  "check_single_doc_type": true,
  "errors": [
    {"code": "FIO_MISMATCH"},
    {"code": "DOC_DATE_TOO_OLD"}
  ],
  "verdict": false
}
```

### Why This Works

#### ✅ Fast Queries (Using Boolean Fields)
```sql
-- "Show me all runs where FIO didn't match"
SELECT * FROM runs WHERE check_fio_match = false;

-- "Show me runs with multiple check failures"
SELECT * FROM runs 
WHERE (check_fio_match = false)::int 
    + (check_doc_date_valid = false)::int 
    + (check_doc_type_known = false)::int 
    + (check_single_doc_type = false)::int > 1;

-- "Breakdown of failure types"
SELECT 
    SUM(CASE WHEN check_fio_match = false THEN 1 ELSE 0 END) as fio_failures,
    SUM(CASE WHEN check_doc_date_valid = false THEN 1 ELSE 0 END) as date_failures,
    SUM(CASE WHEN check_doc_type_known = false THEN 1 ELSE 0 END) as type_failures
FROM runs
WHERE verdict = false;
```

#### ✅ Complete Error Context (Using JSONB)
```sql
-- "Show me exact error codes for this run"
SELECT errors FROM runs WHERE run_id = '550e8400-e29b-41d4-a716-446655440000';
-- Result: [{"code": "FIO_MISMATCH"}, {"code": "DOC_DATE_TOO_OLD"}]

-- "Find all runs with specific error code"
SELECT * FROM runs WHERE errors @> '[{"code": "FIO_MISMATCH"}]'::jsonb;

-- "Show most common error combinations"
SELECT errors, COUNT(*) 
FROM runs 
WHERE verdict = false 
GROUP BY errors 
ORDER BY COUNT(*) DESC 
LIMIT 10;
```

### Alternative: JSONB-Only Approach (NOT Recommended)

You *could* store everything in JSONB:

```sql
-- Alternative: Store all checks in JSONB
checks JSONB DEFAULT '{}'::jsonb,
errors JSONB DEFAULT '[]'::jsonb
```

```json
{
  "checks": {
    "fio_match": false,
    "doc_date_valid": false,
    "doc_type_known": true,
    "single_doc_type_valid": true
  },
  "errors": [
    {"code": "FIO_MISMATCH"},
    {"code": "DOC_DATE_TOO_OLD"}
  ]
}
```

**Why NOT to do this**:
- ❌ Slower queries (JSONB path queries are slower than column lookups)
- ❌ Harder to index for analytics
- ❌ No type safety at DB level
- ❌ More complex query syntax

**When to consider it**:
- ✅ If you need to add new check types frequently (dynamic schema)
- ✅ If you're using document DB patterns in PostgreSQL

---

## Deep Dive: Question 2 - RFC 7807 Error Storage

### The Problem: Three Error Types

Your system has **3 distinct error categories**:

#### 1. **Business Validation Errors** (HTTP 200, verdict=false)
```json
{
  "run_id": "abc-123",
  "verdict": false,
  "errors": [{"code": "FIO_MISMATCH"}],
  "processing_time_seconds": 4.2
}
```
- Pipeline completed successfully
- Document failed business rules
- **Not an HTTP error** - always returns 200 OK

#### 2. **Client Errors** (HTTP 4xx via RFC 7807)
```json
{
  "type": "/errors/VALIDATION_ERROR",
  "title": "Request validation failed",
  "status": 422,
  "detail": "iin: Must be exactly 12 digits",
  "code": "VALIDATION_ERROR",
  "category": "client_error",
  "retryable": false,
  "trace_id": "xyz-789"
}
```
- Invalid input from client
- Never reaches pipeline
- **HTTP error** - returns 4xx status

#### 3. **Server Errors** (HTTP 5xx via RFC 7807)
```json
{
  "type": "/errors/S3_ERROR",
  "title": "S3 service error",
  "status": 502,
  "code": "S3_ERROR",
  "category": "server_error",
  "retryable": true,
  "trace_id": "def-456"
}
```
- External service failure (S3, OCR, LLM)
- Internal server error
- **HTTP error** - returns 5xx status

### Challenge: How to Store These in One Table?

You need to distinguish:
1. Did the request succeed or fail?
2. If failed, was it client fault or server fault?
3. Can the client retry?
4. What was the specific error?

### Solution: Status + Error Taxonomy

```sql
CREATE TABLE runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE,
    
    -- ========================================
    -- REQUEST METADATA
    -- ========================================
    external_request_id VARCHAR(100),
    external_s3_path VARCHAR(1024),
    external_iin VARCHAR(12),
    external_first_name VARCHAR(100),
    external_last_name VARCHAR(100),
    external_second_name VARCHAR(100),
    
    -- ========================================
    -- EXTRACTED DATA
    -- ========================================
    extracted_fio TEXT,
    extracted_doc_date VARCHAR(20),
    extracted_single_doc_type BOOLEAN,
    extracted_doc_type_known BOOLEAN,
    extracted_doc_type VARCHAR(200),
    
    -- ========================================
    -- VALIDATION CHECKS (Business Rules)
    -- ========================================
    check_fio_match BOOLEAN,
    check_doc_date_valid BOOLEAN,
    check_doc_type_known BOOLEAN,
    check_single_doc_type BOOLEAN,
    
    -- ========================================
    -- FINAL VERDICT & BUSINESS ERRORS
    -- ========================================
    verdict BOOLEAN NOT NULL,
    errors JSONB DEFAULT '[]'::jsonb,  -- Business validation errors
    
    -- ========================================
    -- OVERALL STATUS (KEY FIELD!)
    -- ========================================
    status VARCHAR(20) NOT NULL,
    -- Possible values:
    --   'success'         - HTTP 200, verdict=true, no errors
    --   'business_error'  - HTTP 200, verdict=false, business validation failed
    --   'client_error'    - HTTP 4xx, invalid request, never reached pipeline
    --   'server_error'    - HTTP 5xx, system/external service failure
    
    -- ========================================
    -- SYSTEM/CLIENT ERROR DETAILS (RFC 7807)
    -- ========================================
    error_category VARCHAR(20),
    -- Values: 'client_error', 'server_error', NULL if success/business_error
    
    error_code VARCHAR(100),
    -- RFC 7807 error codes: 'VALIDATION_ERROR', 'S3_ERROR', 'OCR_FAILED', etc.
    -- NULL if status='success' or status='business_error'
    
    error_message TEXT,
    -- Human-readable error from RFC 7807 'detail' field
    -- NULL if status='success' or status='business_error'
    
    error_detail TEXT,
    -- Additional technical details (optional)
    
    error_retryable BOOLEAN,
    -- Can client retry? (from RFC 7807)
    -- NULL if not applicable
    
    -- ========================================
    -- TIMING
    -- ========================================
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    processing_time_seconds FLOAT,
    
    -- ========================================
    -- TRACING
    -- ========================================
    trace_id UUID,
    
    -- ========================================
    -- INDEXES
    -- ========================================
    CONSTRAINT runs_status_check CHECK (status IN ('success', 'business_error', 'client_error', 'server_error'))
);

-- Indexes
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_error_code ON runs(error_code);
CREATE INDEX idx_runs_verdict ON runs(verdict);
CREATE INDEX idx_runs_external_request_id ON runs(external_request_id);
CREATE INDEX idx_runs_external_iin ON runs(external_iin);
CREATE INDEX idx_runs_created_at ON runs(created_at DESC);
CREATE INDEX idx_runs_error_category ON runs(error_category) WHERE error_category IS NOT NULL;
```

### Example Rows

#### Example 1: Success (HTTP 200, verdict=true)
```json
{
  "status": "success",
  "verdict": true,
  "errors": [],
  "check_fio_match": true,
  "check_doc_date_valid": true,
  "check_doc_type_known": true,
  "check_single_doc_type": true,
  "error_category": null,
  "error_code": null,
  "error_message": null,
  "error_retryable": null
}
```

#### Example 2: Business Error (HTTP 200, verdict=false)
```json
{
  "status": "business_error",
  "verdict": false,
  "errors": [
    {"code": "FIO_MISMATCH"},
    {"code": "DOC_DATE_TOO_OLD"}
  ],
  "check_fio_match": false,
  "check_doc_date_valid": false,
  "check_doc_type_known": true,
  "check_single_doc_type": true,
  "error_category": null,
  "error_code": null,
  "error_message": null,
  "error_retryable": null
}
```

#### Example 3: Client Error (HTTP 422)
```json
{
  "status": "client_error",
  "verdict": false,
  "errors": [],
  "check_fio_match": null,
  "check_doc_date_valid": null,
  "check_doc_type_known": null,
  "check_single_doc_type": null,
  "error_category": "client_error",
  "error_code": "VALIDATION_ERROR",
  "error_message": "iin: Must be exactly 12 digits",
  "error_retryable": false,
  "external_iin": "123",  // Invalid IIN that caused error
  "extracted_fio": null,  // Pipeline never ran
  "processing_time_seconds": 0.01  // Failed fast
}
```

#### Example 4: Server Error (HTTP 502)
```json
{
  "status": "server_error",
  "verdict": false,
  "errors": [],
  "check_fio_match": null,
  "check_doc_date_valid": null,
  "check_doc_type_known": null,
  "check_single_doc_type": null,
  "error_category": "server_error",
  "error_code": "S3_ERROR",
  "error_message": "Failed to download file from S3: Connection timeout",
  "error_retryable": true,
  "external_s3_path": "documents/2024/sample.pdf",
  "extracted_fio": null,  // Pipeline started but failed early
  "processing_time_seconds": 5.3  // Spent time trying to connect
}
```

---

## Query Examples by Error Type

### 1. Success Rate
```sql
SELECT 
    status,
    COUNT(*) as count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM runs
GROUP BY status
ORDER BY count DESC;
```

**Result**:
```
status           | count | percentage
-----------------|-------|----------
success          | 8520  | 85.20%
business_error   | 1130  | 11.30%
client_error     | 250   |  2.50%
server_error     | 100   |  1.00%
```

### 2. Client Error Breakdown
```sql
SELECT 
    error_code,
    COUNT(*) as count,
    error_retryable,
    ARRAY_AGG(DISTINCT SUBSTRING(error_message, 1, 50)) as sample_messages
FROM runs
WHERE status = 'client_error'
GROUP BY error_code, error_retryable
ORDER BY count DESC;
```

**Result**:
```
error_code         | count | retryable | sample_messages
-------------------|-------|-----------|------------------
VALIDATION_ERROR   | 200   | false     | ["iin: Must be exactly 12 digits", "s3_path: Cannot contain '..'"]
RESOURCE_NOT_FOUND | 50    | false     | ["S3 object not found: documents/2024/missing.pdf"]
```

### 3. Server Error Analysis (Retryable vs Not)
```sql
SELECT 
    error_code,
    error_retryable,
    COUNT(*) as count,
    AVG(processing_time_seconds) as avg_time_to_fail
FROM runs
WHERE status = 'server_error'
GROUP BY error_code, error_retryable
ORDER BY count DESC;
```

**Result**:
```
error_code          | retryable | count | avg_time_to_fail
--------------------|-----------|-------|------------------
S3_ERROR            | true      | 45    | 5.2
OCR_FAILED          | true      | 30    | 8.7
LLM_TIMEOUT         | true      | 15    | 30.0
INTERNAL_SERVER_ERROR| false    | 10    | 0.3
```

### 4. Business Validation Failure Analysis
```sql
-- Most common validation failure combinations
SELECT 
    errors,
    COUNT(*) as count
FROM runs
WHERE status = 'business_error'
GROUP BY errors
ORDER BY count DESC
LIMIT 10;
```

**Result**:
```
errors                                          | count
------------------------------------------------|------
[{"code": "FIO_MISMATCH"}]                     | 450
[{"code": "DOC_DATE_TOO_OLD"}]                 | 320
[{"code": "DOC_TYPE_UNKNOWN"}]                 | 180
[{"code": "FIO_MISMATCH"}, {"code": "DOC_DATE_TOO_OLD"}] | 90
```

### 5. Error Funnel (Where do requests fail?)
```sql
SELECT 
    CASE 
        WHEN status = 'client_error' THEN '1. Request Validation'
        WHEN status = 'server_error' AND error_code IN ('S3_ERROR') THEN '2. File Download'
        WHEN status = 'server_error' AND error_code IN ('OCR_FAILED') THEN '3. OCR Processing'
        WHEN status = 'server_error' AND error_code IN ('LLM_FILTER_PARSE_ERROR', 'EXTRACT_FAILED') THEN '4. LLM Processing'
        WHEN status = 'business_error' THEN '5. Business Validation'
        WHEN status = 'success' THEN '6. Success'
        ELSE 'Other'
    END as stage,
    COUNT(*) as count
FROM runs
GROUP BY stage
ORDER BY stage;
```

**Result**:
```
stage                  | count
-----------------------|------
1. Request Validation  | 250
2. File Download       | 45
3. OCR Processing      | 30
4. LLM Processing      | 25
5. Business Validation | 1130
6. Success             | 8520
```

---

## Implementation in FastAPI Processor

### Current Code Flow

Looking at your middleware (`exception_handler.py`), you already have:

```python
# Base error categories
category = "client_error"  # or "server_error"
```

And in orchestrator, you have:

```python
# Business errors
ctx.errors.append(make_error("FIO_MISMATCH"))
```

### How to Map to Database

```python
# In services/processor.py or new services/db_writer.py

from typing import Dict, Any, Optional

def build_db_record(
    run_id: str,
    verdict: bool,
    errors: list[dict],
    checks: Optional[dict],
    external_data: dict,
    extracted_data: dict,
    processing_time: float,
    trace_id: Optional[str],
    rfc_error: Optional[dict] = None,  # RFC 7807 error if exists
) -> Dict[str, Any]:
    """Build PostgreSQL record from pipeline result."""
    
    # Determine status
    if rfc_error is not None:
        # System or client error (HTTP 4xx/5xx)
        status = rfc_error.get("category")  # 'client_error' or 'server_error'
        error_category = rfc_error.get("category")
        error_code = rfc_error.get("code")
        error_message = rfc_error.get("detail")
        error_retryable = rfc_error.get("retryable")
    elif verdict:
        # Success (HTTP 200, verdict=true)
        status = "success"
        error_category = None
        error_code = None
        error_message = None
        error_retryable = None
    else:
        # Business error (HTTP 200, verdict=false)
        status = "business_error"
        error_category = None
        error_code = None
        error_message = None
        error_retryable = None
    
    return {
        "run_id": run_id,
        "external_request_id": external_data.get("request_id"),
        "external_s3_path": external_data.get("s3_path"),
        "external_iin": external_data.get("iin"),
        "external_first_name": external_data.get("first_name"),
        "external_last_name": external_data.get("last_name"),
        "external_second_name": external_data.get("second_name"),
        
        "extracted_fio": extracted_data.get("fio"),
        "extracted_doc_date": extracted_data.get("doc_date"),
        "extracted_single_doc_type": extracted_data.get("single_doc_type"),
        "extracted_doc_type_known": extracted_data.get("doc_type_known"),
        "extracted_doc_type": extracted_data.get("doc_type"),
        
        "check_fio_match": checks.get("fio_match") if checks else None,
        "check_doc_date_valid": checks.get("doc_date_valid") if checks else None,
        "check_doc_type_known": checks.get("doc_type_known") if checks else None,
        "check_single_doc_type": checks.get("single_doc_type_valid") if checks else None,
        
        "verdict": verdict,
        "errors": errors,  # JSONB array
        
        "status": status,
        "error_category": error_category,
        "error_code": error_code,
        "error_message": error_message,
        "error_retryable": error_retryable,
        
        "processing_time_seconds": processing_time,
        "trace_id": trace_id,
        "created_at": datetime.now(),
        "completed_at": datetime.now(),
    }
```

### Handling RFC 7807 Errors

When an exception occurs in middleware:

```python
# In api/middleware/exception_handler.py

except BaseError as e:
    # Before returning RFC 7807 response, also store in DB
    rfc_error = {
        "category": "server_error",  # or from e.category
        "code": e.error_code,
        "detail": e.detail,
        "retryable": e.retryable,
    }
    
    # Store failed run in database
    db_record = build_db_record(
        run_id=getattr(request.state, "run_id", str(uuid.uuid4())),
        verdict=False,
        errors=[],  # No business errors for system errors
        checks=None,
        external_data=extract_external_data_from_request(request),
        extracted_data={},
        processing_time=time.time() - request.state.start_time,
        trace_id=trace_id,
        rfc_error=rfc_error,  # Pass RFC 7807 error
    )
    
    await insert_to_postgres(db_record)
    
    # Then return RFC 7807 response
    return JSONResponse(...)
```

---

## Final Schema Recommendation

```sql
CREATE TABLE runs (
    -- Primary keys
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE,
    
    -- External request context (from Kafka)
    external_request_id VARCHAR(100),
    external_s3_path VARCHAR(1024),
    external_iin VARCHAR(12),
    external_first_name VARCHAR(100),
    external_last_name VARCHAR(100),
    external_second_name VARCHAR(100),
    
    -- Extracted data (from pipeline)
    extracted_fio TEXT,
    extracted_doc_date VARCHAR(20),
    extracted_single_doc_type BOOLEAN,
    extracted_doc_type_known BOOLEAN,
    extracted_doc_type VARCHAR(200),
    
    -- Validation check results (business rules)
    check_fio_match BOOLEAN,
    check_doc_date_valid BOOLEAN,
    check_doc_type_known BOOLEAN,
    check_single_doc_type BOOLEAN,
    
    -- Final verdict and business errors
    verdict BOOLEAN NOT NULL,
    errors JSONB DEFAULT '[]'::jsonb,
    
    -- Overall status (KEY!)
    status VARCHAR(20) NOT NULL,
    CONSTRAINT runs_status_check CHECK (status IN ('success', 'business_error', 'client_error', 'server_error')),
    
    -- System/Client error details (RFC 7807)
    error_category VARCHAR(20),
    error_code VARCHAR(100),
    error_message TEXT,
    error_detail TEXT,
    error_retryable BOOLEAN,
    
    -- Timing
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    processing_time_seconds FLOAT,
    
    -- Tracing
    trace_id UUID
);

-- Indexes
CREATE INDEX idx_runs_status ON runs(status);
CREATE INDEX idx_runs_verdict ON runs(verdict);
CREATE INDEX idx_runs_error_code ON runs(error_code) WHERE error_code IS NOT NULL;
CREATE INDEX idx_runs_external_request_id ON runs(external_request_id);
CREATE INDEX idx_runs_external_iin ON runs(external_iin);
CREATE INDEX idx_runs_created_at ON runs(created_at DESC);
CREATE INDEX idx_runs_trace_id ON runs(trace_id) WHERE trace_id IS NOT NULL;

-- JSONB indexes for error search
CREATE INDEX idx_runs_errors_gin ON runs USING gin(errors);
```

---

## Summary

### Question 1: Multiple Check Failures
**Answer**: Use **hybrid approach**
- ✅ Individual boolean columns (`check_fio_match`, etc.) for fast queries
- ✅ JSONB `errors` array for complete error context
- ✅ Enables both analytics and debugging

### Question 2: RFC 7807 Error Storage
**Answer**: Use **status taxonomy + error fields**
- ✅ `status` column with 4 values: `success`, `business_error`, `client_error`, `server_error`
- ✅ Separate `error_code`, `error_message`, `error_category`, `error_retryable` for system errors
- ✅ Keep `verdict` and `errors` JSONB for business validation failures
- ✅ Enables clear separation: HTTP errors vs business rule violations

### Key Insight
**Business errors are NOT system errors**:
- Business error: HTTP 200, `verdict=false`, `errors=[{code: "FIO_MISMATCH"}]`
- System error: HTTP 5xx, RFC 7807 ProblemDetail
- Client error: HTTP 4xx, RFC 7807 ProblemDetail

Your database schema should reflect this distinction using the `status` field as the primary discriminator.

---

*Created: 2025-12-08*  
*Updated for: RB-OCR PostgreSQL Schema Design*
