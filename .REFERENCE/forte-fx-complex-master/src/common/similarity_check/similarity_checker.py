from typing import Dict, Any, List
import re
import unicodedata

from src.common.similarity_check._amount_check import AmountComparator
from src.common.similarity_check._date_check import compare_dates
from src.common.similarity_check._organisation_check import compare_organisation_name


class SimilarityChecker:
    DATE_FIELDS = {"CONTRACT_DATE", "CONTRACT_END_DATE"}
    ORG_FIELDS = {"CLIENT", "COUNTERPARTY_NAME"}
    NUMERIC_FIELDS = {"AMOUNT"}

    # Optional: specific unordered-set fields (otherwise treat all general ones as flexible)
    SET_FIELDS = {"CONTRACT_CURRENCY", "PAYMENT_CURRENCY", "CONTRACT_NAMES", "DOCUMENT_REFERENCES"}

    # Treat these tokens as null-like AFTER canonicalization
    NULL_STRINGS = {"", "none", "null", "n/a", "na", "nan", "-", "—", "–"}

    # Quotes, commas, dots, spaces, fancy quotes (note: we remove spaces after canonicalization)
    STRIP_CHARS = r"['\"«»„“”‚‘’.·.,\s]+"  # kept behavior: remove quotes/commas/dots/spaces

    # ---------- Canonicalization helpers ----------

    # Translate “smart” quotes & dashes to simple ASCII; NBSP/thin spaces to regular space.
    _TRANS_TABLE = str.maketrans({
        # Quotes → "
        "\u2018": '"', "\u2019": '"', "\u201A": '"', "\u201B": '"',
        "\u201C": '"', "\u201D": '"', "\u201E": '"', "\u201F": '"',
        "«": '"', "»": '"', "„": '"', "‟": '"', "‚": '"',
        # Dashes/Hyphens → -
        "\u2010": "-",  # hyphen
        "\u2011": "-",  # non-breaking hyphen
        "\u2012": "-",  # figure dash
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2212": "-",  # minus sign
        "\u2043": "-",  # hyphen bullet
        "\uFE58": "-", "\uFE63": "-", "\uFF0D": "-",  # compatibility/fullwidth dashes
        "\u00AD": "",   # soft hyphen -> drop
        # Misc punctuation harmonization (optional)
        "’": '"', "‘": '"', "“": '"', "”": '"',
    })

    # Any Unicode space chars we want to normalize to a regular space
    _UNICODE_SPACES_RE = re.compile(r"[\u00A0\u1680\u2000-\u200B\u202F\u205F\u3000]")

    def __init__(self, debug=False):
        self.debug = debug

    @classmethod
    def _canon(cls, value: Any) -> str:
        """
        Unicode-aware canonicalization used EVERYWHERE:
          - NFKC normalization
          - quotes → "
          - all dash variants → '-'
          - any unicode space → ' '
          - collapse spaces, trim, lowercase
        """
        if value is None:
            return ""
        s = str(value)
        s = unicodedata.normalize("NFKC", s)
        s = s.translate(cls._TRANS_TABLE)
        s = cls._UNICODE_SPACES_RE.sub(" ", s)
        s = re.sub(r"\s+", " ", s).strip().lower()
        return s

    # ---------- Null & Cleaning helpers ----------

    @classmethod
    def _clean_string(cls, value: Any) -> str:
        """
        Old helper kept for compatibility, but now runs through _canon first,
        then applies your 'strip punctuation and spaces' rule.
        """
        if value is None:
            return ""
        s = cls._canon(value)
        return re.sub(cls.STRIP_CHARS, "", s)

    @classmethod
    def _is_nullish(cls, value: Any) -> bool:
        if value is None:
            return True
        s = cls._canon(value)  # canonicalize BEFORE checking null-tokens
        return (not s) or (s in cls.NULL_STRINGS)

    @classmethod
    def _both_nullish(cls, a: Any, b: Any) -> bool:
        return cls._is_nullish(a) and cls._is_nullish(b)

    @classmethod
    def _xor_nullish(cls, a: Any, b: Any) -> bool:
        return cls._is_nullish(a) ^ cls._is_nullish(b)

    # ---------- Normalizers ----------

    @classmethod
    def _norm_none_empty(cls, value: Any) -> str:
        """
        General text/list normalization for non-special fields.
        Canonicalize first, then remove quotes/commas/dots/spaces.
        """
        if cls._is_nullish(value):
            return ""
        if isinstance(value, list):
            items = [
                re.sub(cls.STRIP_CHARS, "", cls._canon(v))
                for v in value
                if not cls._is_nullish(v)
            ]
            return " | ".join(sorted(set(items))) if items else ""
        return re.sub(cls.STRIP_CHARS, "", cls._canon(value))

    @classmethod
    def _norm_token_set(cls, value: Any) -> str:
        """
        Normalize a value as an unordered set of tokens (for fields we treat as sets).
        Splits on commas OR whitespace for strings; accepts lists.
        Canonicalizes each token, drops null-like tokens, and sorts.
        """
        if cls._is_nullish(value):
            return ""
        tokens: List[str] = []

        if isinstance(value, list):
            raw_parts = [str(v) for v in value]
        else:
            raw_parts = [str(value)]

        for part in raw_parts:
            # Split on commas OR whitespace
            for tok in re.split(r"[,\s]+", cls._canon(part)):
                if cls._is_nullish(tok):
                    continue
                cleaned = re.sub(cls.STRIP_CHARS, "", tok)
                if cleaned and not cls._is_nullish(cleaned):
                    tokens.append(cleaned)

        if not tokens:
            return ""
        return ", ".join(sorted(set(tokens)))

    # ---------- List unroller ----------

    @classmethod
    def _unroll_list(cls, value: Any) -> Any:
        """
        Turn lists into a single string: 'a, b, c'.
        Nullish elements are removed; if nothing remains -> ''.
        Non-list values are returned as-is.
        """
        if not isinstance(value, list):
            return value
        parts: List[str] = []
        for v in value:
            if cls._is_nullish(v):
                continue
            s = cls._canon(v)
            if s and not cls._is_nullish(s):
                parts.append(s)
        return ", ".join(parts) if parts else ""

    # ---------- Dispatcher ----------

    def _compare_field(self, key: str, left: Any, right: Any) -> bool:
        # 0) Unroll lists into "a, b" strings before any checks
        left = self._unroll_list(left)
        right = self._unroll_list(right)

        # 1) Uniform null logic
        if self._both_nullish(left, right):
            return True
        if self._xor_nullish(left, right):
            return False

        # 2) Field-specific logic
        if key in self.DATE_FIELDS:
            # Dates get canonicalized by compare_dates internally (assumed).
            # We still pass the raw strings because date parser may rely on punctuation.
            return compare_dates(left, right)

        if key in self.ORG_FIELDS:
            # Compare organization names on canonicalized strings
            return compare_organisation_name(self._canon(left), self._canon(right), debug=self.debug)

        if key in self.NUMERIC_FIELDS:
            # Amount comparator should accept raw strings; we canonicalize dash/space/quote beforehand
            return AmountComparator.compare(self._canon(left), self._canon(right))

        if key in self.SET_FIELDS:
            return self._norm_token_set(left) == self._norm_token_set(right)

        # 3) General text/list logic
        # (Shouldn't happen now that we unroll, but keep for safety)
        return self._norm_none_empty(left) == self._norm_none_empty(right)

    # ---------- Public API ----------

    def compare(
        self,
        actual_values: Dict[str, Any],
        pipeline_values: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Compare two dicts (actual vs pipeline) field-by-field.
        Ignores missing keys in pipeline_values.
        Returns: list of {name: FIELD, Identical: bool}.
        """
        results: List[Dict[str, Any]] = []

        for key, expected_raw in actual_values.items():
            pipeline_raw = pipeline_values.get(key)
            identical = self._compare_field(key, expected_raw, pipeline_raw)
            results.append({"name": key, "Identical": bool(identical)})

        return results
