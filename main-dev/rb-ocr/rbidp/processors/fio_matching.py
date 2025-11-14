from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Tuple

try:
    from rapidfuzz import fuzz  # optional for fallback
except Exception:  # pragma: no cover
    fuzz = None


@dataclass
class NameParts:
    last: Optional[str]
    first: Optional[str]
    patro: Optional[str]


# Normalization utilities mirror validator.py behavior
_KZ_TO_RU = str.maketrans({
    "қ": "к",
    "ұ": "у",
    "ү": "у",
    "ң": "н",
    "ғ": "г",
    "ө": "о",
    "Қ": "К",
    "Ұ": "У",
    "Ү": "У",
    "Ң": "Н",
    "Ғ": "Г",
    "Ө": "О",
})

_LATIN_TO_CYR = str.maketrans({
    "a": "а",
    "e": "е",
    "o": "о",
    "p": "р",
    "c": "с",
    "y": "у",
    "x": "х",
    "k": "к",
    "h": "н",
    "b": "в",
    "m": "м",
    "t": "т",
    "i": "и",
    "A": "А",
    "E": "Е",
    "O": "О",
    "P": "Р",
    "C": "С",
    "Y": "У",
    "X": "Х",
    "K": "К",
    "H": "Н",
    "B": "В",
    "M": "М",
    "T": "Т",
    "I": "И",
})


def _collapse_ws_and_case(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    return s.casefold()


def normalize_for_name(s: str) -> str:
    """Normalize for FIO comparison: whitespace, casefold, KZ->RU, Latin->Cyrillic lookalikes."""
    s = _collapse_ws_and_case(s)
    s = s.translate(_KZ_TO_RU)
    s = s.translate(_LATIN_TO_CYR)
    return s


def _strip_trailing_dot(token: str) -> str:
    return token[:-1] if token.endswith(".") else token


def parse_fio(raw: str) -> NameParts:
    """Heuristic parsing to NameParts.
    - Keeps hyphens.
    - Detects compact initials in a single token (e.g., "и.о." -> first='и', patro='о').
    - For two tokens, assumes either (last, first) or (first, patro); we only use this to build variants later.
    """
    s = normalize_for_name(raw)
    if not s:
        return NameParts(None, None, None)
    tokens = s.split()
    if not tokens:
        return NameParts(None, None, None)

    last = None
    first = None
    patro = None

    if len(tokens) >= 3:
        last, first, patro = tokens[0], tokens[1], tokens[2]
        first = _strip_trailing_dot(first)
        patro = _strip_trailing_dot(patro)
    elif len(tokens) == 2:
        # Could be LAST FIRST, FIRST PATRO, LAST + initials (I or IO)
        t1, t2 = tokens
        t2_compact = t2.replace(".", "")
        # initials like "И.О." or "ио"
        if len(t2_compact) == 2 and t2_compact.isalpha():
            last, first, patro = t1, t2_compact[0], t2_compact[1]
        elif len(t2_compact) == 1 and t2_compact.isalpha():
            last, first, patro = t1, t2_compact[0], None
        else:
            # heuristics for FIRST+PATRONYMIC
            patro_suf = (
                "ович", "евич", "ич", "овна", "евна", "ична",
                "қызы", "углы", "улы", "уулу", "кызы", "қызы",
            )
            if any(t2.endswith(s) for s in patro_suf):
                last, first, patro = None, _strip_trailing_dot(t1), _strip_trailing_dot(t2)
            else:
                last, first = t1, _strip_trailing_dot(t2)
    else:  # len == 1
        # Might be just LAST; keep as-is
        last = _strip_trailing_dot(tokens[0])

    return NameParts(last or None, first or None, patro or None)


def build_variants(p: NameParts) -> Dict[str, str]:
    """Return canonical strings per variant: FULL, LF, FP, L_I, L_IO, L.
    Canonicalization rules:
    - FULL/LF/FP: single space between tokens, lowercased.
    - L_I: f"{last} {F}" (no dot stored).
    - L_IO: f"{last} {F}{P}" (no dot and no space between initials stored).
    - L: f"{last}" (surname only) for edge cases where both sides only provide last name.
    """
    variants: Dict[str, str] = {}
    last, first, patro = p.last, p.first, p.patro

    def _canon(*parts: str) -> str:
        parts = [x for x in parts if x]
        s = " ".join(parts)
        s = normalize_for_name(s)
        return s

    if last and first and patro:
        variants["FULL"] = _canon(last, first, patro)
    if last and first:
        variants["LF"] = _canon(last, first)
    if first and patro:
        variants["FP"] = _canon(first, patro)
    if last and first:
        variants["L_I"] = _canon(last, first[:1])
    if last and first and patro:
        # store initials concatenated without spaces/dots
        variants["L_IO"] = _canon(f"{last} {first[:1]}{patro[:1]}")
    if last:
        variants["L"] = _canon(last)

    return variants


def detect_variant(raw: str) -> str:
    """Detect which variant the RAW document string most closely represents.
    Returns one of: FULL, LF, FP, L_I, L_IO, L
    """
    s = normalize_for_name(raw)
    tokens = s.split()
    if not tokens:
        return "L"
    if len(tokens) == 1:
        return "L"
    if len(tokens) >= 3:
        return "FULL"
    # len == 2
    t1, t2 = tokens
    t2c = t2.replace(".", "")
    if len(t2c) == 2 and t2c.isalpha():
        return "L_IO"
    if len(t2c) == 1 and t2c.isalpha():
        return "L_I"
    patro_suf = (
        "ович", "евич", "ич", "овна", "евна", "ична",
        "қызы", "углы", "улы", "уулу", "кызы", "қызы",
    )
    if any(t2.endswith(s) for s in patro_suf):
        return "FP"
    return "LF"


def _normalize_initials_form(s: str) -> str:
    """Normalize dots and spaces for initials comparisons.
    - Remove dots
    - Collapse whitespace
    - Remove spaces between single-letter tokens (e.g., "и о" -> "ио")
    """
    s = normalize_for_name(s)
    s = s.replace(".", "")
    s = re.sub(r"\s+", " ", s).strip()
    # remove spaces between single-letter tokens
    s = re.sub(r"\b([a-zа-я])\s+([a-zа-я])\b", r"\1\2", s)
    return s


def equals_canonical(a: str, b: str) -> bool:
    # Fast path exact compare after standard normalization
    a_std = normalize_for_name(a)
    b_std = normalize_for_name(b)
    if a_std == b_std:
        return True
    # Initials-tolerant compare
    return _normalize_initials_form(a_std) == _normalize_initials_form(b_std)


def fio_match(app_fio: str, doc_fio: str, *, enable_fuzzy_fallback: bool = False, fuzzy_threshold: int = 90) -> Tuple[bool, Dict[str, object]]:
    """Return (match_bool, diagnostics).
    Strategy: parse BOTH application and document FIO, build canonical variants for both, and
    compare same-variant types (FULL, LF, FP, L_I, L_IO) using `equals_canonical`.
    """
    app_parts = parse_fio(app_fio)
    app_variants = build_variants(app_parts)

    doc_variant = detect_variant(doc_fio)
    doc_parts = parse_fio(doc_fio)
    doc_variants = build_variants(doc_parts)

    # Match ONLY against the variant explicitly detected from the document.
    v = doc_variant
    app_val = app_variants.get(v)
    doc_val = doc_variants.get(v)
    if app_val and doc_val and equals_canonical(doc_val, app_val):
        return True, {
            "matched_variant": v,
            "meta_variant_value": app_val,
            "doc_variant_value": doc_val,
            "meta_parse": asdict(app_parts),
            "fuzzy_score": None,
        }

    # Special-case: if the document shows two initials (L_IO), accept match by last + first-initial only,
    # but ONLY when application includes a patronymic (3-part name). This keeps L_IO rejected for 2-part apps.
    if doc_variant == "L_IO" and app_parts.last and app_parts.first and app_parts.patro:
        doc_li = doc_variants.get("L_I")
        app_li = app_variants.get("L_I")
        if doc_li and app_li and equals_canonical(doc_li, app_li):
            return True, {
                "matched_variant": "L_IO",
                "meta_variant_value": app_li,
                "doc_variant_value": doc_li,
                "meta_parse": asdict(app_parts),
                "fuzzy_score": None,
            }

    # Fallback (optional)
    fuzzy_score = None
    if enable_fuzzy_fallback and fuzz is not None:
        try:
            fuzzy_score = fuzz.token_sort_ratio(normalize_for_name(app_fio or ""), normalize_for_name(doc_fio or ""))
            if isinstance(fuzzy_score, (int, float)) and fuzzy_score >= fuzzy_threshold:
                return True, {
                    "matched_variant": None,
                    "meta_variant_value": None,
                    "doc_variant_value": doc_norm,
                    "meta_parse": asdict(app_parts),
                    "fuzzy_score": fuzzy_score,
                }
        except Exception:
            pass

    return False, {
        "matched_variant": None,
        "meta_variant_value": None,
        "doc_variant_value": normalize_for_name(doc_fio),
        "meta_parse": asdict(app_parts),
        "fuzzy_score": fuzzy_score,
    }
