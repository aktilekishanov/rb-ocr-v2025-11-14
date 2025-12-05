# FULL STEP-BY-STEP IMPLEMENTATION PLAN

## Overview

This plan provides a **detailed, actionable roadmap** to implement the TO-BE error handling architecture. The implementation is broken down into 5 phases, executed sequentially to minimize risk.

**Total Duration**: 15 working days
**Risk Level**: Medium
**Team Size**: 1-2 developers

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Phase 1: Foundation (Days 1-3)](#phase-1-foundation)
3. [Phase 2: Resilience Patterns (Days 4-7)](#phase-2-resilience-patterns)
4. [Phase 3: API Layer (Days 8-10)](#phase-3-api-layer)
5. [Phase 4: Observability (Days 11-12)](#phase-4-observability)
6. [Phase 5: Testing & Deployment (Days 13-15)](#phase-5-testing--deployment)
7. [Rollback Strategy](#rollback-strategy)
8. [Monitoring & Success Metrics](#monitoring--success-metrics)

---

## 1. Prerequisites

### 1.1 Development Environment

```bash
# Ensure Python 3.11+
python --version  # Should be 3.11+

# Install additional dependencies
pip install httpx tenacity prometheus-client python-json-logger

# Or update requirements.txt
echo "httpx>=0.25.0" >> requirements.txt
echo "tenacity>=8.2.0" >> requirements.txt
echo "prometheus-client>=0.19.0" >> requirements.txt
echo "python-json-logger>=2.0.7" >> requirements.txt
```

### 1.2 Testing Environment

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-cov pytest-mock httpx

# Verify test setup
pytest --version
```

### 1.3 File Structure Overview

```
fastapi-service/
├── pipeline/
│   ├── core/
│   │   ├── exceptions.py         [NEW] Phase 1
│   │   ├── errors.py              [KEEP] Existing error codes
│   │   └── logging_config.py     [NEW] Phase 4
│   ├── resilience/
│   │   ├── __init__.py           [NEW] Phase 2
│   │   ├── circuit_breaker.py     [NEW] Phase 2
│   │   └── retry.py               [NEW] Phase 2
│   ├── clients/
│   │   ├── llm_client.py          [MODIFY] Phase 2
│   │   └── tesseract_async_client.py [MODIFY] Phase 2
│   └── orchestrator.py            [MODIFY] Phase 3
├── api/
│   ├── validators.py              [NEW] Phase 1
│   ├── schemas.py                 [MODIFY] Phase 1
│   └── middleware/
│       ├── __init__.py           [NEW] Phase 3
│       └── exception_handler.py   [NEW] Phase 3
├── services/
│   ├── processor.py               [MODIFY] Phase 3
│   └── s3_client.py               [MODIFY] Phase 2
├── tests/
│   ├── unit/
│   │   ├── test_exceptions.py     [NEW] Phase 1
│   │   ├── test_validators.py     [NEW] Phase 1
│   │   ├── test_circuit_breaker.py [NEW] Phase 2
│   │   └── test_retry.py          [NEW] Phase 2
│   └── integration/
│       ├── test_error_flows.py    [NEW] Phase 5
│       └── test_resilience.py     [NEW] Phase 5
└── main.py                        [MODIFY] Phase 3
```

---

## Phase 1: Foundation (Days 1-3)

**Goal**: Create exception hierarchy and input validation framework

### Day 1: Exception Hierarchy

#### Step 1.1: Create Base Exceptions

**File**: `pipeline/core/exceptions.py` [NEW]

```python
"""Custom exception hierarchy for RB-OCR."""

from typing import Any, Optional
from enum import Enum


class ErrorCategory(str, Enum):
    """Error categories for classification."""
    CLIENT_ERROR = "client_error"
    SERVER_ERROR = "server_error"
    EXTERNAL_SERVICE = "external_service"
    VALIDATION = "validation"
    BUSINESS_LOGIC = "business_logic"


class BaseError(Exception):
    """Base exception for all RB-OCR errors."""
    
    def __init__(
        self,
        message: str,
        error_code: str,
        category: ErrorCategory,
        http_status: int,
        details: Optional[dict[str, Any]] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.category = category
        self.http_status = http_status
        self.details = details or {}
        self.retryable = retryable
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to RFC 7807 Problem Details format."""
        return {
            "type": f"/errors/{self.error_code}",
            "title": self.message,
            "status": self.http_status,
            "code": self.error_code,
            "detail": self.details.get("detail"),
            "category": self.category.value,
            "retryable": self.retryable,
        }


class ClientError(BaseError):
    """Base for client errors (4xx)."""
    def __init__(self, message: str, error_code: str, **kwargs):
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.CLIENT_ERROR,
            http_status=kwargs.pop("http_status", 400),
            retryable=False,
            **kwargs
        )


class ValidationError(ClientError):
    """Input validation failed (422)."""
    def __init__(self, message: str, field: str, **kwargs):
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            http_status=422,
            details={"field": field, **kwargs.get("details", {})},
        )


class ResourceNotFoundError(ClientError):
    """Resource not found (404)."""
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} not found",
            error_code="RESOURCE_NOT_FOUND",
            http_status=404,
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class ServerError(BaseError):
    """Base for server errors (5xx)."""
    def __init__(self, message: str, error_code: str, **kwargs):
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.SERVER_ERROR,
            http_status=kwargs.pop("http_status", 500),
            retryable=kwargs.pop("retryable", False),
            **kwargs
        )


class ExternalServiceError(ServerError):
    """External service failure (502/504)."""
    def __init__(self, service_name: str, error_type: str, **kwargs):
        http_status = 504 if error_type == "timeout" else 502
        super().__init__(
            message=f"{service_name} service {error_type}",
            error_code=f"{service_name.upper()}_{error_type.upper()}",
            http_status=http_status,
            retryable=True,
            details={"service": service_name, "error_type": error_type, **kwargs.get("details", {})},
        )


class BusinessRuleViolation(Exception):
    """Business rule violation - returns 200 with verdict=False."""
    def __init__(self, error_code: str, details: Optional[str] = None):
        self.error_code = error_code
        self.details = details
        super().__init__(f"{error_code}: {details or ''}")
```

**Verification**:
```bash
# Run unit tests
pytest tests/unit/test_exceptions.py -v
```

**Test File**: `tests/unit/test_exceptions.py` [NEW]

```python
"""Unit tests for exception hierarchy."""

import pytest
from pipeline.core.exceptions import (
    BaseError, ClientError, ValidationError, 
    ResourceNotFoundError, ServerError, ExternalServiceError,
    ErrorCategory
)


def test_base_error_to_dict():
    """Test BaseError converts to RFC 7807 format."""
    error = BaseError(
        message="Test error",
        error_code="TEST_ERROR",
        category=ErrorCategory.CLIENT_ERROR,
        http_status=400,
        details={"detail": "Additional info"},
        retryable=False,
    )
    
    result = error.to_dict()
    
    assert result["type"] == "/errors/TEST_ERROR"
    assert result["title"] == "Test error"
    assert result["status"] == 400
    assert result["code"] == "TEST_ERROR"
    assert result["category"] == "client_error"
    assert result["retryable"] is False


def test_validation_error():
    """Test ValidationError has correct defaults."""
    error = ValidationError(
        message="Invalid FIO",
        field="fio",
        details={"received": ""}
    )
    
    assert error.http_status == 422
    assert error.error_code == "VALIDATION_ERROR"
    assert error.details["field"] == "fio"


def test_resource_not_found_error():
    """Test ResourceNotFoundError formatting."""
    error = ResourceNotFoundError(
        resource_type="S3 File",
        resource_id="documents/sample.pdf"
    )
    
    assert error.http_status == 404
    assert error.message == "S3 File not found"
    assert error.details["resource_type"] == "S3 File"


def test_external_service_error_timeout():
    """Test ExternalServiceError with timeout."""
    error = ExternalServiceError(
        service_name="OCR",
        error_type="timeout",
        details={"timeout_seconds": 300}
    )
    
    assert error.http_status == 504
    assert error.error_code == "OCR_TIMEOUT"
    assert error.retryable is True


def test_external_service_error_generic():
    """Test ExternalServiceError with generic error."""
    error = ExternalServiceError(
        service_name="LLM",
        error_type="error"
    )
    
    assert error.http_status == 502
    assert error.error_code == "LLM_ERROR"
    assert error.retryable is True
```

---

### Day 2: Input Validation

#### Step 1.2: Create Validators

**File**: `api/validators.py` [NEW]

```python
"""Input validation utilities."""

from pydantic import BaseModel, Field, field_validator
from fastapi import UploadFile
from typing import Optional, Set
import re

from pipeline.core.exceptions import ValidationError


# Constants
ALLOWED_CONTENT_TYPES: Set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}

MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


class VerifyRequest(BaseModel):
    """Validated request for document verification."""
    
    fio: str = Field(
        ...,
        min_length=3,
        max_length=200,
        description="Full name of applicant"
    )
    
    @field_validator('fio')
    @classmethod
    def validate_fio(cls, v: str) -> str:
        """Validate FIO format."""
        # Allow Cyrillic, Latin, spaces, hyphens
        if not re.match(r'^[А-Яа-яЁёA-Za-z\s\-]+$', v):
            raise ValueError("FIO must contain only letters, spaces, and hyphens")
        
        # Remove excessive whitespace
        v = re.sub(r'\s+', ' ', v.strip())
        
        # Must have at least 2 words
        if len(v.split()) < 2:
            raise ValueError("FIO must contain at least first and last name")
        
        return v


async def validate_upload_file(file: UploadFile) -> None:
    """Validate uploaded file."""
    
    # Check content type
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            message=f"Invalid file type: {file.content_type}",
            field="file",
            details={
                "allowed_types": list(ALLOWED_CONTENT_TYPES),
                "received_type": file.content_type,
            }
        )
    
    # Check file size
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset
    
    if file_size > MAX_FILE_SIZE_BYTES:
        raise ValidationError(
            message=f"File too large: {file_size / 1024 / 1024:.2f}MB",
            field="file",
            details={
                "max_size_mb": MAX_FILE_SIZE_MB,
                "actual_size_mb": round(file_size / 1024 / 1024, 2),
            }
        )
```

**Verification**:
```bash
pytest tests/unit/test_validators.py -v
```

**Test File**: `tests/unit/test_validators.py` [NEW]

```python
"""Unit tests for input validators."""

import pytest
import io
from fastapi import UploadFile
from pydantic import ValidationError as PydanticValidationError

from api.validators import VerifyRequest, validate_upload_file
from pipeline.core.exceptions import ValidationError


def test_verify_request_valid_fio():
    """Test valid FIO passes validation."""
    request = VerifyRequest(fio="Иванов Иван Иванович")
    assert request.fio == "Иванов Иван Иванович"


def test_verify_request_fio_too_short():
    """Test FIO too short raises error."""
    with pytest.raises(PydanticValidationError):
        VerifyRequest(fio="A")


def test_verify_request_fio_single_word():
    """Test single-word FIO raises error."""
    with pytest.raises(PydanticValidationError):
        VerifyRequest(fio="Иванов")


def test_verify_request_fio_invalid_chars():
    """Test FIO with numbers raises error."""
    with pytest.raises(PydanticValidationError):
        VerifyRequest(fio="Иванов123")


@pytest.mark.asyncio
async def test_validate_upload_file_valid():
    """Test valid file passes validation."""
    content = b"PDF content"
    file = UploadFile(
        filename="test.pdf",
        file=io.BytesIO(content),
        headers={"content-type": "application/pdf"}
    )
    
    # Should not raise
    await validate_upload_file(file)


@pytest.mark.asyncio
async def test_validate_upload_file_invalid_type():
    """Test invalid file type raises error."""
    content = b"Text content"
    file = UploadFile(
        filename="test.txt",
        file=io.BytesIO(content),
        headers={"content-type": "text/plain"}
    )
    
    with pytest.raises(ValidationError) as exc_info:
        await validate_upload_file(file)
    
    assert exc_info.value.http_status == 422
    assert exc_info.value.details["field"] == "file"


@pytest.mark.asyncio
async def test_validate_upload_file_too_large():
    """Test file exceeding size limit raises error."""
    # Create 51MB file
    content = b"x" * (51 * 1024 * 1024)
    file = UploadFile(
        filename="large.pdf",
        file=io.BytesIO(content),
        headers={"content-type": "application/pdf"}
    )
    
    with pytest.raises(ValidationError) as exc_info:
        await validate_upload_file(file)
    
    assert exc_info.value.http_status == 422
    assert "too large" in exc_info.value.message.lower()
```

---

### Day 3: Enhanced Response Schemas

#### Step 1.3: Update API Schemas

**File**: `api/schemas.py` [MODIFY]

```python
"""Pydantic request/response schemas for API endpoints."""

from pydantic import BaseModel, Field
from typing import List, Optional, Any


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs."""
    
    type: str = Field(..., description="URI reference identifying the problem type")
    title: str = Field(..., description="Short, human-readable summary")
    status: int = Field(..., description="HTTP status code")
    detail: Optional[str] = Field(None, description="Human-readable explanation")
    instance: Optional[str] = Field(None, description="URI reference (run_id)")
    
    # Extension members
    code: str = Field(..., description="Application error code")
    category: str = Field(..., description="Error category")
    retryable: bool = Field(default=False, description="Whether retryable")
    retry_after: Optional[int] = Field(None, description="Seconds to wait before retry")
    trace_id: Optional[str] = Field(None, description="Distributed tracing ID")


class ErrorDetail(BaseModel):
    """Verification error detail."""
    code: str = Field(..., description="Error code")
    message: str | None = Field(None, description="Human-readable message in Russian")
    details: Optional[str] = Field(None, description="Additional context")


class VerifyResponse(BaseModel):
    """Enhanced response from verification endpoint."""
    run_id: str = Field(..., description="Unique run identifier (UUID)")
    verdict: bool = Field(..., description="True if all checks pass")
    errors: List[ErrorDetail] = Field(default_factory=list)
    processing_time_seconds: float = Field(..., description="Processing duration")
    trace_id: Optional[str] = Field(None, description="Tracing correlation ID")


class KafkaEventRequest(BaseModel):
    """Request schema for Kafka event processing endpoint."""
    request_id: int = Field(..., gt=0)
    s3_path: str = Field(..., min_length=1, max_length=1024)
    iin: int = Field(..., ge=100000000000, le=999999999999)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    second_name: Optional[str] = Field(None, max_length=100)
    
    @field_validator('s3_path')
    @classmethod
    def validate_s3_path(cls, v: str) -> str:
        """Prevent directory traversal."""
        if '..' in v or v.startswith('/'):
            raise ValueError("Invalid S3 path")
        if '.' not in v:
            raise ValueError("S3 path must include file extension")
        return v
```

---

## Phase 2: Resilience Patterns (Days 4-7)

**Goal**: Implement circuit breaker and retry logic

### Day 4-5: Circuit Breaker

#### Step 2.1: Create Circuit Breaker

**File**: `pipeline/resilience/circuit_breaker.py` [NEW]

```python
"""Circuit breaker pattern for external service calls."""

from enum import Enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Any, Optional
import logging

from pipeline.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5
    timeout_seconds: int = 60
    success_threshold: int = 2


class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection."""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN")
            else:
                raise ExternalServiceError(
                    service_name=self.name,
                    error_type="circuit_open",
                    details={
                        "message": "Circuit breaker is OPEN",
                        "retry_after": self._time_until_retry(),
                    }
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return False
        elapsed = datetime.now() - self.last_failure_time
        return elapsed.total_seconds() >= self.config.timeout_seconds
    
    def _time_until_retry(self) -> int:
        if self.last_failure_time is None:
            return 0
        elapsed = datetime.now() - self.last_failure_time
        remaining = self.config.timeout_seconds - elapsed.total_seconds()
        return max(0, int(remaining))
    
    def _on_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                logger.info(f"Circuit breaker '{self.name}' CLOSED")
    
    def _on_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker '{self.name}' re-OPENED")
        elif self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker '{self.name}' OPENED after {self.failure_count} failures")
```

**Verification**:
```bash
pytest tests/unit/test_circuit_breaker.py -v
```

**Test File**: `tests/unit/test_circuit_breaker.py` [NEW]

```python
"""Unit tests for circuit breaker."""

import pytest
import time
from pipeline.resilience.circuit_breaker import (
    CircuitBreaker, CircuitBreakerConfig, CircuitState
)
from pipeline.core.exceptions import ExternalServiceError


def failing_func():
    """Always fails."""
    raise Exception("Service unavailable")


def succeeding_func():
    """Always succeeds."""
    return "success"


def test_circuit_breaker_opens_after_threshold():
    """Test circuit opens after failure threshold."""
    cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
    
    # First 2 failures
    for _ in range(2):
        with pytest.raises(Exception):
            cb.call(failing_func)
    
    assert cb.state == CircuitState.CLOSED
    assert cb.failure_count == 2
    
    # 3rd failure opens circuit
    with pytest.raises(Exception):
        cb.call(failing_func)
    
    assert cb.state == CircuitState.OPEN


def test_circuit_breaker_rejects_when_open():
    """Test circuit rejects requests when open."""
    cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=1))
    
    # Open circuit
    with pytest.raises(Exception):
        cb.call(failing_func)
    
    # Should raise ExternalServiceError
    with pytest.raises(ExternalServiceError) as exc_info:
        cb.call(succeeding_func)
    
    assert exc_info.value.http_status == 502
    assert "circuit_open" in exc_info.value.error_code.lower()


def test_circuit_breaker_half_open_recovery():
    """Test circuit transitions to half-open after timeout."""
    cb = CircuitBreaker("test", CircuitBreakerConfig(
        failure_threshold=1,
        timeout_seconds=1,  # Short timeout for testing
        success_threshold=2
    ))
    
    # Open circuit
    with pytest.raises(Exception):
        cb.call(failing_func)
    
    assert cb.state == CircuitState.OPEN
    
    # Wait for timeout
    time.sleep(1.1)
    
    # First success in HALF_OPEN
    result = cb.call(succeeding_func)
    assert result == "success"
    assert cb.state == CircuitState.HALF_OPEN
    
    # Second success closes circuit
    result = cb.call(succeeding_func)
    assert result == "success"
    assert cb.state == CircuitState.CLOSED
```

---

### Day 6: Retry Logic

**File**: `pipeline/resilience/retry.py` [NEW]

```python
"""Retry with exponential backoff."""

import time
import random
from typing import Callable, Any, Type
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True


def retry_with_backoff(
    func: Callable,
    config: RetryConfig,
    retryable_exceptions: tuple[Type[Exception], ...],
    *args,
    **kwargs
) -> Any:
    """Retry function with exponential backoff."""
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt == config.max_attempts - 1:
                raise
            
            # Calculate delay
            delay = min(
                config.initial_delay_seconds * (config.exponential_base ** attempt),
                config.max_delay_seconds
            )
            
            # Add jitter
            if config.jitter:
                delay = delay * (0.5 + random.random())
            
            logger.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                f"Retrying in {delay:.2f}s..."
            )
            
            time.sleep(delay)
    
    raise last_exception
```

**Verification**:
```bash
pytest tests/unit/test_retry.py -v
```

---

### Day 7: Update Clients

#### Step 2.2: Update LLM Client

**File**: `pipeline/clients/llm_client.py` [MODIFY]

Add imports at the top:
```python
from pipeline.core.exceptions import ExternalServiceError
from pipeline.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from pipeline.resilience.retry import retry_with_backoff, RetryConfig
```

Update the exception handling in `call_fortebank_llm`:
```python
# Replace existing exception handling with:
except urllib.error.HTTPError as e:
    if e.code == 429:
        raise ExternalServiceError(
            service_name="LLM",
            error_type="rate_limit",
            details={"http_code": e.code}
        )
    raise ExternalServiceError(
        service_name="LLM",
        error_type="error",
        details={"http_code": e.code, "reason": str(e.reason)}
    )
except (urllib.error.URLError, ssl.SSLError) as e:
    raise ExternalServiceError(
        service_name="LLM",
        error_type="timeout" if "timeout" in str(e).lower() else "unavailable",
        details={"reason": str(e)}
    )
```

---

## Phase 3: API Layer (Days 8-10)

**Goal**: Implement exception middleware and update endpoints

### Day 8: Exception Middleware

**File**: `api/middleware/exception_handler.py` [NEW]

```python
"""Global exception handling middleware."""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import logging
import uuid

from pipeline.core.exceptions import BaseError
from api.schemas import ProblemDetail

logger = logging.getLogger(__name__)


async def exception_middleware(request: Request, call_next):
    """Global exception handling middleware."""
    
    # Generate trace ID
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    
    try:
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
    
    except BaseError as e:
        logger.error(
            "BaseError occurred",
            extra={
                "trace_id": trace_id,
                "error_code": e.error_code,
                "path": request.url.path,
            },
            exc_info=True
        )
        
        problem = ProblemDetail(
            **e.to_dict(),
            instance=request.url.path,
            trace_id=trace_id,
        )
        
        return JSONResponse(
            status_code=e.http_status,
            content=problem.dict(exclude_none=True),
            headers={"X-Trace-ID": trace_id}
        )
    
    except RequestValidationError as e:
        logger.warning("Validation error", extra={"trace_id": trace_id})
        
        problem = ProblemDetail(
            type="/errors/VALIDATION_ERROR",
            title="Request validation failed",
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_ERROR",
            category="client_error",
            retryable=False,
            instance=request.url.path,
            trace_id=trace_id,
        )
        
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=problem.dict(exclude_none=True),
            headers={"X-Trace-ID": trace_id}
        )
    
    except Exception as e:
        logger.exception("Unexpected error", extra={"trace_id": trace_id})
        
        problem = ProblemDetail(
            type="/errors/INTERNAL_SERVER_ERROR",
            title="Internal server error",
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
            code="INTERNAL_SERVER_ERROR",
            category="server_error",
            retryable=False,
            instance=request.url.path,
            trace_id=trace_id,
        )
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=problem.dict(exclude_none=True),
            headers={"X-Trace-ID": trace_id}
        )
```

---

### Day 9-10: Update Main Endpoints

**File**: `main.py` [MODIFY]

```python
# Add imports
from api.middleware.exception_handler import exception_middleware
from api.validators import validate_upload_file, VerifyRequest

# Register middleware
app.middleware("http")(exception_middleware)

# Update /v1/verify endpoint
@app.post("/v1/verify", response_model=VerifyResponse)
async def verify_document(
    request: Request,
    file: UploadFile = File(...),
    fio: str = Form(...),
):
    """Verify document with comprehensive error handling."""
    
    trace_id = getattr(request.state, "trace_id", None)
    
    # Validate file
    await validate_upload_file(file)
    
    # Validate FIO
    verify_req = VerifyRequest(fio=fio)
    
    # ... rest of existing logic ...
    
    response = VerifyResponse(
        **result,
        trace_id=trace_id,
    )
    return response
```

---

## Phase 4: Observability (Days 11-12)

**Goal**: Implement structured logging

**File**: `pipeline/core/logging_config.py` [NEW]

```python
"""Structured logging configuration."""

import logging
import json
from typing import Any


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
        }
        
        # Add extra fields
        for key in ["trace_id", "run_id", "error_code", "service"]:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False)


def configure_logging():
    """Configure structured logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    
    logger = logging.getLogger()
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
```

Update `main.py` to use structured logging:
```python
from pipeline.core.logging_config import configure_logging

configure_logging()
```

---

## Phase 5: Testing & Deployment (Days 13-15)

### Day 13-14: Integration Tests

**File**: `tests/integration/test_error_flows.py` [NEW]

```bash
# Run integration tests
pytest tests/integration/ -v --cov=api --cov=pipeline
```

Test cases:
- Test 422 validation error on invalid FIO
- Test 404 on S3 file not found
- Test 504 on OCR timeout
- Test 200 with verdict=False on business failure
- Test trace_id in response headers

---

### Day 15: Deployment

#### Deployment Checklist

```markdown
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Code review completed
- [ ] Documentation updated
- [ ] Monitoring dashboards configured
- [ ] Alerting rules defined
- [ ] Rollback plan tested
- [ ] Deployment to staging
- [ ] Smoke tests on staging
- [ ] Deployment to production
- [ ] Monitor error rates for 24h
```

---

## Rollback Strategy

### Immediate Rollback (< 5 minutes)

```bash
# Revert to previous deployment
git revert <commit-hash>
docker-compose up -d --build
```

### Partial Rollback

If specific phase fails:
1. Keep exception hierarchy (Phase 1) - backward compatible
2. Disable resilience patterns (Phase 2) - feature flag
3. Revert middleware (Phase 3) - use old error handling

---

## Monitoring & Success Metrics

### Dashboards to Create

1. **Error Rate Dashboard**
   - 2xx rate
   - 4xx rate (by error code)
   - 5xx rate (by error code)
   - Circuit breaker state

2. **Performance Dashboard**
   - Request duration
   - Retry count
   - Circuit breaker trips

3. **Client Dashboard**
   - Validation errors (422)
   - Not found errors (404)
   - Rate limit errors (429)

### Success Criteria (Week 1 Post-Deployment)

```
✅ 5xx rate < 5% (down from 20%)
✅ False alerts reduced by 70%+
✅ No security incidents
✅ Client error rate categorized correctly
✅ Mean time to debug < 90 minutes
```

---

## Summary

**Total Effort**:
- 24 files to create/modify
- ~2,500 lines of code
- ~1,000 lines of tests
- 15 working days

**Key Milestones**:
- Day 3: Exception hierarchy complete
- Day 7: Resilience patterns ready
- Day 10: API layer updated
- Day 15: Production deployment

**Risk Mitigation**:
- Incremental deployment
- Comprehensive testing
- Clear rollback plan
- Monitoring from day 1
