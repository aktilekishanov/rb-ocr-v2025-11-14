import re
from typing import Tuple, List

# ---------- Precompiled, module-level assets for speed ----------

# Map punctuation/quotes to spaces in one pass
_TRANS = str.maketrans({
    ",": " ",           # commas -> space
    "«": " ", "»": " ", # fancy quotes -> space
    "“": " ", "”": " ", # curly quotes -> space
    '"': " ",           # straight quotes -> space
})

_WS_RE = re.compile(r"\s+")

_LEGAL_FORMS_RE = re.compile(
    r"(?P<AO>\bао|акционерное\s+общество|jsc|joint\s+stock\s+company)"
    r"|(?P<TOO>\btoo|\bтоо|товарищество\s+с\s+ограниченной\s+ответственностью|\bllp|\bllc|\bltd|limited\s+liability\s+partnership|\bl.l.p.|\bl.l.c.|\bl.t.d.)"
    r"|(?P<IP>\bип|индивидуальный\s+предприниматель)"
    r"|(?P<OOO>\bооо|\booo|общество\s+с\s+ограниченной\s+ответственностью)",
    re.IGNORECASE
)

# Canonical tokens we inject during normalization (surrounded by spaces)
_TOKEN_BY_GROUP = {"AO": " ao ", "TOO": " too ", "IP": " ip ", "OOO": " ooo "}
_CANON_TOKENS_RE = re.compile(r"\b(?:ao|too|ip|ooo)\b")

# --- Homoglyph folding: Cyrillic → Latin skeleton (after casefold) ---
# Keep this conservative: only the most common confusables.
# (We do not persist this; we only use it for equality comparison.)
_HOMOGLYPH_TRANSLATE = str.maketrans({
    # vowels
    "а": "a",  # Cyrillic a
    "е": "e",  # Cyrillic e
    "о": "o",  # Cyrillic o
    "ё": "e",  # treat ё ~ e for plain skeleton
    "і": "i",  # Ukrainian/Belarusian i -> i (harmless; helps if present)
    # consonants / shapes
    "р": "p",
    "с": "c",
    "х": "x",
    "у": "y",
    "к": "k",
    "м": "m",
    "т": "t",
    "н": "h",
    "в": "b",
    # uppercase not needed since we casefold, but safe to include:
    "А": "a", "Е": "e", "О": "o", "Ё": "e", "І": "i",
    "Р": "p", "С": "c", "Х": "x", "У": "y", "К": "k",
    "М": "m", "Т": "t", "Н": "h", "В": "b",
})

# ── bracket variants helper ────────────────────────────────────────────────
_BRACKETS_RE = re.compile(r"\(([^)]*)\)")  # simple () support; easy to extend

def _cleanup_spaces(s: str) -> str:
    return _WS_RE.sub(" ", s).strip()

def _strip_core_punct(s: str) -> str:
    # We decided: dots/commas don't matter
    return _cleanup_spaces(re.sub(r"[.,]", " ", s))

def _bracket_variants(core: str) -> List[str]:
    """Return variants for comparison: whole, outside (no brackets), and each inside."""
    insides = _BRACKETS_RE.findall(core)
    outside = _BRACKETS_RE.sub(" ", core)
    variants = [core, outside] + insides
    # normalize punctuation/spacing on each variant
    variants = [_strip_core_punct(v) for v in variants]
    # dedupe while preserving order, drop empties
    seen, out = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out

def _homoglyph_fold(s: str) -> str:
    """Fold common Cyrillic lookalikes into Latin skeleton for comparison."""
    # Assumes s is already casefolded
    return s.translate(_HOMOGLYPH_TRANSLATE)

def _normalize_and_extract_type(s: str, debug: bool = False) -> Tuple[str, str]:
    """
    Lowercase + translate punctuation to spaces + collapse whitespace,
    then replace all legal-form variants with canonical tokens ('ao','too','ip','ooo')
    while simultaneously capturing the detected type(s) in this string.

    Returns:
      (detected_type, core_name)
      - detected_type ∈ {"ao","too","ip","ooo","unknown","mixed"}
      - core_name     : string with canonical tokens removed, spaces collapsed
    """
    if s is None:
        s = ""

    # 1) Lowercase & cheap punctuation normalization
    s = s.casefold().strip().translate(_TRANS)
    s = _WS_RE.sub(" ", s)

    # 2) Replace legal-form variants with canonical tokens and record types
    seen_types: List[str] = []

    def _sub(m: re.Match) -> str:
        g = m.lastgroup  # "AO", "TOO", "IP", "OOO"
        t = g.lower()
        if not seen_types or seen_types[-1] != t:
            seen_types.append(t)
        return _TOKEN_BY_GROUP[g]

    s = _LEGAL_FORMS_RE.sub(_sub, s)
    s = _WS_RE.sub(" ", s).strip()

    # 3) Decide detected_type for this side
    if not seen_types:
        detected = "unknown"
    else:
        uniq = set(seen_types)
        detected = seen_types[0] if len(uniq) == 1 else "mixed"

    # 4) Extract the core name by removing all canonical tokens
    core = _CANON_TOKENS_RE.sub(" ", s)
    core = _WS_RE.sub(" ", core).strip()

    # Remove punctuation that shouldn't affect semantic comparison
    core = re.sub(r"[.,]", " ", core)
    core = _WS_RE.sub(" ", core).strip()

    if debug:
        print(f"  _normalize_and_extract_type -> detected={detected!r}, core={core!r}, raw_norm={s!r}")
    return detected, core

def compare_organisation_name(left: str, right: str, debug: bool = False) -> bool:
    """
       Optimized comparison of organisation names (company or entrepreneur).
       True if semantically equivalent across:
         - Legal form variants (АО/JSC, ТОО/LLP/LLC/LTD, ИП)
         - Quote types and commas
         - Extra spaces and casing
         - Prefix/suffix placement of legal forms
       """

    if debug:
        print("=== compare_organisation_name (unified) ===")
        print(f"RAW LEFT : {left!r}")
        print(f"RAW RIGHT: {right!r}")

    t_left, core_left = _normalize_and_extract_type(left or "", debug=debug)
    t_right, core_right = _normalize_and_extract_type(right or "", debug=debug)

    if debug:
        print(f"DETECTED TYPES -> left: {t_left!r}, right: {t_right!r}")
        print(f"CORES           left: {core_left!r}")
        print(f"                right:{core_right!r}")

    # Mixed or mismatched types fail
    if t_left == "mixed" or t_right == "mixed":
        if debug:
            print("MIXED TYPE on one side -> False")
            print("=== end compare_organisation_name ===\n")
        return False
    if t_left != t_right:
        if debug:
            print("TYPE MISMATCH -> False")
            print("=== end compare_organisation_name ===\n")
        return False

    # ── bracket-aware candidate expansion ──────────────────────────────────
    left_cands = _bracket_variants(core_left)
    right_cands = _bracket_variants(core_right)

    if debug:
        print(f"LEFT CANDIDATES : {left_cands}")
        print(f"RIGHT CANDIDATES: {right_cands}")

    # Compare every pair with homoglyph fold
    for lc in left_cands:
        for rc in right_cands:
            if _homoglyph_fold(lc) == _homoglyph_fold(rc):
                if debug:
                    print(f"MATCH via candidates -> {lc!r} == {rc!r} -> True")
                    print("=== end compare_organisation_name ===\n")
                return True

    if debug:
        print("No candidate pair matched -> False")
        print("=== end compare_organisation_name ===\n")
    return False
