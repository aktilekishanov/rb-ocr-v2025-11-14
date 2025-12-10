"""Pydantic request/response schemas for API endpoints."""
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs.
    
    This standardized error format provides structured, machine-readable
    error information for HTTP API responses.
    
    See: https://www.rfc-editor.org/rfc/rfc7807
    """
    
    type: str = Field(
        ...,
        description="URI reference identifying the problem type"
    )
    title: str = Field(
        ...,
        description="Short, human-readable summary of the problem"
    )
    status: int = Field(
        ...,
        description="HTTP status code for this problem"
    )
    detail: Optional[str] = Field(
        None,
        description="Human-readable explanation specific to this occurrence"
    )
    instance: Optional[str] = Field(
        None,
        description="URI reference identifying this specific occurrence (e.g., request path)"
    )
    
    # Extension members (allowed by RFC 7807)
    code: str = Field(
        ...,
        description="Application-specific error code"
    )
    category: str = Field(
        ...,
        description="Error category (client_error, server_error, etc.)"
    )
    retryable: bool = Field(
        default=False,
        description="Whether the request can be retried"
    )
    retry_after: Optional[int] = Field(
        None,
        description="Seconds to wait before retrying (for 429 responses)"
    )
    trace_id: Optional[str] = Field(
        None,
        description="Distributed tracing ID for correlation across services"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "/errors/VALIDATION_ERROR",
                "title": "Request validation failed",
                "status": 422,
                "detail": "FIO must contain at least 2 words",
                "instance": "/v1/verify",
                "code": "VALIDATION_ERROR",
                "category": "client_error",
                "retryable": False,
                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
            }
        }


class KafkaEventQueryParams(BaseModel):
    """Query parameter schema for GET endpoint version of Kafka event processing.
    
    Validates all input fields for security and data integrity:
    - request_id: Must be positive integer
    - iin: Must be valid 12-digit Individual Identification Number
    - s3_path: Security checks for path traversal, file extension requirement
    - name fields: Length constraints to prevent abuse
    """
    request_id: int = Field(..., gt=0, description="Unique request identifier from Kafka event (must be positive)")
    s3_path: str = Field(..., min_length=1, max_length=1024, description="S3 object key/path to the document")
    iin: str = Field(..., min_length=12, max_length=12, description="Individual Identification Number (exactly 12 digits, can start with 0)")
    first_name: str = Field(..., min_length=1, max_length=100, description="Applicant's first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Applicant's last name")
    second_name: str | None = Field(None, max_length=100, description="Applicant's patronymic/middle name (optional)")
    
    @field_validator('iin')
    @classmethod
    def validate_iin(cls, iin_value: str) -> str:
        """Validate IIN is exactly 12 digits.
        
        Raises:
            ValueError: If IIN is not exactly 12 digits
        """
        if not iin_value.isdigit():
            raise ValueError("IIN must contain only digits")
        if len(iin_value) != 12:
            raise ValueError(f"IIN must be exactly 12 digits, got {len(iin_value)}")
        return iin_value
    
    @field_validator('s3_path')
    @classmethod
    def validate_s3_path(cls, s3_path_value: str) -> str:
        """Validate S3 path for security and format.
        
        Security checks:
        - Prevent directory traversal attacks (..)
        - Prevent absolute paths (/)
        - Require file extension
        
        Raises:
            ValueError: If path fails validation
        """
        # Security: Prevent directory traversal
        if '..' in s3_path_value:
            raise ValueError("S3 path cannot contain '..' (directory traversal)")
        
        # Security: Prevent absolute paths
        if s3_path_value.startswith('/'):
            raise ValueError("S3 path cannot start with '/' (absolute path)")
        
        # Format: Must have file extension
        if '.' not in s3_path_value:
            raise ValueError("S3 path must include file extension (e.g., .pdf, .jpg)")
        
        return s3_path_value
    
    class Config:
        json_schema_extra = {
            "example": {
                "request_id": 123123,
                "s3_path": "documents/2024/sample.pdf",
                "iin": "021223504060",
                "first_name": "Иван",
                "last_name": "Иванов",
                "second_name": "Иванович"
            }
        }


class ErrorDetail(BaseModel):
    """Represents a single business validation error.
    
    Used in VerifyResponse when verdict=False due to business rule violations
    (e.g., FIO mismatch, document too old). These are NOT HTTP errors.
    
    The error code is self-documenting and maps to specific business rules.
    Additional fields (message, details) can be added in future if needed.
    """
    code: str = Field(..., description="Error code (e.g., FIO_MISMATCH, DOCUMENT_TOO_OLD)")


class VerifyResponse(BaseModel):
    """Response from document verification endpoint.
    
    Returns HTTP 200 OK for both successful verification and business rule violations.
    HTTP errors (4xx/5xx) use ProblemDetail format instead.
    
    Note: trace_id will be omitted if None (only during local testing).
    """
    run_id: str = Field(..., description="Unique run identifier (UUID)")
    verdict: bool = Field(..., description="True if all checks pass")
    errors: List[ErrorDetail] = Field(
        default_factory=list,
        description="List of business validation errors (empty if verdict=True)"
    )
    processing_time_seconds: float = Field(..., description="Processing duration in seconds")
    trace_id: Optional[str] = Field(
        None,
        description="Distributed tracing ID (matches X-Trace-ID header)"
    )
    
    class Config:
        # Exclude None values from JSON output
        json_encoders = {type(None): lambda v: None}
    
    def dict(self, **kwargs):
        """Override dict to exclude None values."""
        kwargs.setdefault('exclude_none', True)
        return super().dict(**kwargs)
    
    def model_dump(self, **kwargs):
        """Override model_dump to exclude None values."""
        kwargs.setdefault('exclude_none', True)
        return super().model_dump(**kwargs)

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "description": "Successful verification",
                    "value": {
                        "run_id": "550e8400-e29b-41d4-a716-446655440000",
                        "verdict": True,
                        "errors": [],
                        "processing_time_seconds": 12.4,
                        "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                    }
                },
                {
                    "description": "Business validation failed",
                    "value": {
                        "run_id": "550e8400-e29b-41d4-a716-446655440001",
                        "verdict": False,
                        "errors": [
                            {
                                "code": "FIO_MISMATCH",
                                "message": "ФИО не совпадает",
                                "details": "Expected: 'Иванов Иван', Got: 'Петров Петр'"
                            }
                        ],
                        "processing_time_seconds": 11.8,
                        "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567891"
                    }
                }
            ]
        }


class KafkaEventRequest(BaseModel):
    """Request schema for Kafka event processing endpoint with comprehensive validation.
    
    Validates all input fields for security and data integrity:
    - request_id: Must be positive integer
    - iin: Must be valid 12-digit Individual Identification Number
    - s3_path: Security checks for path traversal, file extension requirement
    - name fields: Length constraints to prevent abuse
    """
    request_id: int = Field(..., gt=0, description="Unique request identifier from Kafka event (must be positive)")
    s3_path: str = Field(..., min_length=1, max_length=1024, description="S3 object key/path to the document")
    iin: str = Field(..., min_length=12, max_length=12, description="Individual Identification Number (exactly 12 digits, can start with 0)")
    first_name: str = Field(..., min_length=1, max_length=100, description="Applicant's first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="Applicant's last name")
    second_name: str | None = Field(None, max_length=100, description="Applicant's patronymic/middle name (optional)")
    
    @field_validator('iin')
    @classmethod
    def validate_iin(cls, iin_value: str) -> str:
        """Validate IIN is exactly 12 digits.
        
        Raises:
            ValueError: If IIN is not exactly 12 digits
        """
        if not iin_value.isdigit():
            raise ValueError("IIN must contain only digits")
        if len(iin_value) != 12:
            raise ValueError(f"IIN must be exactly 12 digits, got {len(iin_value)}")
        return iin_value
    
    @field_validator('s3_path')
    @classmethod
    def validate_s3_path(cls, s3_path_value: str) -> str:
        """Validate S3 path for security and format.
        
        Security checks:
        - Prevent directory traversal attacks (..)
        - Prevent absolute paths (/)
        - Require file extension
        
        Raises:
            ValueError: If path fails validation
        """
        # Security: Prevent directory traversal
        if '..' in s3_path_value:
            raise ValueError("S3 path cannot contain '..' (directory traversal)")
        
        # Security: Prevent absolute paths
        if s3_path_value.startswith('/'):
            raise ValueError("S3 path cannot start with '/' (absolute path)")
        
        # Format: Must have file extension
        if '.' not in s3_path_value:
            raise ValueError("S3 path must include file extension (e.g., .pdf, .jpg)")
        
        return s3_path_value
    
    class Config:
        json_schema_extra = {
            "example": {
                "request_id": 123123,
                "s3_path": "documents/2024/sample.pdf",
                "iin": "021223504060",
                "first_name": "Иван",
                "last_name": "Иванов",
                "second_name": "Иванович"
            }
        }

