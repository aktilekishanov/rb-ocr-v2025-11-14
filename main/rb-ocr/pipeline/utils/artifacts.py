"""
Helpers for building and persisting high-level pipeline artifacts.

This module is responsible for `final_result.json`, the human-facing
manifest, and a side-by-side JSON view that compares meta vs extracted
data for debugging and auditability.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.core.config import METADATA_FILENAME
from pipeline.core.validity import compute_valid_until, format_date
from pipeline.utils.io_utils import read_json, write_json


def build_final_result(
    *,
    run_id: str,
    errors: list[dict[str, Any]],
    verdict: bool,
    checks: dict[str, Any] | None,
    final_path: str | Path,
    meta_dir: str | Path,
) -> dict[str, Any]:
    """
    Build and persist the top-level `final_result.json` payload.

    Only error codes are written to the public artifact to avoid
    leaking internal details; the full error objects are preserved in
    the in-memory return structure.

    Args:
      run_id: Unique run identifier.
      errors: List of structured error dicts accumulated by the pipeline.
      verdict: Overall boolean verdict for the document.
      checks: Optional per-check results (not written directly here).
      final_path: Destination path for `final_result.json`.
      meta_dir: Directory where `metadata.json` is stored.

    Returns:
      A dict summarizing the run for internal use, including the path
      to the written `final_result.json`.
    """
    file_errors: list[dict[str, Any]] = []
    for e in errors:
        if isinstance(e, dict) and "code" in e:
            file_errors.append({"code": e.get("code")})
        else:
            file_errors.append({"code": str(e)})

    file_result: dict[str, Any] = {
        "run_id": run_id,
        "verdict": bool(verdict),
        "errors": file_errors,
    }

    try:
        meta_path = Path(meta_dir) / METADATA_FILENAME
        if meta_path.exists():
            mo = read_json(meta_path)
            if isinstance(mo, dict) and "stamp_present" in mo:
                file_result["stamp_present"] = bool(mo.get("stamp_present"))
    except Exception:
        pass

    write_json(final_path, file_result)

    return {
        "run_id": run_id,
        "verdict": bool(verdict),
        "errors": errors,
        "final_result_path": str(final_path),
    }


def write_manifest(
    *,
    meta_dir: str | Path,
    run_id: str,
    user_input: dict[str, Any],
    file_info: dict[str, Any],
    artifacts: dict[str, Any],
    status: str,
    error: str | None,
    created_at: str,
) -> None:
    """
    Write a manifest describing the run, timing, and key artifacts.

    The manifest is intended for operators and debugging tools. It
    normalizes timing fields and records only curated artifact paths.

    Args:
      meta_dir: Directory where `manifest.json` will be written.
      run_id: Unique run identifier.
      user_input: Dict with user-provided fields from the request.
      file_info: Dict with basic file metadata (name, size, content type).
      artifacts: Dict containing paths and durations collected by stages.
      status: High-level status string for the run.
      error: Optional error message for failed runs.
      created_at: ISO timestamp when the run was created.
    """
    meta_dir = Path(meta_dir)
    final_result_path = artifacts.get("final_result_path") or str(meta_dir / "final_result.json")
    side_by_side_path = (
        str(meta_dir / "side_by_side.json") if (meta_dir / "side_by_side.json").exists() else None
    )
    merged_path = artifacts.get("llm_merged_path")

    duration_seconds = artifacts.get("duration_seconds")
    try:
        if duration_seconds is not None:
            duration_seconds = float(duration_seconds)
    except Exception:
        duration_seconds = None

    manifest = {
        "run_id": run_id,
        "created_at": created_at,
        "timing": {
            "duration_seconds": duration_seconds,
            "stamp_seconds": artifacts.get("stamp_seconds"),
            "ocr_seconds": artifacts.get("ocr_seconds"),
            "llm_seconds": artifacts.get("llm_seconds"),
        },
        "user_input": user_input,
        "file": file_info,
        "artifacts": {
            "final_result_path": final_result_path,
            "side_by_side_path": side_by_side_path,
            "merged_path": merged_path,
        },
        "status": status,
        "error": error,
    }
    write_json(Path(meta_dir) / "manifest.json", manifest)


def build_side_by_side(
    *, meta_dir: str | Path, merged_path: str | Path, request_created_at: str
) -> None:
    """
    Build a side-by-side JSON view of meta vs extracted fields.

    This artifact is used for manual inspection and QA: it surfaces the
    key comparison points (FIO, doc type, doc date, validity window and
    stamp presence) in a single, easy-to-read structure.

    Args:
      meta_dir: Directory containing `metadata.json` and stamp results.
      merged_path: Path to `merged.json` produced by the merge stage.
      request_created_at: Original request creation timestamp.
    """
    meta_dir = Path(meta_dir)
    meta_obj = read_json(meta_dir / METADATA_FILENAME)
    merged_obj = read_json(merged_path)

    fio_meta_raw = meta_obj.get("fio") if isinstance(meta_obj, dict) else None
    fio_extracted_raw = merged_obj.get("fio") if isinstance(merged_obj, dict) else None

    doc_type_meta_raw = meta_obj.get("doc_type") if isinstance(meta_obj, dict) else None
    doc_type_extracted_raw = (
        merged_obj.get("doc_type") if isinstance(merged_obj, dict) else None
    )

    doc_date_extracted = merged_obj.get("doc_date") if isinstance(merged_obj, dict) else None
    vu_dt, _, _, _ = compute_valid_until(doc_type_extracted_raw, doc_date_extracted)
    valid_until_str = format_date(vu_dt)

    single_doc_type_raw = merged_obj.get("single_doc_type") if isinstance(merged_obj, dict) else None
    doc_type_known_raw = merged_obj.get("doc_type_known") if isinstance(merged_obj, dict) else None

    side_by_side: dict[str, Any] = {
        "request_created_at": request_created_at,
        "fio": {"meta": fio_meta_raw, "extracted": fio_extracted_raw},
        "doc_type": {"meta": doc_type_meta_raw, "extracted": doc_type_extracted_raw},
        "doc_date": {"extracted": doc_date_extracted, "valid_until": valid_until_str},
        "single_doc_type": {"extracted": single_doc_type_raw},
        "doc_type_known": {
            "extracted": (doc_type_known_raw if isinstance(doc_type_known_raw, bool) else None)
        },
    }

    try:
        scr_path = meta_dir / "stamp_check_response.json"
        sp_val = None
        if scr_path.exists():
            scr = read_json(scr_path)
            if isinstance(scr, dict) and "stamp_present" in scr:
                sp_val = bool(scr.get("stamp_present"))
        side_by_side["stamp_present"] = {"extracted": (sp_val if sp_val is not None else None)}
    except Exception:
        pass

    write_json(meta_dir / "side_by_side.json", side_by_side)
