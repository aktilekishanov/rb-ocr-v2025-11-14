import re
from typing import Any
from pipeline.core.dates import now_utc_plus
from pipeline.core.validity import compute_valid_until, is_within_validity
from pipeline.processors.fio_matching import (
    fio_match as det_fio_match,
)


def _norm_text(text: Any) -> str:
    if not isinstance(text, str):
        return ""
    return re.sub(r"\s+", " ", text.strip()).casefold()


def validate_run(
    user_provided_fio: dict[str, str | None],
    extractor_data: dict[str, Any],
    doc_type_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Validate a single run using in-memory data only.
    """

    detected_doc_types = doc_type_data.get("detected_doc_types")
    doc_type = (
        detected_doc_types[0]
        if isinstance(detected_doc_types, list) and detected_doc_types
        else None
    )

    merged = {
        "fio": extractor_data.get("fio"),
        "doc_date": extractor_data.get("doc_date"),
        "single_doc_type": doc_type_data.get("single_doc_type"),
        "doc_type_known": doc_type_data.get("doc_type_known"),
        "doc_type": doc_type,
    }

    fio_meta_raw = (
        user_provided_fio.get("fio")
        if isinstance(user_provided_fio, dict)
        else user_provided_fio
    )

    fio_raw = merged["fio"]
    doc_class_raw = merged["doc_type"]
    doc_date_raw = merged["doc_date"]
    single_doc_type_raw = merged["single_doc_type"]
    doc_type_known_raw = merged["doc_type_known"]

    # --- FIO match ---
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

    doc_type_known = (
        doc_type_known_raw if isinstance(doc_type_known_raw, bool) else None
    )

    # --- Date validity ---
    now = now_utc_plus(5)
    valid_until_dt, policy_type, policy_days, policy_error = compute_valid_until(
        doc_class_raw, doc_date_raw
    )
    doc_date_valid = is_within_validity(valid_until_dt, now)

    # --- Single doc flag ---
    single_doc_type_valid = (
        single_doc_type_raw if isinstance(single_doc_type_raw, bool) else None
    )

    checks = {
        "fio_match": fio_match,
        "doc_type_known": doc_type_known,
        "doc_date_valid": doc_date_valid,
        "single_doc_type_valid": single_doc_type_valid,
    }

    verdict = (
        checks["fio_match"] is True
        and checks["doc_type_known"] is True
        and checks["doc_date_valid"] is True
        and checks["single_doc_type_valid"] is True
    )

    return {
        "success": True,
        "error": None,
        "result": {
            "checks": checks,
            "verdict": verdict,
        },
    }
