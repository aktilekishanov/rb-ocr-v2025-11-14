"""Pipeline configuration constants."""

import os


def _env_bool(name: str, default: bool = False) -> bool:
    value_str = str(os.getenv(name, str(default))).strip().lower()
    return value_str in ("1", "true", "t", "yes", "y", "on")


# LLM inference settings
DEFAULT_TEMPERATURE = 0.00001

# Artifact filenames - sequential numbered for clarity
INPUT_FILE = "00_input{ext}"  # Template, ext filled at runtime

OCR_RAW = "01_ocr.raw.json"
OCR_FILTERED = "01_ocr.filtered.json"

LLM_DTC_RAW = "02_llm_dtc.raw.json"
LLM_DTC_FILTERED = "02_llm_dtc.filtered.json"

LLM_EXT_RAW = "03_llm_ext.raw.json"
LLM_EXT_FILTERED = "03_llm_ext.filtered.json"

FINAL_JSON = "04_final.json"

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
