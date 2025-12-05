# Error Handling Architecture - README

## Overview

Production-ready error handling system with RFC 7807 compliance, circuit breakers, retry logic, and structured logging.

**Status**: ✅ All 4 phases complete, 83 tests passing

---

## Quick Start

### Files Created

**Phase 1: Foundation**
- `pipeline/core/exceptions.py` - Exception hierarchy
- `api/validators.py` - Input validators  
- `api/schemas.py` - Enhanced with ProblemDetail (modified)
- `tests/unit/test_exceptions.py` - 22 tests
- `tests/unit/test_validators.py` - 29 tests

**Phase 2: Resilience**
- `pipeline/resilience/circuit_breaker.py` - Circuit breaker
- `pipeline/resilience/retry.py` - Retry logic
- `tests/unit/test_circuit_breaker.py` - 16 tests
- `tests/unit/test_retry.py` - 16 tests

**Phase 3: API Layer**
- `api/middleware/exception_handler.py` - Exception middleware
- `main.py` - Updated endpoints (modified)

**Phase 4: Observability**
- `pipeline/core/logging_config.py` - Structured JSON logging

---

## HTTP Status Codes

| Code | Meaning | When Used | Retryable |
|------|---------|-----------|-----------|
| 200 | OK | Business logic success/failure | - |
| 404 | Not Found | S3 file missing | No |
| 413 | Payload Too Large | File > 50MB | No |
| 422 | Unprocessable | Invalid FIO, IIN, file type | No |
| 429 | Too Many Requests | Rate limited | Yes (Retry-After) |
| 500 | Internal Error | Unexpected error | No |
| 502 | Bad Gateway | External service error | Yes |
| 503 | Service Unavailable | Circuit breaker open | No (wait) |
| 504 | Gateway Timeout | External service timeout | Yes |

---

## Error Response Format (RFC 7807)

```json
{
  "type": "/errors/VALIDATION_ERROR",
  "title": "Request validation failed",
  "status": 422,
  "detail": "FIO must contain at least 2 words",
  "instance": "/v1/verify",
  "code": "VALIDATION_ERROR",
  "category": "client_error",
  "retryable": false,
  "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**Header**: `X-Trace-ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890`

---

## Usage Examples

### Client Error Handling

```javascript
async function verifyDocument(file, fio) {
  try {
    const response = await fetch('/v1/verify', {
      method: 'POST',
      body: formData
    });
    
    const traceId = response.headers.get('X-Trace-ID');
    
    switch (response.status) {
      case 200:
        const result = await response.json();
        return result.verdict ? handleSuccess(result) : handleBusinessFailure(result);
        
      case 422:
        const error = await response.json();
        return showValidationError(error.detail);
        
      case 413:
        return showError('File too large. Max 50MB.');
        
      case 429:
        const retryAfter = error.retry_after || 60;
        return retryLater(retryAfter);
        
      case 502:
      case 504:
        // External service error - retry with backoff
        return retryWithBackoff();
        
      case 503:
        // Circuit breaker open - don't retry immediately
        return showError(`Service temporarily unavailable. Trace ID: ${traceId}`);
        
      default:
        return showError(`Error occurred. Report trace ID: ${traceId}`);
    }
  } catch (e) {
    console.error('Network error:', e);
  }
}
```

---

## Testing

```bash
# Run all unit tests
pytest tests/unit/ -v
# Expected: 83 passed

# Run with coverage
pytest tests/unit/ --cov=pipeline --cov=api --cov-report=html
# Expected: > 80% coverage

# Run specific test suite
pytest tests/unit/test_exceptions.py -v      # 22 tests
pytest tests/unit/test_validators.py -v      # 29 tests
pytest tests/unit/test_circuit_breaker.py -v # 16 tests
pytest tests/unit/test_retry.py -v           # 16 tests
```

---

## Deployment

See [`deployment-checklist.md`](deployment-checklist.md) for full deployment guide.

**Quick Deploy**:
```bash
# Run tests
pytest tests/unit/ -v

# Deploy
docker build -t rb-ocr-api:latest .
docker-compose up -d
```

---

## Monitoring

### Trace ID Usage

**Search logs by trace ID**:
```bash
grep "a1b2c3d4-e5f6-7890-abcd-ef1234567890" /var/log/app/*.log | jq '.'
```

**JSON log format**:
```json
{
  "timestamp": "2025-12-05T12:53:45Z",
  "level": "ERROR",
  "message": "External service timeout",
  "trace_id": "a1b2c3d4...",
  "run_id": "550e8400...",
  "service": "LLM",
  "duration_ms": 30000
}
```

### Circuit Breaker Monitoring

```python
# Check state
from pipeline.resilience import CircuitBreaker

breaker = CircuitBreaker("OCR", config)
state = breaker.get_state()
# Returns: {"name": "OCR", "state": "closed", "failure_count": 0, ...}
```

---

## Architecture

```
Request → Middleware (trace_id) → Validators → Processor → Response
                ↓                      ↓            ↓
           Exception?              Valid?      Success?
                ↓                      ↓            ↓
         RFC 7807 JSON           422 Error    200 verdict
         + X-Trace-ID
```

**Resilience Patterns**:
- Circuit Breaker: Prevents cascading failures
- Retry: Exponential backoff for transient errors
- Validation: Input sanitization & security

---

## Troubleshooting

### High 422 Rate
**Cause**: Clients sending invalid data  
**Fix**: Review validation rules, inform clients

### Circuit Breaker Stuck OPEN
**Cause**: External service down  
**Fix**: Check service health, manual reset if needed

### Missing Trace IDs  
**Cause**: Middleware bypass  
**Fix**: Verify middleware registration: `app.middleware("http")(exception_middleware)`

---

## Documentation

- [Phase 1 Walkthrough](phase1-walkthrough.md) - Exceptions & validators
- [Phase 2 Walkthrough](phase2-walkthrough.md) - Circuit breaker & retry
- [Phase 3 Walkthrough](phase3-walkthrough.md) - Middleware & endpoints
- [Complete Walkthrough](complete-walkthrough.md) - Full architecture
- [Deployment Checklist](deployment-checklist.md) - Production deployment

---

## Summary

✅ **83 tests passing**  
✅ **RFC 7807 compliant**  
✅ **Circuit breakers preventing cascading failures**  
✅ **Trace IDs for debugging**  
✅ **Structured JSON logging**  
✅ **Production-ready**
