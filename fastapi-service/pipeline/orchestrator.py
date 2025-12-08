"""
RB-OCR pipeline orchestrator for main-dev.

Coordinates per-run directory layout, staged processing 
(acquire, OCR, LLM doc-type check, extraction, merge, validation), 
error handling,timing, and artifact/manifest writing. 
Public entrypoint: `run_pipeline`.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from pipeline.clients.tesseract_async_client import ask_tesseract
from pipeline.core.config import (
    LLM_DOC_TYPE_FILTERED,
    LLM_DOC_TYPE_RAW,
    LLM_EXTRACTOR_FILTERED,
    LLM_EXTRACTOR_RAW,
    MAX_PDF_PAGES,
    MERGED_FILENAME,
    METADATA_FILENAME,
    OCR_PAGES,
    UTC_OFFSET_HOURS,
    VALIDATION_FILENAME,
)
from pipeline.core.errors import make_error
from pipeline.processors.agent_doc_type_checker import check_single_doc_type
from pipeline.processors.agent_extractor import extract_doc_data
from pipeline.processors.filter_llm_generic_response import filter_llm_generic_response
from pipeline.processors.filter_ocr_response import filter_ocr_response
from pipeline.processors.merge_outputs import merge_extractor_and_doc_type
from pipeline.processors.validator import validate_run
from pipeline.utils.artifacts import (
    build_final_result as util_build_final_result,
    write_manifest as util_write_manifest,
    build_side_by_side as util_build_side_by_side,
)
from pipeline.utils.io_utils import (
    copy_file as util_copy_file,
    read_json as util_read_json,
    safe_filename as util_safe_filename,
    write_json as util_write_json,
)
from pipeline.utils.timing import StageTimers, stage_timer
from pipeline.models.dto import DocTypeCheck, ExtractorResult


logger = logging.getLogger(__name__)


def _count_pdf_pages(path: str) -> int | None:
    try:
        import pypdf as _pypdf  # type: ignore

        try:
            reader = _pypdf.PdfReader(path)
            return len(reader.pages)
        except Exception as e:
            logger.debug("pypdf reader failed: %s", e, exc_info=True)
    except Exception:
        pass
    try:
        import PyPDF2 as _pypdf2  # type: ignore

        try:
            reader = _pypdf2.PdfReader(path)
            return len(reader.pages)
        except Exception:
            pass
    except Exception:
        pass
    try:
        with open(path, "rb") as f:
            data = f.read()
        import re as _re

        return len(_re.findall(rb"/Type\s*/Page\b", data)) or None
    except Exception:
        return None


def _generate_run_id() -> str:
    """Generate a unique run identifier using UUID4.
    
    Returns:
        A UUID4 string (e.g., '550e8400-e29b-41d4-a716-446655440000')
    """
    return str(uuid.uuid4())


def _mk_run_dirs(runs_root: Path, run_id: str) -> dict[str, Path]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_dir = runs_root / date_str / run_id
    input_dir = base_dir / "input" / "original"
    ocr_dir = base_dir / "ocr"
    llm_dir = base_dir / "llm"
    meta_dir = base_dir / "meta"
    validation_dir = base_dir / "validation"
    for d in (input_dir, ocr_dir, llm_dir, meta_dir, validation_dir):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "base": base_dir,
        "input": input_dir,
        "ocr": ocr_dir,
        "llm": llm_dir,
        "meta": meta_dir,
        "validation": validation_dir,
    }


@dataclass
class PipelineContext:
    fio: str | None
    source_file_path: str
    original_filename: str
    content_type: str | None
    runs_root: Path
    run_id: str
    request_created_at: str
    dirs: dict[str, Path]
    saved_path: Path | None = None
    size_bytes: int | None = None
    pages_obj: dict[str, Any] | None = None
    timers: StageTimers = field(default_factory=StageTimers)
    t0: float = field(default_factory=time.perf_counter)
    errors: list[dict[str, Any]] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)

    @property
    def base_dir(self) -> Path:
        return self.dirs["base"]

    @property
    def input_dir(self) -> Path:
        return self.dirs["input"]

    @property
    def ocr_dir(self) -> Path:
        return self.dirs["ocr"]

    @property
    def llm_dir(self) -> Path:
        return self.dirs["llm"]

    @property
    def meta_dir(self) -> Path:
        return self.dirs["meta"]

    @property
    def validation_dir(self) -> Path:
        return self.dirs["validation"]


def _finalize_timing_artifacts(ctx: PipelineContext) -> None:
    ctx.artifacts["duration_seconds"] = time.perf_counter() - ctx.t0
    ctx.artifacts["ocr_seconds"] = ctx.timers.totals.get("ocr", 0.0)
    ctx.artifacts["llm_seconds"] = ctx.timers.totals.get("llm", 0.0)


def fail_and_finalize(code: str, details: str | None, ctx: PipelineContext) -> dict[str, Any]:
    ctx.errors.append(make_error(code, details=details))
    _finalize_timing_artifacts(ctx)
    final_path = ctx.meta_dir / "final_result.json"
    result = util_build_final_result(
        run_id=ctx.run_id,
        errors=ctx.errors,
        verdict=False,
        checks=None,
        final_path=final_path,
        meta_dir=ctx.meta_dir,
    )
    ctx.artifacts["final_result_path"] = str(final_path)
    saved_path_str = str(ctx.saved_path) if ctx.saved_path is not None else str(
        ctx.input_dir / util_safe_filename(ctx.original_filename or os.path.basename(ctx.source_file_path))
    )
    util_write_manifest(
        meta_dir=ctx.meta_dir,
        run_id=ctx.run_id,
        user_input={"fio": ctx.fio or None},
        file_info={
            "original_filename": ctx.original_filename,
            "saved_path": saved_path_str,
            "content_type": ctx.content_type,
            "size_bytes": ctx.size_bytes,
        },
        artifacts=ctx.artifacts,
        status="error",
        error=code,
        created_at=ctx.request_created_at,
    )
    return result


def finalize_success(verdict: bool, checks: dict[str, Any] | None, ctx: PipelineContext) -> dict[str, Any]:
    _finalize_timing_artifacts(ctx)
    final_path = ctx.meta_dir / "final_result.json"
    result = util_build_final_result(
        run_id=ctx.run_id,
        errors=ctx.errors,
        verdict=verdict,
        checks=checks,
        final_path=final_path,
        meta_dir=ctx.meta_dir,
    )
    ctx.artifacts["final_result_path"] = str(final_path)
    util_write_manifest(
        meta_dir=ctx.meta_dir,
        run_id=ctx.run_id,
        user_input={"fio": ctx.fio or None},
        file_info={
            "original_filename": ctx.original_filename,
            "saved_path": str(ctx.saved_path) if ctx.saved_path is not None else None,
            "content_type": ctx.content_type,
            "size_bytes": ctx.size_bytes,
        },
        artifacts=ctx.artifacts,
        status="success",
        error=None,
        created_at=ctx.request_created_at,
    )
    return result


def stage_acquire(ctx: PipelineContext) -> dict[str, Any] | None:
    base_name = util_safe_filename(ctx.original_filename or os.path.basename(ctx.source_file_path))
    ctx.saved_path = ctx.input_dir / base_name
    try:
        util_copy_file(ctx.source_file_path, ctx.saved_path)
    except Exception as e:
        return fail_and_finalize("FILE_SAVE_FAILED", str(e), ctx)

    try:
        ctx.size_bytes = ctx.saved_path.stat().st_size
    except Exception:
        ctx.size_bytes = None

    metadata = {"fio": ctx.fio or None}
    util_write_json(ctx.meta_dir / METADATA_FILENAME, metadata)

    if ctx.saved_path.suffix.lower() == ".pdf":
        pages = _count_pdf_pages(str(ctx.saved_path))
        if pages is not None and pages > MAX_PDF_PAGES:
            return fail_and_finalize("PDF_TOO_MANY_PAGES", None, ctx)
    return None


def stage_ocr(ctx: PipelineContext) -> dict[str, Any] | None:
    with stage_timer(ctx, "ocr"):
        ocr_result = ask_tesseract(str(ctx.saved_path), output_dir=str(ctx.ocr_dir), save_json=True)
    if not ocr_result.get("success"):
        return fail_and_finalize("OCR_FAILED", str(ocr_result.get("error")), ctx)

    try:
        filtered_pages_path = filter_ocr_response(
            ocr_result.get("raw_obj", {}), str(ctx.ocr_dir), filename=OCR_PAGES
        )
        ctx.artifacts["ocr_pages_filtered_path"] = str(filtered_pages_path)
        pages_obj = util_read_json(filtered_pages_path)
        if not isinstance(pages_obj, dict) or not isinstance(pages_obj.get("pages"), list):
            raise ValueError("Invalid pages object")
        if len(pages_obj["pages"]) == 0:
            return fail_and_finalize("OCR_EMPTY_PAGES", None, ctx)
        ctx.pages_obj = pages_obj
        return None
    except Exception as e:
        return fail_and_finalize("OCR_FILTER_FAILED", str(e), ctx)


def stage_doc_type_check(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            dtc_raw_str = check_single_doc_type(ctx.pages_obj)
        dtc_raw_path = ctx.llm_dir / LLM_DOC_TYPE_RAW
        with open(dtc_raw_path, "w", encoding="utf-8") as f:
            f.write(dtc_raw_str or "")
        try:
            dtc_filtered_path = filter_llm_generic_response(
                str(dtc_raw_path), str(ctx.llm_dir), filename=LLM_DOC_TYPE_FILTERED
            )
            ctx.artifacts["llm_doc_type_check_filtered_path"] = str(dtc_filtered_path)
            dtc_obj = util_read_json(dtc_filtered_path)
        except Exception as e:
            return fail_and_finalize("LLM_FILTER_PARSE_ERROR", str(e), ctx)
        try:
            dtc = DocTypeCheck.model_validate(dtc_obj if isinstance(dtc_obj, dict) else {})
        except Exception:
            return fail_and_finalize("DTC_PARSE_ERROR", None, ctx)
        is_single = getattr(dtc, "single_doc_type", None)
        if not isinstance(is_single, bool):
            return fail_and_finalize("DTC_PARSE_ERROR", None, ctx)
        if is_single is False:
            return fail_and_finalize("MULTIPLE_DOCUMENTS", None, ctx)
        return None
    except Exception as e:
        return fail_and_finalize("DTC_FAILED", str(e), ctx)


def stage_extract(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            llm_raw = extract_doc_data(ctx.pages_obj)
            llm_raw_path = ctx.llm_dir / LLM_EXTRACTOR_RAW
            with open(llm_raw_path, "w", encoding="utf-8") as f:
                f.write(llm_raw or "")
            try:
                filtered_path = filter_llm_generic_response(
                    str(llm_raw_path), str(ctx.llm_dir), filename=LLM_EXTRACTOR_FILTERED
                )
            except Exception as e:
                return fail_and_finalize("LLM_FILTER_PARSE_ERROR", str(e), ctx)
        try:
            os.remove(llm_raw_path)
        except Exception as e:
            logger.debug("Failed to remove llm_raw_path: %s", e, exc_info=True)
        ctx.artifacts["llm_extractor_filtered_path"] = str(filtered_path)
        try:
            filtered_obj = util_read_json(filtered_path)
        except Exception as e:
            return fail_and_finalize("LLM_FILTER_PARSE_ERROR", str(e), ctx)
        try:
            ext = ExtractorResult.model_validate(filtered_obj if isinstance(filtered_obj, dict) else {})
        except Exception as ve:
            raise ValueError("Extractor filtered object is invalid") from ve
        if not hasattr(ext, "fio") or not hasattr(ext, "doc_date"):
            raise ValueError("Missing key: required fields")
        if ext.fio is not None and not isinstance(ext.fio, str):
            raise ValueError("Key fio has invalid type")
        if ext.doc_date is not None and not isinstance(ext.doc_date, str):
            raise ValueError("Key doc_date has invalid type")
        return None
    except ValueError as ve:
        return fail_and_finalize("EXTRACT_SCHEMA_INVALID", str(ve), ctx)
    except Exception as e:
        return fail_and_finalize("EXTRACT_FAILED", str(e), ctx)


def stage_merge(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            merged_path = merge_extractor_and_doc_type(
                extractor_filtered_path=ctx.artifacts.get("llm_extractor_filtered_path", ""),
                doc_type_filtered_path=ctx.artifacts.get("llm_doc_type_check_filtered_path", ""),
                output_dir=str(ctx.llm_dir),
                filename=MERGED_FILENAME,
            )
        ctx.artifacts["llm_merged_path"] = str(merged_path)
        try:
            util_build_side_by_side(
                meta_dir=ctx.meta_dir,
                merged_path=merged_path,
                request_created_at=ctx.request_created_at,
            )
        except Exception:
            pass
        return None
    except Exception as e:
        return fail_and_finalize("MERGE_FAILED", str(e), ctx)


def stage_validate_and_finalize(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            validation = validate_run(
                meta_path=str(ctx.meta_dir / METADATA_FILENAME),
                merged_path=str(ctx.artifacts.get("llm_merged_path", "")),
                output_dir=str(ctx.validation_dir),
                filename=VALIDATION_FILENAME,
                write_file=False,
            )
        if not validation.get("success"):
            return fail_and_finalize("VALIDATION_FAILED", str(validation.get("error")), ctx)

        val_result = validation.get("result", {})
        checks = val_result.get("checks") if isinstance(val_result, dict) else None
        verdict = bool(val_result.get("verdict")) if isinstance(val_result, dict) else False
        check_errors: list[dict[str, Any]] = []
        if isinstance(checks, dict):
            fm = checks.get("fio_match")
            if fm is False:
                check_errors.append(make_error("FIO_MISMATCH"))
            elif fm is None:
                check_errors.append(make_error("FIO_MISSING"))

            dtk = checks.get("doc_type_known")
            if dtk is False or dtk is None:
                check_errors.append(make_error("DOC_TYPE_UNKNOWN"))

            dv = checks.get("doc_date_valid")
            if dv is False:
                check_errors.append(make_error("DOC_DATE_TOO_OLD"))
            elif dv is None:
                check_errors.append(make_error("DOC_DATE_MISSING"))
        ctx.errors.extend(check_errors)
        return finalize_success(verdict=verdict, checks=checks, ctx=ctx)
    except Exception as e:
        return fail_and_finalize("VALIDATION_FAILED", str(e), ctx)


def run_pipeline(
    fio: str | None,
    source_file_path: str,
    original_filename: str,
    content_type: str | None,
    runs_root: Path,
) -> dict[str, Any]:
    """
    Run the full RB-OCR pipeline for a single input document.

    Args:
      fio: Optional FIO string from the request context.
      source_file_path: Path to the uploaded file on disk.
      original_filename: Original filename as provided by the client.
      content_type: Optional MIME type of the uploaded file.
      runs_root: Root directory where per-run artifacts are stored.

    Returns:
      A dict containing the final pipeline result with keys like
      ``verdict``, ``errors``, and ``final_result_path``. On failure,
      errors are encoded via standardized error codes.
    """

    run_id = _generate_run_id()
    request_created_at = datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).strftime("%d.%m.%Y")
    dirs = _mk_run_dirs(runs_root, run_id)

    ctx = PipelineContext(
        fio=fio,
        source_file_path=source_file_path,
        original_filename=original_filename,
        content_type=content_type,
        runs_root=runs_root,
        run_id=run_id,
        request_created_at=request_created_at,
        dirs=dirs,
    )

    for stage in (
        stage_acquire,
        stage_ocr,
        stage_doc_type_check,
        stage_extract,
        stage_merge,
        stage_validate_and_finalize,
    ):
        res = stage(ctx)
        if res is not None:
            return res

    return fail_and_finalize("UNKNOWN_ERROR", None, ctx)
