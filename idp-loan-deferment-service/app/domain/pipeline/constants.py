"""Domain pipeline constants.

Phase 1: canonical artifact filenames and default limits; not wired into runtime yet.
"""

# Canonical artifact relative paths inside a run directory
OCR_PAGES_JSON = "ocr/pages.json"
FINAL_RESULT_JSON = "meta/final_result.json"
JOB_STATUS_JSON = "meta/job.json"

# Default limits and flags (keep aligned with app/core/config.py defaults)
DEFAULT_MAX_PDF_PAGES: int = 200
