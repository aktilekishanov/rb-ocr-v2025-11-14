from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Storage(ABC):
    @abstractmethod
    def save_input_file(self, source_path: str, run_id: str) -> str: ...

    @abstractmethod
    def write_json(self, run_id: str, relative_path: str, obj: dict[str, Any]) -> str: ...
