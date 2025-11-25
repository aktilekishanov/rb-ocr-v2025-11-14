from __future__ import annotations

from app.domain.pipeline.models import RunContext
from app.domain.pipeline.errors import InvalidInputError


def run_acquire(context: RunContext) -> RunContext:
    """Validate base fields on the context.

    Phase 3 keeps this minimal: ensure run_id exists.
    """
    if not context.run_id:
        raise InvalidInputError("run_id is required in RunContext")
    return context
