"""
PII-safe logging utilities.

Provides minimal sanitization helpers to prevent sensitive data
leakage in logs while keeping them useful for debugging.
"""


def sanitize_fio(fio: str | None) -> str:
    """
    Sanitize full name (FIO) for logs.

    Rules:
    - None / empty / <4 chars → fully masked
    - Otherwise → first 2 + last 2 chars, middle masked
    """
    if not fio:
        return "***"

    fio = fio.strip()
    if len(fio) < 4:
        return "***"

    return f"{fio[:2]}***{fio[-2:]}"


def sanitize_iin(iin: str | None) -> str:
    """
    Sanitize IIN for logs.

    Rules:
    - None / too short → fully masked
    - Otherwise → first 3 + last 2 digits, middle masked
    """
    if not iin or len(iin) < 5:
        return "***"

    return f"{iin[:3]}***{iin[-2:]}"


def sanitize_request_id(request_id: int | str | None) -> str:
    """
    Normalize request ID for logs.
    """
    return str(request_id) if request_id is not None else "N/A"
