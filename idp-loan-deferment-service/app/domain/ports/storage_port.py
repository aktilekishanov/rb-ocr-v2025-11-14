"""StoragePort protocol for pipeline persistence.

Phase 0: contract only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class StoragePort(Protocol):  # pragma: no cover - Phase 0 contract
    """Abstraction over storage used by the pipeline.

    Implementations live in the infrastructure layer.
    """

    def save_input(self, run_id: str, src_path: Path) -> Path: ...

    def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path: ...

    def read_json(self, run_id: str, rel_path: str) -> dict: ...

    def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None: ...
