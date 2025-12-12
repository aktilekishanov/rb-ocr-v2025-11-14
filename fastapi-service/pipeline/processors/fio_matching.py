from __future__ import annotations
import difflib
import re
from dataclasses import asdict, dataclass

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
    app_parts = parse_fio(app_fio)
    app_variants = build_variants(app_parts)

    doc_variant = detect_variant(doc_fio)
    doc_parts = parse_fio(doc_fio)
    doc_variants = build_variants(doc_parts)

    variant_key = doc_variant
    app_val = app_variants.get(variant_key)
    doc_val = doc_variants.get(variant_key)

    # Exact canonical match per detected variant
    if app_val and doc_val and equals_canonical(doc_val, app_val):
        return True, {
            "matched_variant": variant_key,
            "meta_variant_value": app_val,
            "doc_variant_value": doc_val,
            "meta_parse": asdict(app_parts),
            "fuzzy_score": 100,
        }

    # L_IO raw form normalization match (for spaced initials in doc)
    if doc_variant == "L_IO":
        app_lio = app_variants.get("L_IO")
        doc_norm = normalize_for_name(doc_fio)
        if app_lio and equals_canonical(doc_norm, app_lio):
            return True, {
                "matched_variant": "L_IO",
                "meta_variant_value": app_lio,
                "doc_variant_value": doc_norm,
                "meta_parse": asdict(app_parts),
                "fuzzy_score": 100,
            }

    # Special-case: accept L_I match when app has FULL parts
    if doc_variant == "L_IO" and app_parts.last and app_parts.first and app_parts.patro:
        doc_li = doc_variants.get("L_I")
        app_li = app_variants.get("L_I")
        if doc_li and app_li and equals_canonical(doc_li, app_li):
            return True, {
                "matched_variant": "L_IO",
                "meta_variant_value": app_li,
                "doc_variant_value": doc_li,
                "meta_parse": asdict(app_parts),
                "fuzzy_score": 100,
            }

    # Variant-level fuzzy
    fuzzy_score = None

    def _score(a: str, b: str) -> int:
        if fuzz:
            return int(fuzz.ratio(a, b))
        return int(round(difflib.SequenceMatcher(None, a, b).ratio() * 100))

    if enable_fuzzy_fallback and app_val and doc_val:
        fuzzy_score = _score(app_val, doc_val)
        if fuzzy_score >= fuzzy_threshold:
            return True, {
                "matched_variant": variant_key,
                "meta_variant_value": app_val,
                "doc_variant_value": doc_val,
                "meta_parse": asdict(app_parts),
                "fuzzy_score": fuzzy_score,
            }

    # Raw fuzzy fallback
    if enable_fuzzy_fallback:
        app_norm = normalize_for_name(app_fio or "")
        doc_norm = normalize_for_name(doc_fio or "")

        if fuzz:
            s2 = int(fuzz.token_sort_ratio(app_norm, doc_norm))
        else:
            s2 = int(
                round(difflib.SequenceMatcher(None, app_norm, doc_norm).ratio() * 100)
            )

        fuzzy_score = max(fuzzy_score, s2) if isinstance(fuzzy_score, int) else s2

        if s2 >= fuzzy_threshold:
            return True, {
                "matched_variant": None,
                "meta_variant_value": None,
                "doc_variant_value": doc_norm,
                "meta_parse": asdict(app_parts),
                "fuzzy_score": s2,
            }

    return False, {
        "matched_variant": None,
        "meta_variant_value": None,
        "doc_variant_value": normalize_for_name(doc_fio),
        "meta_parse": asdict(app_parts),
        "fuzzy_score": fuzzy_score,
    }
