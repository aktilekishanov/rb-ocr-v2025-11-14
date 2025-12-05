"""Unit tests for exception hierarchy."""

import pytest
from pipeline.core.exceptions import (
    BaseError,
    ClientError,
    ValidationError,
    ResourceNotFoundError,
    PayloadTooLargeError,
    RateLimitError,
    ServerError,
    ExternalServiceError,
    BusinessRuleViolation,
    ErrorCategory,
)


class TestBaseError:
    """Tests for BaseError class."""
    
    def test_base_error_creation(self):
        """Test BaseError can be created with all parameters."""
        error = BaseError(
            message="Test error",
            error_code="TEST_ERROR",
            category=ErrorCategory.CLIENT_ERROR,
            http_status=400,
            details={"detail": "Additional info", "field": "test"},
            retryable=False,
        )
        
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.category == ErrorCategory.CLIENT_ERROR
        assert error.http_status == 400
        assert error.details == {"detail": "Additional info", "field": "test"}
        assert error.retryable is False
    
    def test_base_error_to_dict(self):
        """Test BaseError converts to RFC 7807 format."""
        error = BaseError(
            message="Test error",
            error_code="TEST_ERROR",
            category=ErrorCategory.CLIENT_ERROR,
            http_status=400,
            details={"detail": "Additional context"},
            retryable=False,
        )
        
        result = error.to_dict()
        
        assert result["type"] == "/errors/TEST_ERROR"
        assert result["title"] == "Test error"
        assert result["status"] == 400
        assert result["code"] == "TEST_ERROR"
        assert result["category"] == "client_error"
        assert result["detail"] == "Additional context"
        assert result["retryable"] is False
    
    def test_base_error_default_details(self):
        """Test BaseError with no details provided."""
        error = BaseError(
            message="Test",
            error_code="TEST",
            category=ErrorCategory.SERVER_ERROR,
            http_status=500,
        )
        
        assert error.details == {}
        assert error.retryable is False


class TestClientError:
    """Tests for ClientError and subclasses."""
    
    def test_client_error_defaults(self):
        """Test ClientError has correct defaults."""
        error = ClientError(
            message="Client error",
            error_code="CLIENT_ERROR"
        )
        
        assert error.http_status == 400
        assert error.category == ErrorCategory.CLIENT_ERROR
        assert error.retryable is False
    
    def test_client_error_custom_status(self):
        """Test ClientError can override HTTP status."""
        error = ClientError(
            message="Not found",
            error_code="NOT_FOUND",
            http_status=404
        )
        
        assert error.http_status == 404


class TestValidationError:
    """Tests for ValidationError."""
    
    def test_validation_error_basic(self):
        """Test ValidationError with basic parameters."""
        error = ValidationError(
            message="Invalid FIO",
            field="fio"
        )
        
        assert error.http_status == 422
        assert error.error_code == "VALIDATION_ERROR"
        assert error.category == ErrorCategory.CLIENT_ERROR
        assert error.details["field"] == "fio"
        assert error.retryable is False
    
    def test_validation_error_with_details(self):
        """Test ValidationError with additional details."""
        error = ValidationError(
            message="Invalid FIO format",
            field="fio",
            details={"received": "", "expected": "At least 2 words"}
        )
        
        assert error.details["field"] == "fio"
        assert error.details["received"] == ""
        assert error.details["expected"] == "At least 2 words"
    
    def test_validation_error_to_dict(self):
        """Test ValidationError RFC 7807 format."""
        error = ValidationError(
            message="Invalid input",
            field="email"
        )
        
        result = error.to_dict()
        assert result["status"] == 422
        assert result["code"] == "VALIDATION_ERROR"


class TestResourceNotFoundError:
    """Tests for ResourceNotFoundError."""
    
    def test_resource_not_found_basic(self):
        """Test ResourceNotFoundError with basic parameters."""
        error = ResourceNotFoundError(
            resource_type="S3 File",
            resource_id="documents/sample.pdf"
        )
        
        assert error.http_status == 404
        assert error.error_code == "RESOURCE_NOT_FOUND"
        assert error.message == "S3 File not found"
        assert error.details["resource_type"] == "S3 File"
        assert error.details["resource_id"] == "documents/sample.pdf"
    
    def test_resource_not_found_message(self):
        """Test ResourceNotFoundError message formatting."""
        error = ResourceNotFoundError(
            resource_type="Document",
            resource_id="12345"
        )
        
        assert "Document not found" in error.message


class TestPayloadTooLargeError:
    """Tests for PayloadTooLargeError."""
    
    def test_payload_too_large_basic(self):
        """Test PayloadTooLargeError with basic parameters."""
        error = PayloadTooLargeError(
            max_size_mb=50,
            actual_size_mb=75.5
        )
        
        assert error.http_status == 413
        assert error.error_code == "PAYLOAD_TOO_LARGE"
        assert "75.50MB" in error.message
        assert "max: 50MB" in error.message
        assert error.details["max_size_mb"] == 50
        assert error.details["actual_size_mb"] == 75.5


class TestRateLimitError:
    """Tests for RateLimitError."""
    
    def test_rate_limit_default(self):
        """Test RateLimitError with default retry_after."""
        error = RateLimitError()
        
        assert error.http_status == 429
        assert error.error_code == "RATE_LIMIT_EXCEEDED"
        assert error.retryable is True
        assert error.details["retry_after"] == 60
    
    def test_rate_limit_custom_retry(self):
        """Test RateLimitError with custom retry_after."""
        error = RateLimitError(retry_after=120)
        
        assert error.details["retry_after"] == 120


class TestServerError:
    """Tests for ServerError."""
    
    def test_server_error_defaults(self):
        """Test ServerError has correct defaults."""
        error = ServerError(
            message="Internal error",
            error_code="INTERNAL_ERROR"
        )
        
        assert error.http_status == 500
        assert error.category == ErrorCategory.SERVER_ERROR
        assert error.retryable is False
    
    def test_server_error_retryable(self):
        """Test ServerError can be marked as retryable."""
        error = ServerError(
            message="Database unavailable",
            error_code="DB_UNAVAILABLE",
            retryable=True
        )
        
        assert error.retryable is True


class TestExternalServiceError:
    """Tests for ExternalServiceError."""
    
    def test_external_service_timeout(self):
        """Test ExternalServiceError with timeout."""
        error = ExternalServiceError(
            service_name="OCR",
            error_type="timeout",
            details={"timeout_seconds": 300}
        )
        
        assert error.http_status == 504
        assert error.error_code == "OCR_TIMEOUT"
        assert error.message == "OCR service timeout"
        assert error.retryable is True
        assert error.details["service"] == "OCR"
        assert error.details["error_type"] == "timeout"
        assert error.details["timeout_seconds"] == 300
    
    def test_external_service_unavailable(self):
        """Test ExternalServiceError with unavailable service."""
        error = ExternalServiceError(
            service_name="LLM",
            error_type="unavailable"
        )
        
        assert error.http_status == 502
        assert error.error_code == "LLM_UNAVAILABLE"
        assert error.retryable is True
    
    def test_external_service_error(self):
        """Test ExternalServiceError with generic error."""
        error = ExternalServiceError(
            service_name="S3",
            error_type="error",
            details={"reason": "Access denied"}
        )
        
        assert error.http_status == 502
        assert error.error_code == "S3_ERROR"
        assert error.details["reason"] == "Access denied"
    
    def test_external_service_circuit_open(self):
        """Test ExternalServiceError with circuit breaker open."""
        error = ExternalServiceError(
            service_name="OCR",
            error_type="circuit_open"
        )
        
        assert error.http_status == 503
        assert error.error_code == "OCR_CIRCUIT_OPEN"
        assert error.retryable is True


class TestBusinessRuleViolation:
    """Tests for BusinessRuleViolation."""
    
    def test_business_rule_basic(self):
        """Test BusinessRuleViolation with basic parameters."""
        error = BusinessRuleViolation(
            error_code="FIO_MISMATCH"
        )
        
        assert error.error_code == "FIO_MISMATCH"
        assert error.details is None
        assert "FIO_MISMATCH" in str(error)
    
    def test_business_rule_with_details(self):
        """Test BusinessRuleViolation with details."""
        error = BusinessRuleViolation(
            error_code="DOC_DATE_TOO_OLD",
            details="Document dated 2020-01-01, must be within 6 months"
        )
        
        assert error.error_code == "DOC_DATE_TOO_OLD"
        assert error.details == "Document dated 2020-01-01, must be within 6 months"
        assert "DOC_DATE_TOO_OLD" in str(error)
        assert "2020-01-01" in str(error)


class TestErrorCategory:
    """Tests for ErrorCategory enum."""
    
    def test_error_category_values(self):
        """Test ErrorCategory has expected values."""
        assert ErrorCategory.CLIENT_ERROR.value == "client_error"
        assert ErrorCategory.SERVER_ERROR.value == "server_error"
        assert ErrorCategory.EXTERNAL_SERVICE.value == "external_service"
        assert ErrorCategory.VALIDATION.value == "validation"
        assert ErrorCategory.BUSINESS_LOGIC.value == "business_logic"
