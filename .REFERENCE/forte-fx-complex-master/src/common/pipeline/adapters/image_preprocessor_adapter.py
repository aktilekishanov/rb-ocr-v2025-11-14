from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import as_completed
from typing import Mapping, Dict, Optional
from src.common.logger.logger_config import get_logger

logger = get_logger("Image Preprocessor")

class ImagePreprocessAdapter:
    def __init__(self, preprocessor, suffix: str = ".png"):
        self.preprocessor = preprocessor
        self.suffix = suffix.lower()

    from typing import Mapping, Dict

    def preprocess_image_dict(
        self,
        files: Mapping[str, bytes],
        max_workers: int = 12
    ) -> Dict[str, bytes]:
        """
        Multithreaded version.
        Processes images concurrently, preserves order by key.
        Falls back to original bytes if preprocessing fails.
        """
        if not files:
            return {}

        out: Dict[str, bytes] = {}
        total = len(files)

        def _process(name: str, content: bytes) -> bytes:
            if not name.lower().endswith(self.suffix):
                return content
            try:
                return self.preprocessor.preprocess_image_bytes(content)
            except Exception:
                logger.exception("Failed to preprocess %s", name)
                return content  # fallback to original

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_name = {
                executor.submit(_process, name, content): (i, name)
                for i, (name, content) in enumerate(files.items(), start=1)
            }

            for fut in as_completed(future_to_name):
                i, name = future_to_name[fut]
                try:
                    out[name] = fut.result()
                    logger.info(f"Preprocessed page {i}/{total} ({name})")
                except Exception:
                    logger.exception("Unhandled failure in preprocessing %s", name)
                    out[name] = files[name]

        return out
