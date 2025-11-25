from __future__ import annotations

from typing import Tuple

from app.domain.pipeline.models import RunContext, ValidationResult, RunResult
from app.domain.pipeline.errors import StageError


def run_validate(context: RunContext) -> Tuple[RunContext, RunResult]:
    """Validate merged artifacts and build RunResult.

    Phase 3: minimal rules to shape the pipeline output.
    """
    merged = context.artifacts.get("merged")
    if not isinstance(merged, dict):
        raise StageError("Merged artifacts missing for validate stage")

    errors: list[str] = []
    warnings: list[str] = []

    fields = merged.get("fields") or {}

    # Minimal rule example: require fio field
    if "fio" not in fields:
        errors.append("Missing required field: fio")

    is_valid = len(errors) == 0

    val = ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
    run_result = RunResult(
        run_id=context.run_id,
        verdict=is_valid,
        errors=list(errors),
        checks={"has_fio": "fio" in fields},
        meta={"doc_type": merged.get("doc_type")},
    )

    context.artifacts["validation_result"] = val
    context.artifacts["run_result"] = run_result
    return context, run_result
