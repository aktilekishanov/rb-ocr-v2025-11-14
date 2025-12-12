"""
RB-OCR pipeline orchestrator for main-dev.

Coordinates per-run directory layout, staged processing
(acquire, OCR, LLM doc-type check, extraction, merge, validation),
error handling,timing, and artifact/manifest writing.
Public entrypoint: `run_pipeline`.
"""

from __future__ import annotations

import logging
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
    OCR_RESULT_FILE,
    LLM_DTC_RESULT_FILE,
    LLM_EXT_RESULT_FILE,
    FINAL_RESULT_FILE,
)
from pipeline.core.errors import make_error
from pipeline.processors.agent_doc_type_checker import check_single_doc_type
from pipeline.processors.agent_extractor import extract_doc_data
from pipeline.utils.parsers import parse_ocr_output, parse_llm_output
from pipeline.processors.validator import validate_run
from pipeline.utils.io_utils import (
    copy_file as util_copy_file,
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
    """Calculate and store timing artifacts in context."""
    ctx.artifacts["duration_seconds"] = time.perf_counter() - ctx.t0
    ctx.artifacts["ocr_seconds"] = ctx.timers.totals.get("ocr", 0.0)
    ctx.artifacts["llm_seconds"] = ctx.timers.totals.get("llm", 0.0)


def _build_external_metadata_obj(ctx: PipelineContext):
    """Build ExternalMetadata object from context."""
    from pipeline.utils.db_record import ExternalMetadata

    return ExternalMetadata(
        request_id=ctx.external_request_id,
        s3_path=ctx.external_s3_path,
        iin=ctx.external_iin,
        first_name=ctx.external_first_name,
        last_name=ctx.external_last_name,
        second_name=ctx.external_second_name,
    )


def _build_error_final_json(ctx: PipelineContext, code: str) -> dict[str, Any]:
    """Build final JSON structure for error case."""
    from pipeline.utils.db_record import FinalJsonBuilder
    from pipeline.core.errors import ErrorCode

    error_spec = ErrorCode.get_spec(code)
    processing_time = ctx.artifacts.get("duration_seconds", 0.0)
    completed_at = datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).isoformat()

    return (
        FinalJsonBuilder(ctx.run_id, ctx.trace_id, ctx.request_created_at)
        .with_external_metadata(_build_external_metadata_obj(ctx))
        .with_error(
            code, error_spec.message_ru, error_spec.category, error_spec.retryable
        )
        .with_timing(completed_at, processing_time)
        .build()
    )


def _write_final_json(ctx: PipelineContext, final_json: dict[str, Any]) -> str:
    """Write final.json to disk and return path."""
    final_path = ctx.base_dir / FINAL_RESULT_FILE
    util_write_json(final_path, final_json)
    ctx.artifacts["final_result_path"] = str(final_path)
    return str(final_path)


def handle_pipeline_failure(
    code: str, details: str | None, ctx: PipelineContext
) -> dict[str, Any]:
    """Handle pipeline failure by appending error, building final JSON, and writing to disk."""
    ctx.errors.append(make_error(code, details=details))
    _finalize_timing_artifacts(ctx)

    final_json = _build_error_final_json(ctx, code)
    final_path = _write_final_json(ctx, final_json)

    return {
        "run_id": ctx.run_id,
        "verdict": False,
        "errors": ctx.errors,
        "final_result_path": final_path,
    }


def _extract_final_data(ctx: PipelineContext) -> tuple[dict, dict, list[str]]:
    """Extract data needed for final JSON from context."""
    extractor_data = ctx.extractor_result or {}
    doc_type_data = ctx.doc_type_result or {}
    rule_errors = [error["code"] for error in ctx.errors]
    return extractor_data, doc_type_data, rule_errors


def _build_success_final_json(
    ctx: PipelineContext, verdict: bool, checks: dict[str, Any] | None
) -> dict[str, Any]:
    """Build final JSON structure for success case."""
    from pipeline.utils.db_record import (
        FinalJsonBuilder,
        ExtractedData,
        RuleChecks,
    )

    extractor_data, doc_type_data, rule_errors = _extract_final_data(ctx)
    processing_time = ctx.artifacts.get("duration_seconds", 0.0)
    completed_at = datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).isoformat()

    return (
        FinalJsonBuilder(ctx.run_id, ctx.trace_id, ctx.request_created_at)
        .with_external_metadata(_build_external_metadata_obj(ctx))
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


def finalize_success(
    verdict: bool, checks: dict[str, Any] | None, ctx: PipelineContext
) -> dict[str, Any]:
    """Finalize pipeline with successful completion."""
    _finalize_timing_artifacts(ctx)
    final_json = _build_success_final_json(ctx, verdict, checks)
    final_path = _write_final_json(ctx, final_json)

    return {
        "run_id": ctx.run_id,
        "verdict": verdict,
        "errors": ctx.errors,
        "final_result_path": final_path,
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
        return handle_pipeline_failure("FILE_SAVE_FAILED", str(e), ctx)

    try:
        ctx.size_bytes = ctx.saved_path.stat().st_size
    except Exception:
        ctx.size_bytes = None

    if ctx.saved_path.suffix.lower() == ".pdf":
        pages = _count_pdf_pages(str(ctx.saved_path))
        if pages is not None and pages > MAX_PDF_PAGES:
            return handle_pipeline_failure("PDF_TOO_MANY_PAGES", None, ctx)
    return None


def stage_ocr(ctx: PipelineContext) -> dict[str, Any] | None:
    with stage_timer(ctx, "ocr"):
        ocr_result = ask_tesseract(
            str(ctx.saved_path), output_dir=str(ctx.base_dir), save_json=False
        )
    if not ocr_result.get("success"):
        return handle_pipeline_failure("OCR_FAILED", str(ocr_result.get("error")), ctx)

    try:
        # Parse OCR output in-memory
        pages = parse_ocr_output(ocr_result.get("raw_obj", {}))

        # Save parsed result to disk
        util_write_json(ctx.base_dir / OCR_RESULT_FILE, {"pages": pages})

        ctx.pages_obj = pages
        if not ctx.pages_obj or len(ctx.pages_obj) == 0:
            return handle_pipeline_failure("OCR_EMPTY_PAGES", None, ctx)

    except Exception as e:
        return handle_pipeline_failure("OCR_FILTER_FAILED", str(e), ctx)
    return None


def stage_doc_type_check(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            doc_type_check_raw_str = check_single_doc_type(ctx.pages_obj)

        try:
            # Parse LLM output in-memory
            dtc_obj = parse_llm_output(doc_type_check_raw_str or "")

            # Save parsed result to disk
            util_write_json(ctx.base_dir / LLM_DTC_RESULT_FILE, dtc_obj)

            ctx.doc_type_result = dtc_obj
        except Exception as e:
            return handle_pipeline_failure("LLM_FILTER_PARSE_ERROR", str(e), ctx)

        try:
            dtc = DocTypeCheck.model_validate(ctx.doc_type_result)
        except Exception:
            return handle_pipeline_failure("DTC_PARSE_ERROR", None, ctx)

        is_single = getattr(dtc, "single_doc_type", None)
        if not isinstance(is_single, bool):
            return handle_pipeline_failure("DTC_PARSE_ERROR", None, ctx)
        if is_single is False:
            return handle_pipeline_failure("MULTIPLE_DOCUMENTS", None, ctx)
        return None
    except Exception as e:
        return handle_pipeline_failure("DTC_FAILED", str(e), ctx)


def stage_extract(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            llm_raw_str = extract_doc_data(ctx.pages_obj)

        try:
            # Parse LLM output in-memory
            extractor_obj = parse_llm_output(llm_raw_str or "")

            # Save parsed result to disk
            util_write_json(ctx.base_dir / LLM_EXT_RESULT_FILE, extractor_obj)

            ctx.extractor_result = extractor_obj
        except Exception as e:
            return handle_pipeline_failure("LLM_FILTER_PARSE_ERROR", str(e), ctx)

        try:
            extractor_result = ExtractorResult.model_validate(ctx.extractor_result)
        except Exception as ve:
            raise ValueError("Extractor filtered object is invalid") from ve
        if not hasattr(extractor_result, "fio") or not hasattr(
            extractor_result, "doc_date"
        ):
            raise ValueError("Missing key: required fields")
        if extractor_result.fio is not None and not isinstance(
            extractor_result.fio, str
        ):
            raise ValueError("Key fio has invalid type")
        if extractor_result.doc_date is not None and not isinstance(
            extractor_result.doc_date, str
        ):
            raise ValueError("Key doc_date has invalid type")
        return None
    except ValueError as ve:
        return handle_pipeline_failure("EXTRACT_SCHEMA_INVALID", str(ve), ctx)
    except Exception as e:
        return handle_pipeline_failure("EXTRACT_FAILED", str(e), ctx)


def _build_check_errors(checks: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build list of validation errors from check results."""
    check_errors = []
    if not isinstance(checks, dict):
        return check_errors

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

    return check_errors


def stage_validate(ctx: PipelineContext) -> dict[str, Any] | None:
    """Validate the pipeline results and build error list."""
    try:
        with stage_timer(ctx, "llm"):
            validation = validate_run(
                user_provided_fio={"fio": ctx.fio},
                extractor_data=ctx.extractor_result,
                doc_type_data=ctx.doc_type_result,
            )
        if not validation.get("success"):
            return handle_pipeline_failure(
                "VALIDATION_FAILED", str(validation.get("error")), ctx
            )

        val_result = validation.get("result", {})
        checks = val_result.get("checks") if isinstance(val_result, dict) else None
        verdict = (
            bool(val_result.get("verdict")) if isinstance(val_result, dict) else False
        )

        check_errors = _build_check_errors(checks)
        ctx.errors.extend(check_errors)

        # Return validation results for finalization
        return {"verdict": verdict, "checks": checks}
    except Exception as e:
        return handle_pipeline_failure("VALIDATION_FAILED", str(e), ctx)


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
    request_created_at = datetime.now(
        timezone(timedelta(hours=UTC_OFFSET_HOURS))
    ).isoformat()
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

    # Run pipeline stages
    for stage in (
        stage_acquire,
        stage_ocr,
        stage_doc_type_check,
        stage_extract,
    ):
        stage_result = stage(ctx)
        if stage_result is not None:
            return stage_result

    # Validate and finalize (split into two steps for function purity)
    validation_result = stage_validate(ctx)
    if validation_result is None:
        return handle_pipeline_failure("UNKNOWN_ERROR", None, ctx)

    # Check if validation returned an error
    if "run_id" in validation_result:
        # This is an error result from handle_pipeline_failure
        return validation_result

    # Finalize with success
    return finalize_success(
        verdict=validation_result["verdict"],
        checks=validation_result["checks"],
        ctx=ctx,
    )
