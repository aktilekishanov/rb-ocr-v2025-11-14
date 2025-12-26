"""Application constants and configuration mappings."""

from typing import Any

ALLOWED_CONTENT_TYPES: set[str] = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
}
KZ_TO_RU_MAPPING: dict[str, str] = {
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
}
LATIN_TO_CYRILLIC_MAPPING: dict[str, str] = {
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
}
PATRONYMIC_SUFFIXES: tuple[str, ...] = (
    "ович",
    "евич",
    "ич",
    "овна",
    "евна",
    "ична",
    "қызы",
    "углы",
    "улы",
    "уулу",
    "кызы",
    "қызы",
)
VALIDITY_OVERRIDES: dict[str, dict[str, Any]] = {
    "Заключение врачебно-консультативной комиссии (ВКК)": {
        "type": "fixed_days",
        "days": 180,
    },
    "Справка об инвалидности": {
        "type": "fixed_days",
        "days": 360,
    },
    "Справка о степени утраты общей трудоспособности": {
        "type": "fixed_days",
        "days": 360,
    },
    "Приказ о выходе в декретный отпуск по уходу за ребенком": {
        "type": "fixed_days",
        "days": 365,
    },
    "Справка о выходе в декретный отпуск по уходу за ребенком": {
        "type": "fixed_days",
        "days": 365,
    },
}
