# =============================================================================
# Artifact Filenames
# =============================================================================

INPUT_FILE = "00_input{ext}"  # Template, ext filled at runtime

OCR_RAW = "01_ocr.raw.json"
OCR_FILTERED = "01_ocr.filtered.json"

LLM_DTC_RAW = "02_llm_dtc.raw.json"
LLM_DTC_FILTERED = "02_llm_dtc.filtered.json"

LLM_EXT_RAW = "03_llm_ext.raw.json"
LLM_EXT_FILTERED = "03_llm_ext.filtered.json"

FINAL_JSON = "04_final.json"


# =============================================================================
# Pipeline Settings
# =============================================================================

MAX_PDF_PAGES = 3  # Maximum pages to process per document
UTC_OFFSET_HOURS = 5  # Kazakhstan timezone (UTC+5)
DEFAULT_TEMPERATURE = 0.00001  # LLM temperature for deterministic output


# =============================================================================
# External Service Timeouts (seconds)
# =============================================================================

LLM_REQUEST_TIMEOUT_SECONDS = 30  # Timeout for LLM API requests
OCR_POLL_INTERVAL_SECONDS = 2.0  # Polling interval for OCR status checks
OCR_TIMEOUT_SECONDS = 300  # Total timeout for OCR processing (5 min)
OCR_CLIENT_TIMEOUT_SECONDS = 60  # HTTP client timeout for OCR requests


# =============================================================================
# Retry Configuration
# =============================================================================

BACKOFF_MULTIPLIER = 2  # Exponential backoff multiplier for retries


# =============================================================================
# Validation Limits
# =============================================================================

# File upload
MAX_FILE_SIZE_MB = 50  # Maximum file size for uploads

# FIO (Full Name)
FIO_MIN_LENGTH = 3  # Minimum characters
FIO_MAX_LENGTH = 200  # Maximum characters
FIO_MIN_WORDS = 2  # Minimum words required (first + last name)

# IIN (Individual Identification Number)
IIN_LENGTH = 12  # Exactly 12 digits required

# Name fields
NAME_MAX_LENGTH = 100  # Maximum length for first/last/second name

# S3 paths
S3_PATH_MAX_LENGTH = 1024  # Maximum length for S3 object paths

# =============================================================================
# Error Handling
# =============================================================================

ERROR_BODY_MAX_CHARS = 200  # Maximum chars from error response bodies

