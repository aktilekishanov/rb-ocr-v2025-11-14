import re

class AmountComparator:
    """
    Handles normalization and comparison of numeric values.
    Robust against commas, dots, spaces, quotes, and locale variations.
    """

    NULL_STRINGS = {"", "none", "null", "n/a", "na", "nan", "-", "—"}

    @classmethod
    def _is_nullish(cls, value):
        if value is None:
            return True
        s = str(value).strip().lower()
        s = re.sub(r"[ '\u00A0\"«»,.]", "", s)  # strip quotes, punctuation, spaces
        return not s or s in cls.NULL_STRINGS

    @classmethod
    def normalize(cls, value) -> str:
        """
        Normalize numeric strings:
          - Remove thousands separators.
          - Unify decimal marks to '.'.
          - Null-like → "".
        Returns canonical float as string.
        """
        if cls._is_nullish(value):
            return ""

        s = str(value).strip()
        # Remove spaces, quotes, etc., but keep ',' and '.' for separator logic
        s = re.sub(r"[ '\u00A0\"«»]", "", s)

        has_comma = "," in s
        has_dot = "." in s

        if has_comma and has_dot:
            # Determine which separator is decimal (last one)
            last_pos_comma = s.rfind(",")
            last_pos_dot = s.rfind(".")
            if last_pos_comma > last_pos_dot:
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif has_comma and not has_dot:
            s = s.replace(",", ".")
        # else: only dot or neither — leave as is

        # Validate numeric and return canonical float
        if re.fullmatch(r"[+-]?\d+(\.\d+)?", s):
            try:
                return str(float(s))
            except ValueError:
                pass

        return s.lower()

    @classmethod
    def compare(cls, left, right) -> bool:
        """
        Compare two values after normalization.
        Both null-like → True.
        One null-like → False.
        """
        if cls._is_nullish(left) and cls._is_nullish(right):
            return True
        if cls._is_nullish(left) ^ cls._is_nullish(right):
            return False
        return cls.normalize(left) == cls.normalize(right)
