"""Pydantic request/response schemas for API endpoints."""
from pydantic import BaseModel, Field
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


class ErrorDetail(BaseModel):
    """Represents a single business validation error.
    
    Used in VerifyResponse when verdict=False due to business rule violations
    (e.g., FIO mismatch, document too old). These are NOT HTTP errors.
    """
    code: str = Field(..., description="Error code (e.g., FIO_MISMATCH)")
    message: str | None = Field(None, description="Human-readable message in Russian")
    details: Optional[str] = Field(None, description="Additional context or explanation")


class VerifyResponse(BaseModel):
    """Response from document verification endpoint.
    
    Returns HTTP 200 OK for both successful verification and business rule violations.
    HTTP errors (4xx/5xx) use ProblemDetail format instead.
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
    """Request schema for Kafka event processing endpoint.
    
    This schema is superseded by KafkaEventRequestValidator in api/validators.py
    which includes additional validation logic. This is kept for backward compatibility.
    """
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

