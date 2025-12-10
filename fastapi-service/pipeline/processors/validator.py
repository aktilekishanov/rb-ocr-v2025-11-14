"""
Run-level validation of merged extractor/doc-type results.

Computes FIO match, doc-type knowledge, doc-date validity, and single-doc
constraints, producing a structured ``validation.json`` plus diagnostics 
used by the UI.
"""

import json
import os
import re
from typing import Any

from rapidfuzz import fuzz

from pipeline.core.dates import now_utc_plus
from pipeline.core.validity import compute_valid_until, format_date, is_within_validity
from pipeline.processors.fio_matching import fio_match as det_fio_match

VALIDATION_MESSAGES = {
    "checks": {
        "fio_match": {
            True: "Относится к заявителю",
            False: "Не относится к заявителю",
        },
        "doc_type_known": {
            True: "Тип документа распознан",
            False: "Не удалось определить тип документа",
        },
        "doc_date_valid": {
            True: "Актуальная дата документа",
            False: "Устаревшая дата документа",
        },
        "single_doc_type_valid": {
            True: "Файл содержит один тип документа",
            False: "Файл содержит несколько типов документов",
        },
    },
    "verdict": {
        True: "Отсрочка активирована: прикрепленный документ успешно прошел проверку",
        False: "К сожалению, Вам отказано в отсрочке: прикрепленный документ не прошел проверку",
    },
}


def _norm_text(s: Any) -> str:
    if not isinstance(s, str):
        return ""
    s = re.sub(r"\s+", " ", s.strip())
    return s.casefold()


def _now_utc_plus_5():
    return now_utc_plus(5)


def kz_to_ru(s: str) -> str:
    table = str.maketrans(
        {
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
    )
    return s.translate(table)


def latin_to_cyrillic(s: str) -> str:
    table = str.maketrans(
        {
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
    )
    return s.translate(table)


def validate_run(
    user_provided_fio: dict[str, str | None],
    extractor_data: dict[str, Any],     # Pass data directly (not file path)
    doc_type_data: dict[str, Any],      # Pass data directly (not file path)
) -> dict[str, Any]:
    """
    Validate a single run using in-memory data only.
    
    Optimized to eliminate file I/O - receives parsed data from context.
    
    Args:
      user_provided_fio: FIO from user/Kafka (passed via PipelineContext)
      extractor_data: Parsed extractor results from context (no file read)
      doc_type_data: Parsed doc type results from context (no file read)

    Returns:
      A dict with keys ``success``, ``error``, and
      ``result`` (containing checks, verdict, and diagnostics).
    """
    # Build merged data in-memory (NO FILE I/O)
    merged = {
        "fio": extractor_data.get("fio"),
        "doc_date": extractor_data.get("doc_date"),
        "single_doc_type": doc_type_data.get("single_doc_type"),
        "doc_type_known": doc_type_data.get("doc_type_known"),
        "doc_type": doc_type_data.get("detected_doc_types", [None])[0] if isinstance(doc_type_data.get("detected_doc_types"), list) else None,
    }

    fio_meta_raw = user_provided_fio.get("fio") if isinstance(user_provided_fio, dict) else user_provided_fio

    fio_meta = _norm_text(fio_meta_raw)

    fio_meta_ru = kz_to_ru(fio_meta)
    fio_meta_norm = latin_to_cyrillic(fio_meta_ru)

    fio_raw = merged.get("fio") if isinstance(merged, dict) else None
    fio = _norm_text(fio_raw)
    fio_ru = kz_to_ru(fio)
    fio_norm = latin_to_cyrillic(fio_ru)
    doc_class_raw = merged.get("doc_type") if isinstance(merged, dict) else None
    doc_class = _norm_text(doc_class_raw)
    doc_date_raw = merged.get("doc_date") if isinstance(merged, dict) else None
    single_doc_type_raw = merged.get("single_doc_type") if isinstance(merged, dict) else None
    doc_type_known_raw = merged.get("doc_type_known") if isinstance(merged, dict) else None

    score_before = None
    score_after = None
    try:
        if fio_meta and fio:
            score_before = fuzz.token_sort_ratio(fio_meta, fio)
        if fio_meta_norm and fio_norm:
            score_after = fuzz.token_sort_ratio(fio_meta_norm, fio_norm)
    except Exception:
        pass

    try:
        fio_match_bool, fio_diag = det_fio_match(
            fio_meta_raw or "",
            fio_raw or "",
            enable_fuzzy_fallback=True,
            fuzzy_threshold=85,
        )
        fio_match = bool(fio_match_bool)
    except Exception:
        fio_match = None
        fio_diag = {
            "matched_variant": None,
            "meta_variant_value": None,
            "doc_variant_value": None,
            "meta_parse": None,
            "fuzzy_score": None,
        }
    if isinstance(doc_type_known_raw, bool):
        doc_type_known = doc_type_known_raw
    else:
        doc_type_known = None

    now = _now_utc_plus_5()
    valid_until_dt, policy_type, policy_days, policy_error = compute_valid_until(
        doc_class_raw, doc_date_raw
    )
    doc_date_valid = is_within_validity(valid_until_dt, now)

    if isinstance(single_doc_type_raw, bool):
        single_doc_type_valid = single_doc_type_raw
    else:
        single_doc_type_valid = None

    checks = {
        "fio_match": fio_match,
        "doc_type_known": doc_type_known,
        "doc_date_valid": doc_date_valid,
        "single_doc_type_valid": single_doc_type_valid,
    }

    verdict = (
        checks.get("fio_match") is True
        and checks.get("doc_type_known") is True
        and checks.get("doc_date_valid") is True
        and checks.get("single_doc_type_valid") is True
    )

    diagnostics = {
        "inputs": {
            "fio_meta": fio_meta_raw,
            "fio": fio_raw,
            "doc_type": doc_class_raw,
            "doc_date": doc_date_raw,
            "single_doc_type": single_doc_type_raw,
        },
        "normalization": {
            "fio_meta_norm": fio_meta_norm,
            "fio_norm": fio_norm,
            "doc_type_norm": doc_class,
        },
        "scores": {
            "fio_similarity_before": score_before,
            "fio_similarity_after": score_after,
        },
        "timing": {
            "now_utc_plus_5": now.isoformat(),
            "effective_valid_until": format_date(valid_until_dt),
            "policy_type": policy_type,
            "validity_window_days": policy_days,
            "policy_error": policy_error,
        },
        "checks": checks,
        "fio_details": fio_diag,
        "messages": {
            key: VALIDATION_MESSAGES["checks"][key].get(val) if val is not None else None
            for key, val in checks.items()
        },
    }

    result = {
        "checks": checks,
        "verdict": verdict,
        "diagnostics": diagnostics,
    }

    return {"success": True, "error": None, "result": result}
