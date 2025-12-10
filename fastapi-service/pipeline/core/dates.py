"""
Date parsing and time utilities shared across the RB-OCR pipeline.
"""

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_doc_date(date_value: Any) -> datetime | None:
    """
    Parse a document date string using common RB formats.

    Args:
      date_value: Raw date value; expected to be a string.

    Returns:
      A ``datetime`` instance if parsing succeeds, otherwise None.
    """
    if not isinstance(date_value, str):
        return None
    cleaned_date_string = date_value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned_date_string, fmt)
        except Exception:
            continue
    return None


def now_utc_plus(hours: int = 5) -> datetime:
    """
    Return current time in UTC+offset (default: RB standard UTC+5).
    """

    tz = timezone(timedelta(hours=hours))
    return datetime.now(tz)
