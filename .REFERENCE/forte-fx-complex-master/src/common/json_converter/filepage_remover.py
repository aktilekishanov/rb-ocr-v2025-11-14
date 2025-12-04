import os
import re
from typing import Dict, Any

class FilePageRemover:
    # Remove trailing `_page_<n>` from the stem
    PAGE_TAIL = re.compile(r"_page_\d+$", re.IGNORECASE)

    @staticmethod
    def _normalize(s: str) -> str:
        # Replace non-breaking spaces with normal spaces, then strip
        return s.replace("\u00A0", " ").strip()

    @classmethod
    def _clean_filename(cls, name: str) -> str:
        # 1) normalize weird spaces
        name = cls._normalize(name)

        # 2) drop extension (any extension, case-insensitive)
        stem, _ext = os.path.splitext(name)

        # 3) remove trailing `_page_n` if present
        stem = cls.PAGE_TAIL.sub("", stem)

        # 4) final trim just in case
        return stem.strip()

    def remove_page_suffixes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Overwrites 'filename' with a cleaned version that has:
          - no extension (e.g. .png/.PNG/.jpg/...)
          - no trailing '_page_<n>'
          - normalized spaces
        """
        for field in data.get("fields", []):
            for ref in field.get("references", []):
                filename = ref.get("filename")
                if isinstance(filename, str) and filename:
                    ref["filename"] = self._clean_filename(filename)
        return data
