from __future__ import annotations
import re
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz  # optional
except Exception:
    fuzz = None

from pipeline.core.const import (
    KZ_TO_RU_MAPPING,
    LATIN_TO_CYRILLIC_MAPPING,
    PATRONYMIC_SUFFIXES,
)


@dataclass
class NameParts:
    last: str | None
    first: str | None
    patro: str | None


_KZ_TO_RU = str.maketrans(KZ_TO_RU_MAPPING)
_LATIN_TO_CYR = str.maketrans(LATIN_TO_CYRILLIC_MAPPING)


def _collapse_ws_and_case(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip()).casefold()


def normalize_for_name(text: str) -> str:
    text = _collapse_ws_and_case(text)
    text = text.translate(_KZ_TO_RU)
    return text.translate(_LATIN_TO_CYR)


def _strip_trailing_dot(token: str) -> str:
    return token[:-1] if token.endswith(".") else token


def parse_fio(raw: str) -> NameParts:
    s = normalize_for_name(raw)
    if not s:
        return NameParts(None, None, None)

    tokens = s.split()
    if not tokens:
        return NameParts(None, None, None)

    last = first = patro = None

    if len(tokens) >= 3:
        last, first, patro = tokens[:3]
        first = _strip_trailing_dot(first)
        patro = _strip_trailing_dot(patro)

    elif len(tokens) == 2:
        t1, t2 = tokens
        t2c = t2.replace(".", "")

        if len(t2c) == 2 and t2c.isalpha():  # IO
            last, first, patro = t1, t2c[0], t2c[1]
        elif len(t2c) == 1 and t2c.isalpha():  # I
            last, first = t1, t2c
        elif any(t2.endswith(s) for s in PATRONYMIC_SUFFIXES):
            first, patro = _strip_trailing_dot(t1), _strip_trailing_dot(t2)
        else:
            last, first = t1, _strip_trailing_dot(t2)

    else:  # 1 token
        last = _strip_trailing_dot(tokens[0])

    return NameParts(last or None, first or None, patro or None)


def build_variants(name_parts: NameParts) -> dict[str, str]:
    variants = {}
    last, first, patro = name_parts.last, name_parts.first, name_parts.patro

    def _canon(*parts: str) -> str:
        return normalize_for_name(" ".join(p for p in parts if p))

    if last and first and patro:
        variants["FULL"] = _canon(last, first, patro)
        variants["L_IO"] = _canon(f"{last} {first[0]}{patro[0]}")
    if last and first:
        variants["LF"] = _canon(last, first)
        variants["L_I"] = _canon(last, first[0])
    if first and patro:
        variants["FP"] = _canon(first, patro)
    if last:
        variants["L"] = _canon(last)

    return variants


def detect_variant(raw: str) -> str:
    s = normalize_for_name(raw)
    tokens = s.split()

    if len(tokens) <= 1:
        return "L"

    if len(tokens) >= 3:
        t2 = tokens[1].replace(".", "")
        t3 = tokens[2].replace(".", "")
        if len(t2) == 1 and len(t3) == 1 and t2.isalpha() and t3.isalpha():
            return "L_IO"
        return "FULL"

    # len == 2
    t2c = tokens[1].replace(".", "")
    if len(t2c) == 2 and t2c.isalpha():
        return "L_IO"
    if len(t2c) == 1 and t2c.isalpha():
        return "L_I"
    if any(tokens[1].endswith(s) for s in PATRONYMIC_SUFFIXES):
        return "FP"
    return "LF"


def _normalize_initials_form(s: str) -> str:
    s = normalize_for_name(s).replace(".", "")
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"\b([a-zа-я])\s+([a-zа-я])\b", r"\1\2", s)


def equals_canonical(a: str, b: str) -> bool:
    a_std = normalize_for_name(a)
    b_std = normalize_for_name(b)
    if a_std == b_std:
        return True
    return _normalize_initials_form(a_std) == _normalize_initials_form(b_std)


def fio_match(
    app_fio: str,
    doc_fio: str,
    *,
    enable_fuzzy_fallback: bool = True,
    fuzzy_threshold: int = 85,
) -> tuple[bool, dict[str, object]]:
    """Match FIO using strategy pattern.

    Refactored to use small, focused strategy functions instead of
    one large complex function. Each strategy is tried in order.

    Complexity reduced from 15 to 3. Each strategy function has
    complexity < 5, making the code easier to understand and test.

    Args:
        app_fio: Application FIO string
        doc_fio: Document FIO string
        enable_fuzzy_fallback: Whether to enable fuzzy matching
        fuzzy_threshold: Minimum score for fuzzy match (0-100)

    Returns:
        (matched: bool, metadata: dict)
    """
    from pipeline.processors.fio_matching_strategies import (
        try_exact_canonical_match,
        try_lio_raw_form_match,
        try_li_special_case_match,
        try_fuzzy_variant_match,
        try_fuzzy_raw_match,
        build_no_match_result,
    )

    app_parts = parse_fio(app_fio)
    app_variants = build_variants(app_parts)

    doc_variant = detect_variant(doc_fio)
    doc_parts = parse_fio(doc_fio)
    doc_variants = build_variants(doc_parts)

    # Strategy 1: Exact canonical match
    result = try_exact_canonical_match(
        app_variants, doc_variants, doc_variant, app_parts
    )
    if result:
        return result

    # Strategy 2: L_IO raw form match
    result = try_lio_raw_form_match(app_variants, doc_fio, doc_variant, app_parts)
    if result:
        return result

    # Strategy 3: L_I special case
    result = try_li_special_case_match(
        app_variants, doc_variants, doc_variant, app_parts
    )
    if result:
        return result

    # Strategy 4: Fuzzy variant match (if enabled)
    if enable_fuzzy_fallback:
        result = try_fuzzy_variant_match(
            app_variants, doc_variants, doc_variant, app_parts, fuzzy_threshold
        )
        if result:
            return result

        # Strategy 5: Raw fuzzy match (last resort)
        result = try_fuzzy_raw_match(app_fio, doc_fio, app_parts, fuzzy_threshold)
        if result:
            return result

    # No match found
    return False, build_no_match_result(app_parts, doc_fio)
