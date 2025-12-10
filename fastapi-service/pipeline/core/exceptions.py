"""Custom exception hierarchy for RB-OCR.

This module defines a comprehensive exception hierarchy following industry best practices.
All exceptions inherit from BaseError and provide structured error information compatible
with RFC 7807 Problem Details for HTTP APIs.
"""

from typing import Any, Optional
from enum import Enum


class ErrorCategory(str, Enum):
    """Error categories for classification and monitoring."""

    CLIENT_ERROR = "client_error"
    SERVER_ERROR = "server_error"
    EXTERNAL_SERVICE = "external_service"
    VALIDATION = "validation"
    BUSINESS_LOGIC = "business_logic"


class BaseError(Exception):
    """Base exception for all RB-OCR errors.

    All custom exceptions should inherit from this class to ensure consistent
    error handling and structured error responses.

    Attributes:
        message: Human-readable error message
        error_code: Application-specific error code
        category: Error category for classification
        http_status: HTTP status code to return
        details: Additional context (dict)
        retryable: Whether the operation can be retried
    """

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
        """Convert to RFC 7807 Problem Details format.

        Returns:
            Dict containing standardized error information
        """
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
    """Base for client errors (4xx).

    Represents errors caused by invalid client requests.
    These are not retryable by default.
    """

    def __init__(self, message: str, error_code: str, **kwargs):
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.CLIENT_ERROR,
            http_status=kwargs.pop("http_status", 400),
            retryable=False,
            **kwargs,
        )


class ValidationError(ClientError):
    """Input validation failed (422 Unprocessable Entity).

    Raised when request parameters fail validation rules.

    Args:
        message: Validation error description
        field: Name of the field that failed validation
        details: Additional validation context
    """

    def __init__(self, message: str, field: str, **kwargs):
        additional_details = kwargs.pop("details", {})
        additional_details["field"] = field
        super().__init__(
            message=message,
            error_code="VALIDATION_ERROR",
            http_status=422,
            details=additional_details,
            **kwargs,
        )


class ResourceNotFoundError(ClientError):
    """Resource not found (404).

    Raised when a requested resource does not exist.

    Args:
        resource_type: Type of resource (e.g., "S3 File", "Document")
        resource_id: Identifier of the missing resource
    """

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} not found",
            error_code="RESOURCE_NOT_FOUND",
            http_status=404,
            details={"resource_type": resource_type, "resource_id": resource_id},
        )


class PayloadTooLargeError(ClientError):
    """Payload too large (413).

    Raised when uploaded file exceeds size limits.

    Args:
        max_size_mb: Maximum allowed size in MB
        actual_size_mb: Actual file size in MB
    """

    def __init__(self, max_size_mb: int, actual_size_mb: float):
        super().__init__(
            message=f"File too large: {actual_size_mb:.2f}MB (max: {max_size_mb}MB)",
            error_code="PAYLOAD_TOO_LARGE",
            http_status=413,
            details={"max_size_mb": max_size_mb, "actual_size_mb": actual_size_mb},
        )


class RateLimitError(ClientError):
    """Rate limit exceeded (429).

    Raised when client exceeds request rate limits.
    This error is retryable after the specified delay.

    Args:
        retry_after: Seconds to wait before retrying
    """

    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded",
            error_code="RATE_LIMIT_EXCEEDED",
            http_status=429,
            details={"retry_after": retry_after},
        )
        self.retryable = True  # Set after init to avoid duplicate


class ServerError(BaseError):
    """Base for server errors (5xx).

    Represents internal server errors or failures in external dependencies.
    Some server errors may be retryable.
    """

    def __init__(self, message: str, error_code: str, **kwargs):
        super().__init__(
            message=message,
            error_code=error_code,
            category=ErrorCategory.SERVER_ERROR,
            http_status=kwargs.pop("http_status", 500),
            retryable=kwargs.pop("retryable", False),
            **kwargs,
        )


class ExternalServiceError(ServerError):
    """External service failure (502 Bad Gateway / 504 Gateway Timeout).

    Raised when external services (OCR, LLM, S3) fail or timeout.
    These errors are retryable as they may be transient.

    Args:
        service_name: Name of the external service
        error_type: Type of error ("timeout", "unavailable", "error", "circuit_open")
        details: Additional error context
    """

    def __init__(self, service_name: str, error_type: str, **kwargs):
        # Determine HTTP status based on error type
        if error_type == "timeout":
            http_status = 504
        elif error_type == "circuit_open":
            http_status = 503
        else:
            http_status = 502

        additional_details = kwargs.pop("details", {})
        additional_details.update(
            {
                "service": service_name,
                "error_type": error_type,
            }
        )

        super().__init__(
            message=f"{service_name} service {error_type}",
            error_code=f"{service_name.upper()}_{error_type.upper()}",
            http_status=http_status,
            retryable=True,
            details=additional_details,
            **kwargs,
        )


class BusinessRuleViolation(Exception):
    """Business rule violation - returns 200 OK with verdict=False.

    This is NOT an HTTP error. It represents a successful request where
    the document failed business validation rules (FIO mismatch, doc too old, etc.).

    The API returns HTTP 200 with verdict=False and structured error codes.

    Args:
        error_code: Business rule error code (e.g., "FIO_MISMATCH")
        details: Additional context about the violation
    """

    def __init__(self, error_code: str, details: Optional[str] = None):
        self.error_code = error_code
        self.details = details
        super().__init__(f"{error_code}: {details or ''}")
