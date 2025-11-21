from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any


def ensure_parent(path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    name = re.sub(r"[^\w\-\.\s]", "_", (name or "").strip())
    name = re.sub(r"\s+", "_", name)
    return name or "file"


def write_json(path: str | Path, obj: dict[str, Any]) -> None:
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_json(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def copy_file(src: str | Path, dst: str | Path) -> Path:
    ensure_parent(dst)
    shutil.copyfile(str(src), str(dst))
    return Path(dst)
