"""
Date parsing and time utilities shared across the RB-OCR pipeline.
"""

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_doc_date(s: Any) -> datetime | None:
    """
    Parse a document date string using common RB formats.

    Args:
      s: Raw date value; expected to be a string.

    Returns:
      A ``datetime`` instance if parsing succeeds, otherwise None.
    """
    if not isinstance(s, str):
        return None
    s2 = s.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s2, fmt)
        except Exception:
            continue
    return None


def now_utc_plus(hours: int = 5) -> datetime:
    """
    Return current time in UTC+offset (default: RB standard UTC+5).
    """

    tz = timezone(timedelta(hours=hours))
    return datetime.now(tz)
