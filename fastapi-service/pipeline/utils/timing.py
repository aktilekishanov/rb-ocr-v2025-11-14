"""
Lightweight helpers for measuring per-stage timings in the pipeline.

Stage timers accumulate elapsed wall-clock seconds per named stage so
that orchestrator code can emit simple duration fields into manifests.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Dict


class StageTimers:
    """
    Accumulate elapsed time per logical stage name.

    Use `timer(name)` as a context manager around stage blocks; 
    each exit adds the elapsed seconds to `totals[name]`.
    """

    def __init__(self) -> None:
        self.totals: Dict[str, float] = {}

    @contextmanager
    def timer(self, name: str):
        """
        Measure and accumulate elapsed time for the given stage name.

        Args:
          name: Logical stage identifier (e.g. "ocr" or "llm").

        Yields:
          A context manager that measures the enclosed block.
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            elapsed_time = time.perf_counter() - start_time
            self.totals[name] = self.totals.get(name, 0.0) + elapsed_time


def stage_timer(ctx, name: str):
    """
    Convenience wrapper to access `ctx.timers.timer(name)`.

    Args:
      ctx: Pipeline context object carrying a `timers` attribute.
      name: Logical stage identifier.

    Returns:
      The context manager returned by `StageTimers.timer`.
    """
    return ctx.timers.timer(name)
