"""
Central configuration constants for filenames and global settings.

Holds canonical JSON filenames for OCR, LLM, merge, and validation
artifacts, as well as global limits and feature flags derived from the
environment.
"""

import os


def _env_bool(name: str, default: bool = False) -> bool:
    v = str(os.getenv(name, str(default))).strip().lower()
    return v in ("1", "true", "t", "yes", "y", "on")


# Centralized filenames and constants used across the pipeline

# OCR outputs
OCR_RAW = "ocr_response_raw.json"
OCR_PAGES = "ocr_response_filtered.json"

# LLM: doc type checker (function-oriented filenames)
LLM_DOC_TYPE_RAW = "doc_type_check.raw.json"
LLM_DOC_TYPE_FILTERED = "doc_type_check.filtered.json"

# LLM: extractor (function-oriented filenames)
LLM_EXTRACTOR_RAW = "extractor.raw.json"
LLM_EXTRACTOR_FILTERED = "extractor.filtered.json"

# Merge and validation
MERGED_FILENAME = "merged.json"
VALIDATION_FILENAME = "validation.json"

# User-provided metadata
METADATA_FILENAME = "metadata.json"

# Global settings
MAX_PDF_PAGES = 3
UTC_OFFSET_HOURS = 5


# S3/MinIO Configuration
class S3Config:
    """S3/MinIO hardcoded configuration for DEV."""
    
    ENDPOINT: str = "s3-dev.fortebank.com:9443"
    ACCESS_KEY: str = "fyz13d2czRW7l4sBW8gD"
    SECRET_KEY: str = "1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A"
    BUCKET: str = "loan-statements-dev"
    SECURE: bool = True


# Export singleton config
s3_config = S3Config()
