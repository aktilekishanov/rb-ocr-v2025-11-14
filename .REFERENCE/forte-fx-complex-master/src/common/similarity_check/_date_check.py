from datetime import datetime
from typing import Optional

_ACCEPTED_INPUT_FORMATS = ("%d.%m.%Y", "%Y-%m-%d")

def _normalize_date(value: Optional[str]) -> str:
    """
    Normalize supported date strings to ISO 'YYYY-MM-DD'.
    Unknown/empty/None -> "" (empty string).
    """
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    for fmt in _ACCEPTED_INPUT_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # If not parseable, return original trimmed (lowercased to be consistent)
    return s.lower()

def compare_dates(left: Optional[str], right: Optional[str]) -> bool:
    """
    Compare two dates with normalization.
    Empty equals empty. Otherwise exact match after normalization.
    """
    nl = _normalize_date(left)
    nr = _normalize_date(right)
    return nl == nr
