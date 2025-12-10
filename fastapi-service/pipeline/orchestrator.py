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
    MAX_PDF_PAGES,
    UTC_OFFSET_HOURS,
    INPUT_FILE,
    OCR_FILTERED,
    LLM_DTC_RAW,
    LLM_DTC_FILTERED,
    LLM_EXT_RAW,
    LLM_EXT_FILTERED,
    FINAL_JSON,
)
from pipeline.core.errors import make_error
from pipeline.processors.agent_doc_type_checker import check_single_doc_type
from pipeline.processors.agent_extractor import extract_doc_data
from pipeline.processors.filter_llm_generic_response import filter_llm_generic_response
from pipeline.processors.filter_ocr_response import filter_ocr_response
from pipeline.processors.validator import validate_run
from pipeline.utils.io_utils import (
    copy_file as util_copy_file,
    read_json as util_read_json,
    write_json as util_write_json,
)
from pipeline.utils.timing import StageTimers, stage_timer
from pipeline.models.dto import DocTypeCheck, ExtractorResult


logger = logging.getLogger(__name__)


def _count_pdf_pages(pdf_file_path: str) -> int | None:
    try:
        import pypdf as _pypdf  # type: ignore

        try:
            reader = _pypdf.PdfReader(pdf_file_path)
            return len(reader.pages)
        except Exception as e:
            logger.debug("pypdf reader failed: %s", e, exc_info=True)
    except Exception:
        pass
    try:
        import PyPDF2 as _pypdf2  # type: ignore

        try:
            reader = _pypdf2.PdfReader(pdf_file_path)
            return len(reader.pages)
        except Exception:
            pass
    except Exception:
        pass
    try:
        with open(pdf_file_path, "rb") as f:
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
    base_dir.mkdir(parents=True, exist_ok=True)
    return {"base": base_dir}


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
    
    # Trace ID from middleware
    trace_id: str | None = None
    
    # Kafka/external metadata from request
    external_request_id: str | None = None
    external_s3_path: str | None = None
    external_iin: str | None = None
    external_first_name: str | None = None
    external_last_name: str | None = None
    external_second_name: str | None = None
    
    # Cache parsed results to eliminate redundant file reads
    extractor_result: dict[str, Any] | None = None
    doc_type_result: dict[str, Any] | None = None

    @property
    def base_dir(self) -> Path:
        return self.dirs["base"]


def _finalize_timing_artifacts(ctx: PipelineContext) -> None:
    ctx.artifacts["duration_seconds"] = time.perf_counter() - ctx.t0
    ctx.artifacts["ocr_seconds"] = ctx.timers.totals.get("ocr", 0.0)
    ctx.artifacts["llm_seconds"] = ctx.timers.totals.get("llm", 0.0)


def fail_and_finalize(code: str, details: str | None, ctx: PipelineContext) -> dict[str, Any]:
    """Finalize pipeline with system error (status='error')."""
    from pipeline.utils.db_record import FinalJsonBuilder, ExternalMetadata
    from pipeline.core.errors import ErrorCode
    
    ctx.errors.append(make_error(code, details=details))
    _finalize_timing_artifacts(ctx)  # Calculates ctx.artifacts["duration_seconds"]
    
    # Get error specification from centralized registry
    error_spec = ErrorCode.get_spec(code)
    
    # Use pipeline-internal timing
    processing_time = ctx.artifacts.get("duration_seconds", 0.0)
    completed_at = datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).isoformat()
    
    # Build using fluent interface
    final_json = (
        FinalJsonBuilder(ctx.run_id, ctx.trace_id, ctx.request_created_at)
        .with_external_metadata(ExternalMetadata(
            request_id=ctx.external_request_id,
            s3_path=ctx.external_s3_path,
            iin=ctx.external_iin,
            first_name=ctx.external_first_name,
            last_name=ctx.external_last_name,
            second_name=ctx.external_second_name,
        ))
        .with_error(code, error_spec.message_ru, error_spec.category, error_spec.retryable)
        .with_timing(completed_at, processing_time)
        .build()
    )
    
    # Write final.json
    final_path = ctx.base_dir / FINAL_JSON
    util_write_json(final_path, final_json)
    ctx.artifacts["final_result_path"] = str(final_path)
    
    return {
        "run_id": ctx.run_id,
        "verdict": False,
        "errors": ctx.errors,
        "final_result_path": str(final_path),
    }


def finalize_success(verdict: bool, checks: dict[str, Any] | None, ctx: PipelineContext) -> dict[str, Any]:
    """Finalize pipeline with successful completion (status='success')."""
    from pipeline.utils.db_record import FinalJsonBuilder, ExternalMetadata, ExtractedData, RuleChecks
    
    _finalize_timing_artifacts(ctx)
    
    extractor_data = ctx.extractor_result or {}
    doc_type_data = ctx.doc_type_result or {}
    
    rule_errors = [error["code"] for error in ctx.errors]
    
    # Use pipeline-internal timing
    processing_time = ctx.artifacts.get("duration_seconds", 0.0)
    completed_at = datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).isoformat()
    
    # Build using fluent interface
    final_json = (
        FinalJsonBuilder(ctx.run_id, ctx.trace_id, ctx.request_created_at)
        .with_external_metadata(ExternalMetadata(
            request_id=ctx.external_request_id,
            s3_path=ctx.external_s3_path,
            iin=ctx.external_iin,
            first_name=ctx.external_first_name,
            last_name=ctx.external_last_name,
            second_name=ctx.external_second_name,
        ))
        .with_success(
            extracted=ExtractedData(
                fio=extractor_data.get("fio"),
                doc_date=extractor_data.get("doc_date"),
                single_doc_type=doc_type_data.get("single_doc_type"),
                doc_type_known=doc_type_data.get("doc_type_known"),
                doc_type=_format_doc_type(doc_type_data.get("detected_doc_types")),
            ),
            checks=RuleChecks(
                fio_match=checks.get("fio_match") if checks else None,
                doc_date_valid=checks.get("doc_date_valid") if checks else None,
                doc_type_known=checks.get("doc_type_known") if checks else None,
                single_doc_type=doc_type_data.get("single_doc_type"),
            ),
            verdict=verdict,
            rule_errors=rule_errors,
        )
        .with_timing(completed_at, processing_time)
        .build()
    )
    
    # Write final.json
    final_path = ctx.base_dir / FINAL_JSON
    util_write_json(final_path, final_json)
    ctx.artifacts["final_result_path"] = str(final_path)
    
    return {
        "run_id": ctx.run_id,
        "verdict": verdict,
        "errors": ctx.errors,
        "final_result_path": str(final_path),
    }


def _format_doc_type(detected_types: list | None) -> str | None:
    """Convert list of detected types to single string."""
    if not detected_types:
        return None
    if isinstance(detected_types, list) and len(detected_types) > 0:
        return detected_types[0]
    return None


def stage_acquire(ctx: PipelineContext) -> dict[str, Any] | None:
    ext = Path(ctx.original_filename).suffix or ".bin"
    ctx.saved_path = ctx.base_dir / INPUT_FILE.format(ext=ext)
    try:
        util_copy_file(ctx.source_file_path, ctx.saved_path)
    except Exception as e:
        return fail_and_finalize("FILE_SAVE_FAILED", str(e), ctx)

    try:
        ctx.size_bytes = ctx.saved_path.stat().st_size
    except Exception:
        ctx.size_bytes = None

    if ctx.saved_path.suffix.lower() == ".pdf":
        pages = _count_pdf_pages(str(ctx.saved_path))
        if pages is not None and pages > MAX_PDF_PAGES:
            return fail_and_finalize("PDF_TOO_MANY_PAGES", None, ctx)
    return None


def stage_ocr(ctx: PipelineContext) -> dict[str, Any] | None:
    with stage_timer(ctx, "ocr"):
        ocr_result = ask_tesseract(str(ctx.saved_path), output_dir=str(ctx.base_dir), save_json=False)
    if not ocr_result.get("success"):
        return fail_and_finalize("OCR_FAILED", str(ocr_result.get("error")), ctx)

    try:
        filtered_pages_path = filter_ocr_response(
            ocr_result.get("raw_obj", {}), str(ctx.base_dir), filename=OCR_FILTERED
        )
        ctx.artifacts["pages_filtered_path"] = str(filtered_pages_path)
        data_obj = util_read_json(filtered_pages_path)
        ctx.pages_obj = data_obj.get("pages", []) if isinstance(data_obj, dict) else []
        if not ctx.pages_obj or not isinstance(ctx.pages_obj, list) or len(ctx.pages_obj) == 0:
            return fail_and_finalize("OCR_EMPTY_PAGES", None, ctx)
    except Exception as e:
        return fail_and_finalize("OCR_FILTER_FAILED", str(e), ctx)
    return None


def stage_doc_type_check(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            doc_type_check_raw_json = check_single_doc_type(ctx.pages_obj)
        
        try:
            dtc_raw_path = ctx.base_dir / LLM_DTC_RAW
            with open(dtc_raw_path, "w", encoding="utf-8") as f:
                f.write(doc_type_check_raw_json or "")
            
            dtc_filtered_path = filter_llm_generic_response(
                str(dtc_raw_path), str(ctx.base_dir), filename=LLM_DTC_FILTERED
            )
            
            try:
                os.remove(dtc_raw_path)
            except Exception as e:
                logger.debug("Failed to remove dtc_raw_path: %s", e, exc_info=True)
            
            ctx.artifacts["llm_doc_type_check_filtered_path"] = str(dtc_filtered_path)
            dtc_obj = util_read_json(dtc_filtered_path)
            ctx.doc_type_result = dtc_obj if isinstance(dtc_obj, dict) else {}
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
        
        # Process in-memory (NO RAW FILE WRITE)
        # Write raw string temporarily for filter function (it expects a file path)
        llm_raw_path = ctx.base_dir / LLM_EXT_RAW
        with open(llm_raw_path, "w", encoding="utf-8") as f:
            f.write(llm_raw or "")
        
        try:
            filtered_path = filter_llm_generic_response(
                str(llm_raw_path), str(ctx.base_dir), filename=LLM_EXT_FILTERED
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
        
        ctx.extractor_result = filtered_obj if isinstance(filtered_obj, dict) else {}
        
        try:
            extractor_result = ExtractorResult.model_validate(ctx.extractor_result)
        except Exception as ve:
            raise ValueError("Extractor filtered object is invalid") from ve
        if not hasattr(extractor_result, "fio") or not hasattr(extractor_result, "doc_date"):
            raise ValueError("Missing key: required fields")
        if extractor_result.fio is not None and not isinstance(extractor_result.fio, str):
            raise ValueError("Key fio has invalid type")
        if extractor_result.doc_date is not None and not isinstance(extractor_result.doc_date, str):
            raise ValueError("Key doc_date has invalid type")
        return None
    except ValueError as ve:
        return fail_and_finalize("EXTRACT_SCHEMA_INVALID", str(ve), ctx)
    except Exception as e:
        return fail_and_finalize("EXTRACT_FAILED", str(e), ctx)


def stage_validate_and_finalize(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            validation = validate_run(
                user_provided_fio={"fio": ctx.fio},
                extractor_data=ctx.extractor_result,
                doc_type_data=ctx.doc_type_result,
            )
        if not validation.get("success"):
            return fail_and_finalize("VALIDATION_FAILED", str(validation.get("error")), ctx)

        val_result = validation.get("result", {})
        checks = val_result.get("checks") if isinstance(val_result, dict) else None
        verdict = bool(val_result.get("verdict")) if isinstance(val_result, dict) else False
        check_errors: list[dict[str, Any]] = []
        if isinstance(checks, dict):
            fio_match_result = checks.get("fio_match")
            if fio_match_result is False:
                check_errors.append(make_error("FIO_MISMATCH"))
            elif fio_match_result is None:
                check_errors.append(make_error("FIO_MISSING"))

            doc_type_known = checks.get("doc_type_known")
            if doc_type_known is False or doc_type_known is None:
                check_errors.append(make_error("DOC_TYPE_UNKNOWN"))

            doc_date_valid = checks.get("doc_date_valid")
            if doc_date_valid is False:
                check_errors.append(make_error("DOC_DATE_TOO_OLD"))
            elif doc_date_valid is None:
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
    external_metadata: dict[str, Any] | None = None,  # NEW
) -> dict[str, Any]:
    """
    Run the full RB-OCR pipeline for a single input document.

    Args:
      fio: Optional FIO string from the request context.
      source_file_path: Path to the uploaded file on disk.
      original_filename: Original filename as provided by the client.
      content_type: Optional MIME type of the uploaded file.
      runs_root: Root directory where per-run artifacts are stored.
      external_metadata: Optional dict with trace_id and Kafka metadata.

    Returns:
      A dict containing the final pipeline result with keys like
      ``verdict``, ``errors``, and ``final_result_path``. On failure,
      errors are encoded via standardized error codes.
    """

    run_id = _generate_run_id()
    request_created_at = datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).isoformat()
    dirs = _mk_run_dirs(runs_root, run_id)
    
    # Extract external metadata if provided
    ext_meta = external_metadata or {}

    ctx = PipelineContext(
        fio=fio,
        source_file_path=source_file_path,
        original_filename=original_filename,
        content_type=content_type,
        runs_root=runs_root,
        run_id=run_id,
        request_created_at=request_created_at,
        dirs=dirs,
        trace_id=ext_meta.get("trace_id"),
        external_request_id=ext_meta.get("external_request_id"),
        external_s3_path=ext_meta.get("external_s3_path"),
        external_iin=ext_meta.get("external_iin"),
        external_first_name=ext_meta.get("external_first_name"),
        external_last_name=ext_meta.get("external_last_name"),
        external_second_name=ext_meta.get("external_second_name"),
    )

    for stage in (
        stage_acquire,
        stage_ocr,
        stage_doc_type_check,
        stage_extract,
        stage_validate_and_finalize,
    ):
        stage_result = stage(ctx)
        if stage_result is not None:
            return stage_result

    return fail_and_finalize("UNKNOWN_ERROR", None, ctx)
