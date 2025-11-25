"""Local disk storage adapter implementing StoragePort.

Phase 2: implemented adapter – not wired into runtime code yet.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from app.domain.ports.storage_port import StoragePort


class LocalDiskStorageAdapter(StoragePort):  # pragma: no cover - adapter impl (unused by runtime)
    """Local filesystem adapter conforming to StoragePort.

    Mirrors the behavior and layout of the existing LocalStorage service:
    runs/YYYY-MM-DD/<run_id>/{input,meta,...}
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _base_dir_for(self, run_id: str) -> Path:
        date_str = datetime.now().strftime("%Y-%m-%d")
        return Path(self._base_dir) / date_str / run_id

    def save_input(self, run_id: str, src_path: Path) -> Path:
        base_dir = self._base_dir_for(run_id)
        input_dir = base_dir / "input"
        meta_dir = base_dir / "meta"
        input_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        src = Path(src_path)
        target_name = "document" + (src.suffix or "")
        dest = input_dir / target_name
        shutil.copy2(src, dest)
        return dest

    def write_json(self, run_id: str, rel_path: str, obj: dict) -> Path:
        base_dir = self._base_dir_for(run_id)
        dest = base_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return dest

    def read_json(self, run_id: str, rel_path: str) -> dict:
        base_dir = self._base_dir_for(run_id)
        src = base_dir / rel_path
        with src.open("r", encoding="utf-8") as f:
            return json.load(f)

    def ensure_dirs(self, run_id: str, *rel_dirs: str) -> None:
        base_dir = self._base_dir_for(run_id)
        for d in rel_dirs:
            (base_dir / d).mkdir(parents=True, exist_ok=True)
