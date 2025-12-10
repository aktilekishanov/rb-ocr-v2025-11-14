"""Build final.json structure matching PostgreSQL schema.

Optimized with Builder pattern to eliminate code duplication and improve maintainability.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class ExternalMetadata:
    """External metadata from Kafka request."""

    request_id: str | None = None
    s3_path: str | None = None
    iin: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    second_name: str | None = None


@dataclass
class ExtractedData:
    """Data extracted from document by pipeline."""

    fio: str | None = None
    doc_date: str | None = None
    single_doc_type: bool | None = None
    doc_type_known: bool | None = None
    doc_type: str | None = None


@dataclass
class RuleChecks:
    """Business rule validation results."""

    fio_match: bool | None = None
    doc_date_valid: bool | None = None
    doc_type_known: bool | None = None
    single_doc_type: bool | None = None


class FinalJsonBuilder:
    """Builder for final.json with fluent interface.

    Eliminates code duplication and provides clean, testable API.

    Example:
        final_json = (
            FinalJsonBuilder(run_id, trace_id, created_at)
            .with_external_metadata(external_meta)
            .with_error(code, message, category, retryable)
            .with_timing(completed_at, processing_time)
            .build()
        )
    """

    def __init__(self, run_id: str, trace_id: str | None, created_at: str):
        """Initialize builder with required fields."""
        self.data: dict[str, Any] = {
            "run_id": run_id,
            "trace_id": trace_id,
            "created_at": created_at,
        }

    def with_external_metadata(self, metadata: ExternalMetadata) -> "FinalJsonBuilder":
        """Add external Kafka metadata."""
        self.data.update(
            {
                "external_request_id": metadata.request_id,
                "external_s3_path": metadata.s3_path,
                "external_iin": metadata.iin,
                "external_first_name": metadata.first_name,
                "external_last_name": metadata.last_name,
                "external_second_name": metadata.second_name,
            }
        )
        return self

    def with_error(
        self, code: str, message: str, category: str, retryable: bool
    ) -> "FinalJsonBuilder":
        """Mark as error and set HTTP error fields, NULL all extracted/rule fields."""
        self.data.update(
            {
                "status": "error",
                "http_error_code": code,
                "http_error_message": message,
                "http_error_category": category,
                "http_error_retryable": retryable,
                # NULL all extracted/rule fields
                "extracted_fio": None,
                "extracted_doc_date": None,
                "extracted_single_doc_type": None,
                "extracted_doc_type_known": None,
                "extracted_doc_type": None,
                "rule_fio_match": None,
                "rule_doc_date_valid": None,
                "rule_doc_type_known": None,
                "rule_single_doc_type": None,
                "rule_verdict": None,
                "rule_errors": [],
            }
        )
        return self

    def with_success(
        self,
        extracted: ExtractedData,
        checks: RuleChecks,
        verdict: bool,
        rule_errors: list[str],
    ) -> "FinalJsonBuilder":
        """Mark as success and set extracted/rule fields, NULL all HTTP error fields."""
        self.data.update(
            {
                "status": "success",
                "http_error_code": None,
                "http_error_message": None,
                "http_error_category": None,
                "http_error_retryable": None,
                "extracted_fio": extracted.fio,
                "extracted_doc_date": extracted.doc_date,
                "extracted_single_doc_type": extracted.single_doc_type,
                "extracted_doc_type_known": extracted.doc_type_known,
                "extracted_doc_type": extracted.doc_type,
                "rule_fio_match": checks.fio_match,
                "rule_doc_date_valid": checks.doc_date_valid,
                "rule_doc_type_known": checks.doc_type_known,
                "rule_single_doc_type": checks.single_doc_type,
                "rule_verdict": verdict,
                "rule_errors": rule_errors,
            }
        )
        return self

    def with_timing(
        self, completed_at: str, processing_time_seconds: float
    ) -> "FinalJsonBuilder":
        """Add timing information."""
        self.data.update(
            {
                "completed_at": completed_at,
                "processing_time_seconds": processing_time_seconds,
            }
        )
        return self

    def build(self) -> dict[str, Any]:
        """Return final JSON dict."""
        return self.data
