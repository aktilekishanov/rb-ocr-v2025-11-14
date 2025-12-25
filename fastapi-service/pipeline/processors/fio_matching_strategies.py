"""FIO matching strategies - focused, testable matching functions.

This module breaks down the complex FIO matching logic into small,
single-purpose strategy functions. Each strategy attempts one specific
type of match and returns immediately on success or None on failure.

Benefits:
- Each function < 25 lines
- Cyclomatic complexity < 5
- Easy to test individually
- Clear separation of concerns
"""

import difflib
from dataclasses import asdict
from typing import Optional, Tuple


def try_exact_canonical_match(
    app_variants: dict[str, str],
    doc_variants: dict[str, str],
    doc_variant_key: str,
    app_parts: "NameParts",
) -> Optional[Tuple[bool, dict]]:
    """Strategy 1: Try exact canonical match for detected variant.

    Attempts to match the specific variant type (FULL, LF, L_IO, etc.)
    using exact string comparison after normalization.

    Args:
        app_variants: Application FIO variants
        doc_variants: Document FIO variants
        doc_variant_key: Detected variant type (e.g., "FULL", "LF")
        app_parts: Parsed application name parts

    Returns:
        (True, metadata) if matched, None if not matched
    """
    from pipeline.processors.fio_matching import equals_canonical

    app_val = app_variants.get(doc_variant_key)
    doc_val = doc_variants.get(doc_variant_key)

    if not app_val or not doc_val:
        return None

    if equals_canonical(doc_val, app_val):
        return True, {
            "matched_variant": doc_variant_key,
            "meta_variant_value": app_val,
            "doc_variant_value": doc_val,
            "meta_parse": asdict(app_parts),
            "fuzzy_score": 100,
        }

    return None


def try_lio_raw_form_match(
    app_variants: dict[str, str],
    doc_fio: str,
    doc_variant_key: str,
    app_parts: "NameParts",
) -> Optional[Tuple[bool, dict]]:
    """Strategy 2: Try L_IO raw form normalization match.

    Handles case where document has "Иванов И О" (with spaces)
    and we need to match "Иванов ИО".

    Args:
        app_variants: Application FIO variants
        doc_fio: Raw document FIO string
        doc_variant_key: Detected variant type
        app_parts: Parsed application name parts

    Returns:
        (True, metadata) if matched, None if not matched
    """
    if doc_variant_key != "L_IO":
        return None

    from pipeline.processors.fio_matching import equals_canonical, normalize_for_name

    app_lio = app_variants.get("L_IO")
    if not app_lio:
        return None

    doc_norm = normalize_for_name(doc_fio)

    if equals_canonical(doc_norm, app_lio):
        return True, {
            "matched_variant": "L_IO",
            "meta_variant_value": app_lio,
            "doc_variant_value": doc_norm,
            "meta_parse": asdict(app_parts),
            "fuzzy_score": 100,
        }

    return None


def try_li_special_case_match(
    app_variants: dict[str, str],
    doc_variants: dict[str, str],
    doc_variant_key: str,
    app_parts: "NameParts",
) -> Optional[Tuple[bool, dict]]:
    """Strategy 3: Accept L_I match when app has FULL parts.

    Special case: Document has "Иванов И" but application has
    full name "Иванов Иван Иванович". Accept the match
    because the document might have abbreviated the name.

    Args:
        app_variants: Application FIO variants
        doc_variants: Document FIO variants
        doc_variant_key: Detected variant type
        app_parts: Parsed application name parts

    Returns:
        (True, metadata) if matched, None if not matched
    """
    if doc_variant_key != "L_IO":
        return None

    from pipeline.processors.fio_matching import equals_canonical

    # Only apply if app has full name (last, first, patronymic)
    if not (app_parts.last and app_parts.first and app_parts.patro):
        return None

    doc_li = doc_variants.get("L_I")
    app_li = app_variants.get("L_I")

    if not doc_li or not app_li:
        return None

    if equals_canonical(doc_li, app_li):
        return True, {
            "matched_variant": "L_IO",
            "meta_variant_value": app_li,
            "doc_variant_value": doc_li,
            "meta_parse": asdict(app_parts),
            "fuzzy_score": 100,
        }

    return None


def try_fuzzy_variant_match(
    app_variants: dict[str, str],
    doc_variants: dict[str, str],
    doc_variant_key: str,
    app_parts: "NameParts",
    fuzzy_threshold: int,
) -> Optional[Tuple[bool, dict]]:
    """Strategy 4: Try fuzzy matching on specific variant.

    Uses Levenshtein distance or SequenceMatcher to find
    approximate matches (e.g., "Иванов" vs "Иваноф").

    Args:
        app_variants: Application FIO variants
        doc_variants: Document FIO variants
        doc_variant_key: Detected variant type
        app_parts: Parsed application name parts
        fuzzy_threshold: Minimum score to accept (0-100)

    Returns:
        (True, metadata) if matched, None if not matched
    """
    app_val = app_variants.get(doc_variant_key)
    doc_val = doc_variants.get(doc_variant_key)

    if not app_val or not doc_val:
        return None

    fuzzy_score = _calculate_fuzzy_score(app_val, doc_val)

    if fuzzy_score >= fuzzy_threshold:
        return True, {
            "matched_variant": doc_variant_key,
            "meta_variant_value": app_val,
            "doc_variant_value": doc_val,
            "meta_parse": asdict(app_parts),
            "fuzzy_score": fuzzy_score,
        }

    return None


def try_fuzzy_raw_match(
    app_fio: str,
    doc_fio: str,
    app_parts: "NameParts",
    fuzzy_threshold: int,
) -> Optional[Tuple[bool, dict]]:
    """Strategy 5: Try fuzzy matching on raw normalized strings.

    Last resort: Compare raw normalized strings when structured
    matching fails. Useful for typos or unusual name formats.

    Args:
        app_fio: Raw application FIO
        doc_fio: Raw document FIO
        app_parts: Parsed application name parts
        fuzzy_threshold: Minimum score to accept

    Returns:
        (True, metadata) if matched, None if not matched
    """
    from pipeline.processors.fio_matching import normalize_for_name

    app_norm = normalize_for_name(app_fio or "")
    doc_norm = normalize_for_name(doc_fio or "")

    fuzzy_score = _calculate_fuzzy_score_token_sort(app_norm, doc_norm)

    if fuzzy_score >= fuzzy_threshold:
        return True, {
            "matched_variant": None,
            "meta_variant_value": None,
            "doc_variant_value": doc_norm,
            "meta_parse": asdict(app_parts),
            "fuzzy_score": fuzzy_score,
        }

    return None


def _calculate_fuzzy_score(a: str, b: str) -> int:
    """Calculate fuzzy similarity score (0-100).

    Uses rapidfuzz if available, falls back to difflib.

    Args:
        a: First string
        b: Second string

    Returns:
        Similarity score from 0 to 100
    """
    try:
        from rapidfuzz import fuzz

        return int(fuzz.ratio(a, b))
    except ImportError:
        return int(round(difflib.SequenceMatcher(None, a, b).ratio() * 100))


def _calculate_fuzzy_score_token_sort(a: str, b: str) -> int:
    """Calculate fuzzy score with token sorting.

    Token sorting helps match "Иванов Иван" with "Иван Иванов".

    Args:
        a: First string
        b: Second string

    Returns:
        Similarity score from 0 to 100
    """
    try:
        from rapidfuzz import fuzz

        return int(fuzz.token_sort_ratio(a, b))
    except ImportError:
        return int(round(difflib.SequenceMatcher(None, a, b).ratio() * 100))


def build_no_match_result(
    app_parts: "NameParts",
    doc_fio: str,
    last_fuzzy_score: Optional[int] = None,
) -> dict:
    """Build result metadata for no-match case.

    Args:
        app_parts: Parsed application name parts
        doc_fio: Raw document FIO
        last_fuzzy_score: Last fuzzy score attempted (if any)

    Returns:
        Metadata dictionary for failed match
    """
    from pipeline.processors.fio_matching import normalize_for_name

    return {
        "matched_variant": None,
        "meta_variant_value": None,
        "doc_variant_value": normalize_for_name(doc_fio),
        "meta_parse": asdict(app_parts),
        "fuzzy_score": last_fuzzy_score,
    }
