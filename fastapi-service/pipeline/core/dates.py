"""
Utilities for date/time parsing and timezone handling.

Provides helpers for parsing document dates in various formats and
managing timezone-aware datetime objects for the RB-OCR pipeline.
"""

from datetime import datetime, timedelta, timezone
from typing import Any


def parse_iso_timestamp(timestamp_string: str | None) -> datetime | None:
    """Parse ISO format timestamp string.

    Handles ISO 8601 format timestamps commonly used for system timestamps
    (e.g., "2025-12-10T14:30:00+05:00", "2025-12-10T09:30:00Z").

    Args:
        timestamp_string: ISO format timestamp string, or None

    Returns:
        datetime object or None if parsing fails or input is None

    Example:
        >>> parse_iso_timestamp("2025-12-10T14:30:00+05:00")
        datetime.datetime(2025, 12, 10, 14, 30, tzinfo=...)
        >>> parse_iso_timestamp(None)
        None
        >>> parse_iso_timestamp("invalid")
        None
    """
    if not timestamp_string:
        return None
    try:
        return datetime.fromisoformat(timestamp_string)
    except (ValueError, AttributeError):
        return None


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
