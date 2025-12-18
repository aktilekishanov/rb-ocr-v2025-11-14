"""Pydantic request/response schemas for API endpoints."""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

from pipeline.core.config import (
    IIN_LENGTH,
    NAME_MAX_LENGTH,
    S3_PATH_MAX_LENGTH,
    FIO_MIN_LENGTH,
    FIO_MAX_LENGTH,
    FIO_MIN_WORDS,
)
import re


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details for HTTP APIs.

    This standardized error format provides structured, machine-readable
    error information for HTTP API responses.

    See: https://www.rfc-editor.org/rfc/rfc7807
    """

    type: str = Field(..., description="URI reference identifying the problem type")
    title: str = Field(..., description="Short, human-readable summary of the problem")
    status: int = Field(..., description="HTTP status code for this problem")
    detail: Optional[str] = Field(
        None, description="Human-readable explanation specific to this occurrence"
    )
    instance: Optional[str] = Field(
        None,
        description="URI reference identifying this specific occurrence (e.g., request path)",
    )

    # Extension members (allowed by RFC 7807)
    code: str = Field(..., description="Application-specific error code")
    category: str = Field(
        ..., description="Error category (client_error, server_error, etc.)"
    )
    retryable: bool = Field(
        default=False, description="Whether the request can be retried"
    )
    trace_id: Optional[str] = Field(
        None, description="Distributed tracing ID for correlation across services"
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
                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            }
        }


class VerifyRequest(BaseModel):
    """Validated request for document verification.

    Validates that FIO contains only valid characters and has at least 2 words.
    """

    fio: str = Field(
        ...,
        min_length=FIO_MIN_LENGTH,
        max_length=FIO_MAX_LENGTH,
        description="Full name of applicant (Cyrillic or Latin)",
    )

    @field_validator("fio")
    @classmethod
    def validate_fio(cls, fio_value: str) -> str:
        """Validate FIO format.

        Rules:
        - Must contain only letters (Cyrillic/Latin), spaces, and hyphens
        - Must have at least 2 words (first and last name)
        - Whitespace is normalized

        Args:
            fio_value: FIO string to validate

        Returns:
            Normalized FIO string

        Raises:
            ValueError: If validation fails
        """
        if not re.match(r"^[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІіA-Za-z\s\-]+$", fio_value):
            raise ValueError(
                "FIO must contain only letters (Cyrillic, Latin, or Kazakh), spaces, and hyphens"
            )

        fio_value = re.sub(r"\s+", " ", fio_value.strip())

        if len(fio_value.split()) < FIO_MIN_WORDS:
            raise ValueError(
                "FIO must contain at least first and last name (minimum 2 words)"
            )

        return fio_value


class KafkaEventQueryParams(BaseModel):
    request_id: int = Field(
        ...,
        gt=0,
        description="Unique request identifier from Kafka event (must be positive)",
    )
    s3_path: str = Field(
        ...,
        min_length=1,
        max_length=S3_PATH_MAX_LENGTH,
        description="S3 object key/path to the document",
    )
    iin: str = Field(
        ...,
        min_length=IIN_LENGTH,
        max_length=IIN_LENGTH,
        description="Individual Identification Number (exactly 12 digits, can start with 0)",
    )
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX_LENGTH,
        description="Applicant's first name",
    )
    last_name: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX_LENGTH,
        description="Applicant's last name",
    )
    second_name: str | None = Field(
        None,
        max_length=NAME_MAX_LENGTH,
        description="Applicant's patronymic/middle name (optional)",
    )

    @field_validator("iin")
    @classmethod
    def validate_iin(cls, iin_value: str) -> str:
        """Validate IIN is exactly 12 digits.

        Raises:
            ValueError: If IIN is not exactly 12 digits
        """
        if not iin_value.isdigit():
            raise ValueError("IIN must contain only digits")
        if len(iin_value) != IIN_LENGTH:
            raise ValueError(
                f"IIN must be exactly {IIN_LENGTH} digits, got {len(iin_value)}"
            )
        return iin_value

    @field_validator("s3_path")
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
        if ".." in s3_path_value:
            raise ValueError("S3 path cannot contain '..' (directory traversal)")

        # Security: Prevent absolute paths
        if s3_path_value.startswith("/"):
            raise ValueError("S3 path cannot start with '/' (absolute path)")

        # Format: Must have file extension
        if "." not in s3_path_value:
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
                "second_name": "Иванович",
            }
        }


class ErrorDetail(BaseModel):
    """A single business validation error.
    Used in VerifyResponse when verdict=False due to business rule violations
    The error code is self-documenting and maps to specific business rules.
    """

    code: str = Field(
        ..., description="Error code (e.g., FIO_MISMATCH, DOCUMENT_TOO_OLD)"
    )


class VerifyResponse(BaseModel):
    """Response from document verification endpoint.

    Returns HTTP 200 OK for both successful verification and business rule violations.
    HTTP errors (4xx/5xx) use ProblemDetail format instead.
    """

    request_id: Optional[int] = Field(
        None, description="Echoed request identifier from input (if provided)"
    )
    run_id: str = Field(..., description="Unique run identifier (UUID)")
    verdict: bool = Field(..., description="True if all checks pass")
    errors: List[ErrorDetail] = Field(
        default_factory=list,
        description="List of business validation errors (empty if verdict=True)",
    )
    processing_time_seconds: float = Field(
        ..., description="Processing duration in seconds"
    )
    trace_id: Optional[str] = Field(
        None, description="Distributed tracing ID (matches X-Trace-ID header)"
    )

    class Config:
        # Exclude None values from JSON output
        json_encoders = {type(None): lambda v: None}

    def dict(self, **kwargs):
        """Override dict to exclude None values."""
        kwargs.setdefault("exclude_none", True)
        return super().dict(**kwargs)

    def model_dump(self, **kwargs):
        """Override model_dump to exclude None values."""
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(**kwargs)

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "request_id": "670e8499-r29c-41d4-a786-446655441111",
                    "run_id": "550e8400-e29b-41d4-a716-446655440000",
                    "verdict": True,
                    "errors": [],
                    "processing_time_seconds": 12.4,
                    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                },
                {
                    "request_id": "670e8499-r29c-41d4-a786-446655441111",
                    "run_id": "550e8400-e29b-41d4-a716-446655440001",
                    "verdict": False,
                    "errors": [
                        {
                            "code": "FIO_MISMATCH",
                        }
                    ],
                    "processing_time_seconds": 11.8,
                    "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567891",
                },
            ]
        }


class KafkaEventRequest(BaseModel):
    request_id: int = Field(
        ...,
        gt=0,
        description="Unique request identifier from Kafka event (must be positive)",
    )
    s3_path: str = Field(
        ...,
        min_length=1,
        max_length=S3_PATH_MAX_LENGTH,
        description="S3 object key/path to the document",
    )
    iin: str = Field(
        ...,
        min_length=IIN_LENGTH,
        max_length=IIN_LENGTH,
        description="Individual Identification Number (exactly 12 digits, can start with 0)",
    )
    first_name: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX_LENGTH,
        description="Applicant's first name",
    )
    last_name: str = Field(
        ...,
        min_length=1,
        max_length=NAME_MAX_LENGTH,
        description="Applicant's last name",
    )
    second_name: str | None = Field(
        None,
        max_length=NAME_MAX_LENGTH,
        description="Applicant's patronymic/middle name (optional)",
    )

    @field_validator("iin")
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

    @field_validator("s3_path")
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
        if ".." in s3_path_value:
            raise ValueError("S3 path cannot contain '..' (directory traversal)")

        # Security: Prevent absolute paths
        if s3_path_value.startswith("/"):
            raise ValueError("S3 path cannot start with '/' (absolute path)")

        # Format: Must have file extension
        if "." not in s3_path_value:
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
                "second_name": "Иванович",
            }
        }


class DatabaseHealth(BaseModel):
    """Database connection status."""

    status: str = Field(..., description="Connection status (connected/disconnected)")
    latency_ms: float | None = Field(
        None, description="Connection latency in milliseconds"
    )
    error: str | None = Field(None, description="Error message if disconnected")


class HealthResponse(BaseModel):
    """System health status response."""

    status: str = Field(..., description="Overall system status (healthy/unhealthy)")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    database: DatabaseHealth = Field(..., description="Database connection status")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "service": "rb-ocr-api",
                "version": "1.0.0",
                "database": {
                    "status": "connected",
                    "latency_ms": 1.76,
                    "error": None,
                },
            }
        }
