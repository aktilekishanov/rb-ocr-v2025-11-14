"""Application-level pipeline runner.

Phase 4: add a bridge function that calls the domain pipeline via the process_document use-case,
while preserving a re-export of the legacy runner for rollback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from app.services.pipeline_runner import run_sync_pipeline as legacy_run_sync_pipeline  # re-export for rollback
from app.application.usecases.process_document import process_document

__all__ = ["legacy_run_sync_pipeline", "run_sync_pipeline_app"]


async def run_sync_pipeline_app(*, run_id: str | None, input_path: Path, meta: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """Run the new domain pipeline and return a dict compatible with current API schemas.

    This function is the bridge used by routes and job workers in Phase 4.
    """
    result = await process_document(run_id=run_id, input_path=input_path, extra_meta=meta or {})
    return {
        "run_id": result.run_id,
        "verdict": result.verdict,
        "errors": list(result.errors),
    }
