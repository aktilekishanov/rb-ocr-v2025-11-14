from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Storage


class LocalStorage(Storage):
    def __init__(self, runs_root: Path) -> None:
        self._runs_root = Path(runs_root)

    def _base_dir_for(self, run_id: str) -> Path:
        date_str = datetime.now().strftime("%Y-%m-%d")
        base_dir = self._runs_root / date_str / run_id
        return base_dir

    def save_input_file(self, source_path: str, run_id: str) -> str:
        base_dir = self._base_dir_for(run_id)
        input_dir = base_dir / "input"
        meta_dir = base_dir / "meta"
        input_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)

        src = Path(source_path)
        # Preserve extension if any; store as 'document<ext>' for simplicity
        target_name = "document" + (src.suffix or "")
        dest = input_dir / target_name
        shutil.copy2(src, dest)
        return str(dest)

    def write_json(self, run_id: str, relative_path: str, obj: dict[str, Any]) -> str:
        base_dir = self._base_dir_for(run_id)
        dest = base_dir / relative_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return str(dest)
