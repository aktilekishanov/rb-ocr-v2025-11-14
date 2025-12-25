from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from pipeline.clients.tesseract_async_client import ask_tesseract
from pipeline.core.config import (
    FINAL_RESULT_FILE,
    INPUT_FILE,
    LLM_DTC_RESULT_FILE,
    LLM_EXT_RESULT_FILE,
    MAX_PDF_PAGES,
    OCR_RESULT_FILE,
    UTC_OFFSET_HOURS,
)
from pipeline.core.errors import ErrorCode, make_error
from pipeline.models.dto import DocTypeCheck, ExtractorResult
from pipeline.processors.agent_doc_type_checker import check_single_doc_type
from pipeline.processors.agent_extractor import extract_doc_data
from pipeline.processors.validator import validate_run
from pipeline.utils.io_utils import copy_file as util_copy_file
from pipeline.utils.io_utils import write_json as util_write_json
from pipeline.utils.parsers import parse_llm_output, parse_ocr_output

logger = logging.getLogger(__name__)


# Exceptions & utilities


class StageError(Exception):
    """Raised by stages to signal a pipeline failure with an error code and optional details."""

    def __init__(self, code: str, details: Optional[str] = None) -> None:
        super().__init__(f"{code}: {details}")
        self.code = code
        self.details = details


def _generate_run_id() -> str:
    return str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=UTC_OFFSET_HOURS))).isoformat()


def _detect_extension_from_file(file_path: str) -> str:
    """
    Detect file extension by reading magic bytes (file header).

    Supported formats:
        - PDF:  %PDF
        - JPEG: 0xFFD8
        - PNG:  0x89PNG

    Args:
        file_path: Path to binary file on disk

    Returns:
        Extension string without dot (e.g., 'pdf', 'jpg', 'png', 'bin')
    """
    try:
        with open(file_path, "rb") as f:
            header = f.read(8)  # Read first 8 bytes

        # PDF: %PDF-1.x
        if header.startswith(b"%PDF"):
            return "pdf"

        # JPEG: 0xFFD8FF
        if header.startswith(b"\xff\xd8"):
            return "jpg"

        # PNG: 0x89504E47
        if header.startswith(b"\x89PNG"):
            return "png"

    except Exception:
        # File read error or unrecognized format
        pass

    return "bin"


def _count_pdf_pages_sync(pdf_path: str) -> Optional[int]:
    """Synchronous PDF page counting (runs in thread pool).

    Try pypdf then PyPDF2 to count pages. Return None if both fail.
    This function is designed to run in a thread pool executor,
    so it's safe to block here.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Number of pages or None if counting fails
    """
    try:
        import pypdf as _pypdf  # type: ignore

        reader = _pypdf.PdfReader(pdf_path)
        page_count = len(reader.pages)
        logger.debug(f"PDF page count: {page_count} pages for {pdf_path}")
        return page_count
    except Exception:
        logger.debug("pypdf failed to count pages", exc_info=True)

    try:
        import PyPDF2 as _pypdf2  # type: ignore

        reader = _pypdf2.PdfReader(pdf_path)
        page_count = len(reader.pages)
        logger.debug(f"PDF page count (PyPDF2): {page_count} for {pdf_path}")
        return page_count
    except Exception:
        logger.debug("PyPDF2 failed to count pages", exc_info=True)

    return None


async def _count_pdf_pages_async(pdf_path: str) -> Optional[int]:
    """Async PDF page counting using thread pool executor.

    This runs the blocking PDF operation in a thread pool so the
    event loop remains responsive for other requests.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Number of pages or None if counting fails
    """
    import asyncio

    loop = asyncio.get_event_loop()

    try:
        page_count = await loop.run_in_executor(
            None,  # Use default ThreadPoolExecutor
            _count_pdf_pages_sync,
            pdf_path,
        )
        return page_count
    except Exception as e:
        logger.error(f"Failed to count PDF pages async: {e}", exc_info=True)
        return None


# Context & runner


@dataclass
class PipelineContext:
    fio: Optional[str]
    source_file_path: str
    original_filename: str
    content_type: Optional[str]
    runs_root: Path
    run_id: str
    request_created_at: str
    trace_id: Optional[str] = None

    # populated during run
    dirs: Dict[str, Path] = field(default_factory=dict)
    saved_path: Optional[Path] = None
    size_bytes: Optional[int] = None
    pages_obj: Optional[list] = None
    doc_type_result: Optional[dict] = None
    extractor_result: Optional[dict] = None
    t0: float = field(default_factory=time.perf_counter)
    errors: list[dict] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)

    # external metadata fields (optional)
    external_request_id: Optional[str] = None
    external_s3_path: Optional[str] = None
    external_iin: Optional[str] = None
    external_first_name: Optional[str] = None
    external_last_name: Optional[str] = None
    external_second_name: Optional[str] = None

    @property
    def base_dir(self) -> Path:
        return self.dirs["base"]


def _mk_run_dirs(runs_root: Path, run_id: str) -> Dict[str, Path]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_dir = runs_root / date_str / run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    return {"base": base_dir}


# Stage decorator


def stage(name: str) -> Callable:
    """Decorator to wrap stage functions and convert StageError to exception."""

    def deco(
        fn: Callable[[Any, PipelineContext], Any],
    ) -> Callable[[Any, PipelineContext], Any]:
        def wrapper(self, ctx: PipelineContext) -> Any:
            return fn(self, ctx)

        return wrapper

    return deco


# Pipeline runner


class PipelineRunner:
    def __init__(self, runs_root: Path) -> None:
        self.runs_root = runs_root
        self.logger = logger

    # Helpers for final JSON

    def _finalize_timing_artifacts(self, ctx: PipelineContext) -> None:
        ctx.artifacts["duration_seconds"] = time.perf_counter() - ctx.t0

    def _build_external_metadata_obj(self, ctx: PipelineContext):
        from pipeline.utils.db_record import ExternalMetadata

        return ExternalMetadata(
            request_id=ctx.external_request_id,
            s3_path=ctx.external_s3_path,
            iin=ctx.external_iin,
            first_name=ctx.external_first_name,
            last_name=ctx.external_last_name,
            second_name=ctx.external_second_name,
        )

    def _build_error_final_json(self, ctx: PipelineContext, code: str) -> dict:
        from pipeline.utils.db_record import FinalJsonBuilder

        error_spec = ErrorCode.get_spec(code)
        processing_time = ctx.artifacts.get("duration_seconds", 0.0)
        completed_at = _now_iso()

        return (
            FinalJsonBuilder(ctx.run_id, ctx.trace_id, ctx.request_created_at)
            .with_external_metadata(self._build_external_metadata_obj(ctx))
            .with_error(
                error_spec.int_code,
                error_spec.message_ru,
                error_spec.category,
                error_spec.retryable,
            )
            .with_timing(completed_at, processing_time)
            .build()
        )

    def _build_success_final_json(
        self, ctx: PipelineContext, verdict: bool, checks: dict | None
    ) -> dict:
        from pipeline.utils.db_record import ExtractedData, FinalJsonBuilder, RuleChecks

        extractor_data = ctx.extractor_result or {}
        doc_type_data = ctx.doc_type_result or {}
        rule_errors = [e["code"] for e in ctx.errors]

        processing_time = ctx.artifacts.get("duration_seconds", 0.0)
        completed_at = _now_iso()

        return (
            FinalJsonBuilder(ctx.run_id, ctx.trace_id, ctx.request_created_at)
            .with_external_metadata(self._build_external_metadata_obj(ctx))
            .with_success(
                extracted=ExtractedData(
                    fio=extractor_data.get("fio"),
                    doc_date=extractor_data.get("doc_date"),
                    single_doc_type=doc_type_data.get("single_doc_type"),
                    doc_type_known=doc_type_data.get("doc_type_known"),
                    doc_type=(doc_type_data.get("detected_doc_types") or [None])[0],
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

    def _write_final_json(self, ctx: PipelineContext, final_json: dict) -> str:
        final_path = ctx.base_dir / FINAL_RESULT_FILE
        util_write_json(final_path, final_json)
        ctx.artifacts["final_result_path"] = str(final_path)
        return str(final_path)

    # Stage implementations
    @stage("acquire")
    def _stage_acquire(self, ctx: PipelineContext) -> None:
        # Try filename extension first
        ext = Path(ctx.original_filename).suffix

        # If no extension in filename, detect from file content (magic bytes)
        if not ext:
            detected = _detect_extension_from_file(ctx.source_file_path)
            ext = f".{detected}"
            logger.info(
                f"Detected file type from magic bytes: {detected} "
                f"(filename: {ctx.original_filename})"
            )

        ctx.saved_path = ctx.base_dir / INPUT_FILE.format(ext=ext)
        try:
            util_copy_file(ctx.source_file_path, ctx.saved_path)
        except Exception as exc:
            raise StageError("FILE_SAVE_FAILED", str(exc))

        try:
            ctx.size_bytes = ctx.saved_path.stat().st_size
        except Exception:
            ctx.size_bytes = None

        if ctx.saved_path.suffix.lower() == ".pdf":
            pages = _count_pdf_pages(str(ctx.saved_path))
            if pages is not None and pages > MAX_PDF_PAGES:
                raise StageError("PDF_TOO_MANY_PAGES", None)

    @stage("ocr")
    def _stage_ocr(self, ctx: PipelineContext) -> None:
        try:
            ocr_result = ask_tesseract(
                str(ctx.saved_path), output_dir=str(ctx.base_dir), save_json=False
            )
        except Exception as exc:
            raise StageError("OCR_FAILED", f"OCR request failed: {exc}")

        if not ocr_result.get("success"):
            raise StageError("OCR_FAILED", str(ocr_result.get("error")))

        try:
            pages = parse_ocr_output(ocr_result.get("raw_obj", {}))
            util_write_json(ctx.base_dir / OCR_RESULT_FILE, {"pages": pages})
            ctx.pages_obj = pages
            if not ctx.pages_obj:
                raise StageError("OCR_EMPTY_PAGES", None)
        except StageError:
            raise
        except Exception as exc:
            raise StageError("OCR_FILTER_FAILED", str(exc))

    @stage("llm_doc_type")
    def _stage_doc_type_check(self, ctx: PipelineContext) -> None:
        try:
            raw = check_single_doc_type(ctx.pages_obj)
            dtc_obj = parse_llm_output(raw or "")
            util_write_json(ctx.base_dir / LLM_DTC_RESULT_FILE, dtc_obj)
            ctx.doc_type_result = dtc_obj
        except Exception as exc:
            raise StageError("LLM_FILTER_PARSE_ERROR", str(exc))

        try:
            dtc = DocTypeCheck.model_validate(ctx.doc_type_result)
        except Exception:
            raise StageError("DTC_PARSE_ERROR", None)

        is_single = getattr(dtc, "single_doc_type", None)
        if not isinstance(is_single, bool):
            raise StageError("DTC_PARSE_ERROR", None)
        if is_single is False:
            raise StageError("MULTIPLE_DOCUMENTS", None)

    @stage("llm_extractor")
    def _stage_extract(self, ctx: PipelineContext) -> None:
        try:
            raw = extract_doc_data(ctx.pages_obj)
            extractor_obj = parse_llm_output(raw or "")
            util_write_json(ctx.base_dir / LLM_EXT_RESULT_FILE, extractor_obj)
            ctx.extractor_result = extractor_obj
        except Exception as exc:
            raise StageError("LLM_FILTER_PARSE_ERROR", str(exc))

        # Validate extractor schema
        try:
            extractor_result = ExtractorResult.model_validate(ctx.extractor_result)
        except Exception as ve:
            raise StageError("EXTRACT_SCHEMA_INVALID", str(ve))

        # Basic required fields & types (preserve previous logic)
        if not hasattr(extractor_result, "fio") or not hasattr(
            extractor_result, "doc_date"
        ):
            raise StageError("EXTRACT_SCHEMA_INVALID", "Missing required fields")
        if extractor_result.fio is not None and not isinstance(
            extractor_result.fio, str
        ):
            raise StageError("EXTRACT_SCHEMA_INVALID", "Key fio has invalid type")
        if extractor_result.doc_date is not None and not isinstance(
            extractor_result.doc_date, str
        ):
            raise StageError("EXTRACT_SCHEMA_INVALID", "Key doc_date has invalid type")

    @stage("validate")
    def _stage_validate(self, ctx: PipelineContext) -> Tuple[bool, dict]:
        try:
            validation = validate_run(
                user_provided_fio={"fio": ctx.fio},
                extractor_data=ctx.extractor_result,
                doc_type_data=ctx.doc_type_result,
            )
        except Exception as exc:
            raise StageError("VALIDATION_FAILED", str(exc))

        if not validation.get("success"):
            raise StageError("VALIDATION_FAILED", str(validation.get("error")))

        val_result = validation.get("result", {})
        checks = val_result.get("checks") if isinstance(val_result, dict) else None
        verdict = (
            bool(val_result.get("verdict")) if isinstance(val_result, dict) else False
        )

        # Build check errors similarly to previous logic
        check_errors = []
        fio_match_result = checks.get("fio_match") if isinstance(checks, dict) else None
        if fio_match_result is False:
            check_errors.append(make_error("FIO_MISMATCH"))
        elif fio_match_result is None:
            check_errors.append(make_error("FIO_MISSING"))

        doc_type_known = (
            checks.get("doc_type_known") if isinstance(checks, dict) else None
        )
        if doc_type_known is False or doc_type_known is None:
            check_errors.append(make_error("DOC_TYPE_UNKNOWN"))

        doc_date_valid = (
            checks.get("doc_date_valid") if isinstance(checks, dict) else None
        )
        if doc_date_valid is False:
            check_errors.append(make_error("DOC_DATE_TOO_OLD"))
        elif doc_date_valid is None:
            check_errors.append(make_error("DOC_DATE_MISSING"))

        ctx.errors.extend(check_errors)
        return verdict, checks or {}

    # Public run method

    def run(
        self,
        fio: Optional[str],
        source_file_path: str,
        original_filename: str,
        content_type: Optional[str],
        external_metadata: Optional[dict] = None,
    ) -> dict:
        """Execute pipeline end-to-end and return result dict."""
        run_id = _generate_run_id()
        request_created_at = _now_iso()
        dirs = _mk_run_dirs(self.runs_root, run_id)

        ext_meta = external_metadata or {}

        ctx = PipelineContext(
            fio=fio,
            source_file_path=source_file_path,
            original_filename=original_filename,
            content_type=content_type,
            runs_root=self.runs_root,
            run_id=run_id,
            request_created_at=request_created_at,
            trace_id=ext_meta.get("trace_id"),
            dirs=dirs,
            external_request_id=ext_meta.get("external_request_id"),
            external_s3_path=ext_meta.get("external_s3_path"),
            external_iin=ext_meta.get("external_iin"),
            external_first_name=ext_meta.get("external_first_name"),
            external_last_name=ext_meta.get("external_last_name"),
            external_second_name=ext_meta.get("external_second_name"),
        )

        # Execute stages in order. Convert StageError -> final JSON & return.
        try:
            self._stage_acquire(ctx)
            self._stage_ocr(ctx)
            self._stage_doc_type_check(ctx)
            self._stage_extract(ctx)
            verdict, checks = self._stage_validate(ctx)
        except StageError as se:
            ctx.errors.append(make_error(se.code, details=se.details))
            self._finalize_timing_artifacts(ctx)
            final_json = self._build_error_final_json(ctx, se.code)
            final_path = self._write_final_json(ctx, final_json)
            return {
                "run_id": ctx.run_id,
                "verdict": False,
                "errors": ctx.errors,
                "final_result_path": final_path,
            }
        except Exception as exc:
            # Unexpected error
            self.logger.error(f"Unexpected pipeline error: {exc}", exc_info=True)
            ctx.errors.append(make_error("UNKNOWN_ERROR", details=str(exc)))
            self._finalize_timing_artifacts(ctx)
            final_json = self._build_error_final_json(ctx, "UNKNOWN_ERROR")
            final_path = self._write_final_json(ctx, final_json)
            return {
                "run_id": ctx.run_id,
                "verdict": False,
                "errors": ctx.errors,
                "final_result_path": final_path,
            }

        # Success finalization
        self._finalize_timing_artifacts(ctx)
        final_json = self._build_success_final_json(ctx, verdict, checks)
        final_path = self._write_final_json(ctx, final_json)
        return {
            "run_id": ctx.run_id,
            "verdict": verdict,
            "errors": ctx.errors,
            "final_result_path": final_path,
        }
