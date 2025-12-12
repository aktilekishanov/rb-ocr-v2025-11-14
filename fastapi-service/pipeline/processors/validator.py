"""
Run-level validation of merged extractor/doc-type results.

Computes FIO match, doc-type knowledge, doc-date validity, and single-doc
constraints, returning validation checks and overall verdict.
"""

import re
from typing import Any

from rapidfuzz import fuzz

from pipeline.core.dates import now_utc_plus
from pipeline.core.validity import compute_valid_until, format_date, is_within_validity
from pipeline.processors.fio_matching import (
    fio_match as det_fio_match,
    normalize_for_name,
)


def _norm_text(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    text = re.sub(r"\s+", " ", text.strip())
    return text.casefold()


def validate_run(
    user_provided_fio: dict[str, str | None],
    extractor_data: dict[str, Any],  
    doc_type_data: dict[str, Any],  
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
      ``result`` (containing checks and verdict).
    """
    
    merged = {
        "fio": extractor_data.get("fio"),
        "doc_date": extractor_data.get("doc_date"),
        "single_doc_type": doc_type_data.get("single_doc_type"),
        "doc_type_known": doc_type_data.get("doc_type_known"),
        "doc_type": doc_type_data.get("detected_doc_types", [None])[0]
        if isinstance(doc_type_data.get("detected_doc_types"), list)
        else None,
    }

    fio_meta_raw = (
        user_provided_fio.get("fio")
        if isinstance(user_provided_fio, dict)
        else user_provided_fio
    )

    fio_meta = _norm_text(fio_meta_raw)
    fio_meta_norm = normalize_for_name(fio_meta)

    fio_raw = merged.get("fio") if isinstance(merged, dict) else None
    fio = _norm_text(fio_raw)
    fio_norm = normalize_for_name(fio)
    doc_class_raw = merged.get("doc_type") if isinstance(merged, dict) else None
    doc_class = _norm_text(doc_class_raw)
    doc_date_raw = merged.get("doc_date") if isinstance(merged, dict) else None
    single_doc_type_raw = (
        merged.get("single_doc_type") if isinstance(merged, dict) else None
    )
    doc_type_known_raw = (
        merged.get("doc_type_known") if isinstance(merged, dict) else None
    )

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

    now = now_utc_plus(5)
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

    result = {
        "checks": checks,
        "verdict": verdict,
    }

    return {"success": True, "error": None, "result": result}
