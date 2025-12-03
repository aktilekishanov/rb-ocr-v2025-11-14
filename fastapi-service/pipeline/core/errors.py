"""
Centralized, stable error codes and helpers for the RB-OCR pipeline.

Defines Russian-language messages for a minimal set of error codes that
are used throughout the orchestrator and processors, plus helpers to
construct error dicts consumed by the UI and final JSON artifacts.
"""

# Minimal, stable error codes for MVP
ERROR_MESSAGES_RU: dict[str, str] = {
    # Acquisition/UI
    "PDF_TOO_MANY_PAGES": "PDF должен содержать не более 3 страниц",
    "FILE_SAVE_FAILED": "Не удалось сохранить файл",
    # OCR
    "OCR_FAILED": "Ошибка распознавания OCR",
    "OCR_FILTER_FAILED": "Ошибка обработки страниц OCR",
    "OCR_EMPTY_PAGES": "Не удалось получить текст страниц из OCR",
    # Doc-type check (LLM)
    "DTC_FAILED": "Ошибка проверки типа документа",
    "MULTIPLE_DOCUMENTS": "Файл содержит несколько типов документов",
    "DTC_PARSE_ERROR": "Некорректный ответ проверки типа документа",
    # Extraction (LLM)
    "EXTRACT_FAILED": "Ошибка извлечения данных LLM",
    "LLM_FILTER_PARSE_ERROR": "Ошибка фильтрации ответа LLM",
    "EXTRACT_SCHEMA_INVALID": "Некорректная схема данных извлечения",
    # Merge/Validation
    "MERGE_FAILED": "Ошибка при формировании итогового JSON",
    "VALIDATION_FAILED": "Ошибка валидации",
    "UNKNOWN_ERROR": "Неизвестная ошибка",
    # Check-derived
    "FIO_MISMATCH": "ФИО не совпадает",
    "FIO_MISSING": "Не удалось извлечь ФИО из документа",
    "DOC_TYPE_UNKNOWN": "Не удалось определить тип документа",
    "DOC_DATE_TOO_OLD": "Устаревшая дата документа",
    "DOC_DATE_MISSING": "Не удалось распознать дату документа",
    "SINGLE_DOC_TYPE_INVALID": "Файл содержит несколько типов документов",
}


def message_for(code: str) -> str | None:
    return ERROR_MESSAGES_RU.get(code)


def make_error(
    code: str, message: str | None = None, details: str | None = None
) -> dict[str, str | None]:
    return {
        "code": code,
        "message": message,
        "details": details,
    }
