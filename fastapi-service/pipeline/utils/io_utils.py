"""
Basic file-system utilities shared across the RB-OCR pipeline.

Provides helpers for creating parent directories, generating safe
filenames, and reading/writing JSON payloads in UTF-8.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any


def ensure_parent(path: str | Path) -> None:
    """
    Ensure that the parent directory for the given path exists.

    Creates all missing parents with `exist_ok=True` and does not
    touch the file itself.

    Args:
      path: Target file path whose parent should be created.
    """
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)


def write_json(path: str | Path, obj: dict[str, Any]) -> None:
    """
    Write a JSON object to disk using UTF-8 encoding.

    Ensures the parent directory exists and writes the given mapping
    with `ensure_ascii=False` and indentation.

    Args:
      path: Destination file path.
      obj: JSON-serializable mapping to persist.
    """
    ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def read_json(path: str | Path) -> Any:
    """
    Read and parse a JSON file using UTF-8 encoding.

    Args:
      path: Source file path.

    Returns:
      The decoded JSON value (usually a dict or list).
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def copy_file(src: str | Path, dst: str | Path) -> Path:
    """
    Copy a single file from `src` to `dst`.

    Ensures the parent of `dst` exists before invoking `shutil` and
    returns the destination as a `Path` object.

    Args:
      src: Existing file path to copy from.
      dst: Destination file path to copy to.

    Returns:
      The destination path as a `Path` instance.
    """
    ensure_parent(dst)
    shutil.copyfile(str(src), str(dst))
    return Path(dst)


def build_fio(last_name: str, first_name: str, second_name: str | None = None) -> str:
    """
    Build Full Name (FIO) from components.

    Args:
        last_name: Last name (фамилия)
        first_name: First name (имя)
        second_name: Patronymic/middle name (отчество), optional

    Returns:
        Full name string, e.g., "Иванов Иван Иванович" or "Иванов Иван"

    Example:
        >>> build_fio("Иванов", "Иван", "Иванович")
        "Иванов Иван Иванович"
        >>> build_fio("Петров", "Петр", None)
        "Петров Петр"
    """
    components = [last_name.strip(), first_name.strip()]
    if second_name and second_name.strip():
        components.append(second_name.strip())
    return " ".join(components)
