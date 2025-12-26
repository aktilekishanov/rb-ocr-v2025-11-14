"""
Document validity policies and helpers for the RB-OCR pipeline.

Encodes business rules for how long different document types remain
valid, and provides utilities to compute validity windows and check
whether a document is still within its allowed period.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from pipeline.config.constants import VALIDITY_OVERRIDES
from pipeline.config.settings import UTC_OFFSET_HOURS
from pipeline.utils.dates import parse_doc_date

# Default validity window
DEFAULT_FIXED_DAYS = 40


def _timezone() -> timezone:
    return timezone(timedelta(hours=UTC_OFFSET_HOURS))


def _format_date(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%d.%m.%Y")


def resolve_policy(doc_type: Any) -> dict[str, Any]:
    if isinstance(doc_type, str):
        dt = doc_type.strip()
        if dt in VALIDITY_OVERRIDES:
            return VALIDITY_OVERRIDES[dt]
    return {"type": "fixed_days", "days": DEFAULT_FIXED_DAYS}


def compute_valid_until(
    doc_type: Any,
    doc_date_str: Any,
) -> tuple[datetime | None, str, int | None, str | None]:
    """
    Compute document validity window based on type and date.

    Args:
      doc_type: Extracted document type (string or arbitrary input).
      doc_date_str: Extracted document date as a raw string.

    Returns:
      A tuple ``(valid_until_dt_with_tz, policy_type, window_days_if_fixed, error)``
      where ``policy_type`` is typically ``"fixed_days"`` and ``error`` is a
      non-empty string if the date could not be parsed.
    """
    tz = _timezone()
    policy = resolve_policy(doc_type)
    ptype = policy.get("type")
    if ptype == "fixed_days":
        days = int(policy.get("days", DEFAULT_FIXED_DAYS))
        parsed_date = parse_doc_date(doc_date_str)
        if parsed_date is None:
            return None, "fixed_days", days, "DOC_DATE_MISSING_OR_INVALID"
        localized_date = parsed_date.replace(tzinfo=tz)
        return localized_date + timedelta(days=days), "fixed_days", days, None
    else:
        # Fallback to default fixed days
        days = DEFAULT_FIXED_DAYS
        parsed_date = parse_doc_date(doc_date_str)
        if parsed_date is None:
            return None, "fixed_days", days, "DOC_DATE_MISSING_OR_INVALID"
        localized_date = parsed_date.replace(tzinfo=tz)
        return localized_date + timedelta(days=days), "fixed_days", days, None


def is_within_validity(
    valid_until_dt: datetime | None, now_dt: datetime | None = None
) -> bool | None:
    """
    Return True/False/None for whether now is within the validity window.

    Args:
      valid_until_dt: Upper bound of the validity window, or None.
      now_dt: Optional reference time; if omitted, current UTC+offset is used.

    Returns:
      True if ``now_dt`` (or current time) is within the window, False if the
      document is too old, or None if no validity bound is available.
    """
    if valid_until_dt is None:
        return None
    now = now_dt or datetime.now(_timezone())
    return now <= valid_until_dt


def format_date(dt: datetime | None) -> str | None:
    return _format_date(dt)
