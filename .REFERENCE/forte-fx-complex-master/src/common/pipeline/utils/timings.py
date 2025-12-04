import time
from contextlib import contextmanager
from typing import Dict


@contextmanager
def _timed(stats: Dict[str, float], key: str):
    t0 = time.time()
    try:
        yield
    finally:
        stats[key] = stats.get(key, 0.0) + (time.time() - t0)

def _count_pages(ocr_dict: Dict[str, Dict]) -> Dict[str, int]:
    """
    Returns counts from an OCR result dict of:
      - total_images: number of image entries
      - unique_pages: number of distinct 'page' values when present; falls back to total_images
    """
    total_images = len(ocr_dict or {})
    pages = [v.get("page") for v in (ocr_dict or {}).values() if isinstance(v, dict)]
    unique_pages = len(set([p for p in pages if p is not None])) if pages else 0
    return {
        "total_images": total_images,
        "unique_pages": (unique_pages or total_images)
    }
