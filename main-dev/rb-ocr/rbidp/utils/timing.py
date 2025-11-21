from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Dict


class StageTimers:
    def __init__(self) -> None:
        self.totals: Dict[str, float] = {}

    @contextmanager
    def timer(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dt = time.perf_counter() - t0
            self.totals[name] = self.totals.get(name, 0.0) + dt


def stage_timer(ctx, name: str):
    return ctx.timers.timer(name)
