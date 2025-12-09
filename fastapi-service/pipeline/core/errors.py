"""
Centralized error code registry with specifications.

Provides single source of truth for error codes, including Russian messages,
error categories (client/server), and retryability flags.
"""

from enum import Enum
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorSpec:
    """Specification for a single error type."""
    code: str
    message_ru: str              # Russian message for UI
    category: str                # "client_error" or "server_error"
    retryable: bool              # True if request can be retried


class ErrorCode(Enum):
    """Centralized error code registry.
    
    Single source of truth for all error specifications.
    Usage:
        error_spec = ErrorCode.get_spec("OCR_FAILED")
        print(error_spec.message_ru, error_spec.category, error_spec.retryable)
    """
    
    # ========================================
    # CLIENT ERRORS (not retryable)
    # ========================================
    PDF_TOO_MANY_PAGES = ErrorSpec(
        "PDF_TOO_MANY_PAGES",
        "PDF должен содержать не более 3 страниц",
        "client_error",
        False,
    )
    FILE_SAVE_FAILED = ErrorSpec(
        "FILE_SAVE_FAILED",
        "Не удалось сохранить файл",
        "client_error",
        False,
    )
    MULTIPLE_DOCUMENTS = ErrorSpec(
        "MULTIPLE_DOCUMENTS",
        "Файл содержит несколько типов документов",
        "client_error",
        False,
    )
    
    # ========================================
    # SERVER ERRORS (retryable)
    # ========================================
    OCR_FAILED = ErrorSpec(
        "OCR_FAILED",
        "Ошибка распознавания OCR",
        "server_error",
        True,
    )
    OCR_FILTER_FAILED = ErrorSpec(
        "OCR_FILTER_FAILED",
        "Ошибка обработки страниц OCR",
        "server_error",
        True,
    )
    OCR_EMPTY_PAGES = ErrorSpec(
        "OCR_EMPTY_PAGES",
        "Не удалось получить текст страниц из OCR",
        "server_error",
        True,
    )
    DTC_FAILED = ErrorSpec(
        "DTC_FAILED",
        "Ошибка проверки типа документа",
        "server_error",
        True,
    )
    DTC_PARSE_ERROR = ErrorSpec(
        "DTC_PARSE_ERROR",
        "Некорректный ответ проверки типа документа",
        "server_error",
        True,
    )
    EXTRACT_FAILED = ErrorSpec(
        "EXTRACT_FAILED",
        "Ошибка извлечения данных LLM",
        "server_error",
        True,
    )
    LLM_FILTER_PARSE_ERROR = ErrorSpec(
        "LLM_FILTER_PARSE_ERROR",
        "Ошибка фильтрации ответа LLM",
        "server_error",
        True,
    )
    EXTRACT_SCHEMA_INVALID = ErrorSpec(
        "EXTRACT_SCHEMA_INVALID",
        "Некорректная схема данных извлечения",
        "server_error",
        True,
    )
    MERGE_FAILED = ErrorSpec(
        "MERGE_FAILED",
        "Ошибка при формировании итогового JSON",
        "server_error",
        False,  # Usually indicates bug, not transient
    )
    VALIDATION_FAILED = ErrorSpec(
        "VALIDATION_FAILED",
        "Ошибка валидации",
        "server_error",
        False,  # Usually indicates bug, not transient
    )
    
    # ========================================
    # BUSINESS RULE ERRORS (not used in fail_and_finalize)
    # ========================================
    FIO_MISMATCH = ErrorSpec(
        "FIO_MISMATCH",
        "ФИО не совпадает",
        "client_error",  # User provided wrong data
        False,
    )
    FIO_MISSING = ErrorSpec(
        "FIO_MISSING",
        "Не удалось извлечь ФИО из документа",
        "client_error",
        False,
    )
    DOC_TYPE_UNKNOWN = ErrorSpec(
        "DOC_TYPE_UNKNOWN",
        "Не удалось определить тип документа",
        "client_error",
        False,
    )
    DOC_DATE_TOO_OLD = ErrorSpec(
        "DOC_DATE_TOO_OLD",
        "Устаревшая дата документа",
        "client_error",
        False,
    )
    DOC_DATE_MISSING = ErrorSpec(
        "DOC_DATE_MISSING",
        "Не удалось распознать дату документа",
        "client_error",
        False,
    )
    
    # ========================================
    # FALLBACK
    # ========================================
    UNKNOWN_ERROR = ErrorSpec(
        "UNKNOWN_ERROR",
        "Неизвестная ошибка",
        "server_error",
        False,
    )
    
    @classmethod
    def get_spec(cls, code: str) -> ErrorSpec:
        """Get error specification by code string.
        
        Returns:
            ErrorSpec with category, message, and retryability.
            Returns default spec for unknown codes.
        """
        for error in cls:
            if error.value.code == code:
                return error.value
        # Default for unknown errors
        return ErrorSpec(code, f"Ошибка: {code}", "server_error", False)


# Keep existing helper functions for backward compatibility
def message_for(code: str) -> str | None:
    """Get Russian message for error code."""
    spec = ErrorCode.get_spec(code)
    return spec.message_ru


def make_error(
    code: str, message: str | None = None, details: str | None = None
) -> dict[str, str | None]:
    """Create error dict with code, message, and details."""
    return {
        "code": code,
        "message": message,
        "details": details,
    }
