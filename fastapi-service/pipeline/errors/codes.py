"""
Centralized error code registry with specifications.

Provides single source of truth for error codes, including Russian messages,
error categories (client/server), and retryability flags.
"""

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True)
class ErrorSpec:
    """Specification for a single error type."""

    code: str
    int_code: int
    message_ru: str  # Russian message for UI
    category: str  # "client_error" or "server_error"
    retryable: bool  # True if request can be retried


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
        12,
        "PDF должен содержать не более 3 страниц",
        "client_error",
        False,
    )
    MULTIPLE_DOCUMENTS = ErrorSpec(
        "MULTIPLE_DOCUMENTS",
        3,
        "Файл содержит несколько типов документов",
        "client_error",
        False,
    )

    # ========================================
    # SERVER ERRORS (retryable)
    # ========================================
    FILE_SAVE_FAILED = ErrorSpec(
        "FILE_SAVE_FAILED",
        13,
        "Не удалось сохранить файл",
        "server_error",
        True,
    )
    OCR_FAILED = ErrorSpec(
        "OCR_FAILED",
        20,
        "Ошибка распознавания OCR",
        "server_error",
        True,
    )
    OCR_FILTER_FAILED = ErrorSpec(
        "OCR_FILTER_FAILED",
        21,
        "Ошибка обработки страниц OCR",
        "server_error",
        True,
    )
    OCR_EMPTY_PAGES = ErrorSpec(
        "OCR_EMPTY_PAGES",
        22,
        "Не удалось получить текст страниц из OCR",
        "server_error",
        True,
    )
    DTC_PARSE_ERROR = ErrorSpec(
        "DTC_PARSE_ERROR",
        24,
        "Некорректный ответ проверки типа документа",
        "server_error",
        True,
    )
    LLM_FILTER_PARSE_ERROR = ErrorSpec(
        "LLM_FILTER_PARSE_ERROR",
        26,
        "Ошибка фильтрации ответа LLM",
        "server_error",
        True,
    )
    EXTRACT_SCHEMA_INVALID = ErrorSpec(
        "EXTRACT_SCHEMA_INVALID",
        27,
        "Некорректная схема данных извлечения",
        "server_error",
        True,
    )
    VALIDATION_FAILED = ErrorSpec(
        "VALIDATION_FAILED",
        29,
        "Ошибка валидации",
        "server_error",
        False,
    )

    # ========================================
    # BUSINESS RULE ERRORS (not used in fail_and_finalize)
    # ========================================
    FIO_MISMATCH = ErrorSpec(
        "FIO_MISMATCH",
        4,
        "ФИО не совпадает",
        "client_error",
        False,
    )
    FIO_MISSING = ErrorSpec(
        "FIO_MISSING",
        11,
        "Не удалось извлечь ФИО из документа",
        "client_error",
        False,
    )
    DOC_TYPE_UNKNOWN = ErrorSpec(
        "DOC_TYPE_UNKNOWN",
        6,
        "Не удалось определить тип документа",
        "client_error",
        False,
    )
    DOC_DATE_TOO_OLD = ErrorSpec(
        "DOC_DATE_TOO_OLD",
        2,
        "Устаревшая дата документа",
        "client_error",
        False,
    )
    DOC_DATE_MISSING = ErrorSpec(
        "DOC_DATE_MISSING",
        10,
        "Не удалось распознать дату документа",
        "client_error",
        False,
    )

    # ========================================
    # FALLBACK
    # ========================================
    UNKNOWN_ERROR = ErrorSpec(
        "UNKNOWN_ERROR",
        0,
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
        return ErrorSpec(code, 0, f"Ошибка: {code}", "server_error", False)


def make_error(
    code: str, message: str | None = None, details: str | None = None
) -> dict[str, str | int | None]:
    """Create error dict with integer code, message, and details.

    Looks up the integer code from the string code in ErrorCode.
    """
    spec = ErrorCode.get_spec(code)
    return {
        "code": spec.int_code,
        "message": message,
        "details": details,
    }
