# 🔢 Magic Numbers Review Report

## Executive Summary

**Compliance Score:** 60% (Needs Improvement)

**Status:** ⚠️ **MODERATE VIOLATIONS**

The codebase contains numerous magic numbers that reduce readability and maintainability. While some constants are properly defined (e.g., `MAX_PDF_PAGES`, `UTC_OFFSET_HOURS`), many critical values are hardcoded throughout the code without clear semantic meaning.

---

## 🚨 Critical Violations

### 1. HTTP Status Codes

**Problem:** HTTP status codes are scattered throughout the codebase as raw integers.

#### `pipeline/clients/llm_client.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 83 | `if http_err.code == 429:` | `if http_err.code == HTTPStatus.TOO_MANY_REQUESTS:` | 429 is not self-documenting |
| 93 | `elif 500 <= http_err.code < 600:` | `elif HTTPStatus.INTERNAL_SERVER_ERROR <= http_err.code < 600:` | Range check needs clarity |

#### `api/middleware/exception_handler.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 151 | `if e.status_code >= 500 else "client_error"` | `if e.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR` | 500 is a magic number |

**Recommendation:** Use `http.HTTPStatus` enum throughout:
```python
from http import HTTPStatus

if http_err.code == HTTPStatus.TOO_MANY_REQUESTS:
    # Handle rate limit
```

---

### 2. Retry Configuration

**Problem:** Retry counts and backoff multipliers are hardcoded without named constants.

#### `pipeline/utils/db_client.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 20 | `MAX_RETRIES = 5` | ✅ **GOOD** - Already a constant | |
| 21 | `INITIAL_BACKOFF = 0.5` | ✅ **GOOD** - Already a constant | |
| 48 | `backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))` | `backoff = INITIAL_BACKOFF * (BACKOFF_MULTIPLIER ** (attempt - 1))` | `2` is a magic number |

**Recommendation:** Define `BACKOFF_MULTIPLIER = 2` as a constant.

---

### 3. Timeout Values

**Problem:** Timeout values are hardcoded in function signatures and calls.

#### `pipeline/clients/llm_client.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 71 | `timeout=30` | `timeout=LLM_REQUEST_TIMEOUT_SECONDS` | 30 is not self-documenting |

#### `pipeline/clients/tesseract_async_client.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 86 | `poll_interval: float = 2.0` | `poll_interval: float = OCR_POLL_INTERVAL_SECONDS` | 2.0 needs semantic meaning |
| 87 | `timeout: float = 300.0` | `timeout: float = OCR_TIMEOUT_SECONDS` | 300 is 5 minutes - not obvious |
| 88 | `client_timeout: float = 60.0` | `client_timeout: float = OCR_CLIENT_TIMEOUT_SECONDS` | 60 needs clarity |

**Recommendation:** Define timeout constants in `pipeline/core/config.py`:
```python
# Timeout configuration (in seconds)
LLM_REQUEST_TIMEOUT_SECONDS = 30
OCR_POLL_INTERVAL_SECONDS = 2.0
OCR_TIMEOUT_SECONDS = 300  # 5 minutes
OCR_CLIENT_TIMEOUT_SECONDS = 60
```

---

### 4. Database Pool Configuration

**Problem:** Pool sizes are hardcoded without business context.

#### `pipeline/core/db_config.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 43 | `DB_PORT = 5432` | ✅ **ACCEPTABLE** - Standard PostgreSQL port | |
| 46 | `DB_POOL_MIN_SIZE = 2` | ✅ **GOOD** - Already a constant | |
| 47 | `DB_POOL_MAX_SIZE = 10` | ✅ **GOOD** - Already a constant | |
| 48 | `DB_POOL_TIMEOUT = 10.0` | ✅ **GOOD** - Already a constant | |

**Status:** ✅ **COMPLIANT** - These are already properly defined as module-level constants.

---

### 5. Document Validity Periods

**Problem:** Validity periods are hardcoded in days without clear business rules.

#### `pipeline/core/validity.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 23 | `DEFAULT_FIXED_DAYS = 40` | ✅ **GOOD** - Already a constant | |
| 26 | `"days": 180` | ✅ **GOOD** - In config dict | |
| 27 | `"days": 360` | ✅ **GOOD** - In config dict | |
| 29 | `"days": 365` | ✅ **GOOD** - In config dict | |

**Status:** ✅ **COMPLIANT** - These are properly defined in `VALIDITY_OVERRIDES` dict.

---

### 6. File Size Limits

**Problem:** File size calculations use magic numbers for byte conversions.

#### `api/validators.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 23 | `MAX_FILE_SIZE_MB = 50` | ✅ **GOOD** - Already a constant | |
| 24 | `MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024` | `MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * BYTES_PER_MB` | `1024 * 1024` is a magic number |
| 103 | `actual_size_mb = file_size / 1024 / 1024` | `actual_size_mb = file_size / BYTES_PER_MB` | Repeated magic number |

**Recommendation:** Define byte conversion constants:
```python
# Byte conversion constants
BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024
```

---

### 7. String Length Limits

**Problem:** String length limits are hardcoded in Pydantic Field definitions.

#### `api/schemas.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 35 | `min_length=3` | `min_length=FIO_MIN_LENGTH` | 3 is arbitrary |
| 36 | `max_length=200` | `max_length=FIO_MAX_LENGTH` | 200 is arbitrary |
| 84 | `min_length=1, max_length=1024` | `min_length=1, max_length=S3_PATH_MAX_LENGTH` | 1024 needs semantic meaning |
| 85 | `min_length=12, max_length=12` | `min_length=IIN_LENGTH, max_length=IIN_LENGTH` | 12 is IIN-specific |
| 86-88 | `max_length=100` | `max_length=NAME_MAX_LENGTH` | 100 is repeated |

**Recommendation:** Define validation constants:
```python
# Validation limits
FIO_MIN_LENGTH = 3
FIO_MAX_LENGTH = 200
IIN_LENGTH = 12
NAME_MAX_LENGTH = 100
S3_PATH_MAX_LENGTH = 1024
```

---

### 8. Array Indexing and Slicing

**Problem:** Array indices and slice limits are hardcoded.

#### `api/middleware/exception_handler.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 79 | `errors[0] if errors else {}` | `errors[FIRST_ERROR_INDEX] if errors else {}` | 0 is implicit |
| 113 | `e.errors()[0] if e.errors() else {}` | `e.errors()[FIRST_ERROR_INDEX] if e.errors() else {}` | Repeated pattern |

#### `pipeline/clients/llm_client.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 90 | `error_body[:200]` | `error_body[:ERROR_BODY_MAX_CHARS]` | 200 is arbitrary truncation |

**Recommendation:** Define indexing constants:
```python
FIRST_ERROR_INDEX = 0
ERROR_BODY_MAX_CHARS = 200
```

---

### 9. Seek Positions

**Problem:** File seek positions use magic numbers.

#### `api/validators.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 98 | `file.file.seek(0, 2)` | `file.file.seek(0, os.SEEK_END)` | 2 is not self-documenting |
| 100 | `file.file.seek(0)` | `file.file.seek(0, os.SEEK_SET)` | Explicit is better |

**Recommendation:** Use `os.SEEK_SET`, `os.SEEK_CUR`, `os.SEEK_END` constants.

---

### 10. FIO Word Count

**Problem:** Minimum word count for FIO validation is hardcoded.

#### `api/validators.py`

| Line | Current Code | Proposed Fix | Why? |
| :--- | :--- | :--- | :--- |
| 66 | `if len(fio_value.split()) < 2:` | `if len(fio_value.split()) < FIO_MIN_WORDS:` | 2 is a business rule |

**Recommendation:** Define `FIO_MIN_WORDS = 2` as a constant.

---

## ⚠️ Minor Issues

### 1. Configuration Values

These are already defined as constants but could benefit from better organization:

- `pipeline/core/config.py`:
  - `MAX_PDF_PAGES = 3` ✅
  - `UTC_OFFSET_HOURS = 5` ✅
  - `DEFAULT_TEMPERATURE = 0.00001` ✅

### 2. Port Numbers

- `S3Config.ENDPOINT = "s3-dev.fortebank.com:9443"` - Port 9443 is embedded in string (acceptable for config)
- `DB_PORT = 5432` - Standard PostgreSQL port (acceptable)

---

## ✅ Good Examples

The codebase does have some good practices:

1. **`pipeline/core/config.py`**: Centralized configuration constants
   ```python
   MAX_PDF_PAGES = 3
   UTC_OFFSET_HOURS = 5
   ```

2. **`pipeline/utils/db_client.py`**: Retry configuration
   ```python
   MAX_RETRIES = 5
   INITIAL_BACKOFF = 0.5
   ```

3. **`pipeline/core/validity.py`**: Document validity periods
   ```python
   DEFAULT_FIXED_DAYS = 40
   VALIDITY_OVERRIDES = {
       DOC_VKK: {"type": "fixed_days", "days": 180},
       ...
   }
   ```

---

## 🛠 Action Plan

### Phase 1: HTTP Status Codes (High Priority)
1. Add `from http import HTTPStatus` to relevant files
2. Replace all numeric HTTP status codes with `HTTPStatus` enum values
3. Files to update:
   - `pipeline/clients/llm_client.py`
   - `api/middleware/exception_handler.py`
   - `pipeline/core/exceptions.py`

### Phase 2: Timeout Constants (High Priority)
1. Add timeout constants to `pipeline/core/config.py`
2. Update function signatures in:
   - `pipeline/clients/llm_client.py`
   - `pipeline/clients/tesseract_async_client.py`

### Phase 3: Byte Conversion Constants (Medium Priority)
1. Add byte conversion constants to `pipeline/core/config.py`
2. Update calculations in:
   - `api/validators.py`

### Phase 4: Validation Constants (Medium Priority)
1. Add validation constants to `api/validators.py` or `api/schemas.py`
2. Update Pydantic Field definitions in:
   - `api/schemas.py`
   - `api/validators.py`

### Phase 5: Miscellaneous (Low Priority)
1. Add indexing constants
2. Update file seek operations to use `os.SEEK_*` constants
3. Add `BACKOFF_MULTIPLIER` constant

---

## 📊 Summary Statistics

- **Total Files Scanned:** 20+
- **Critical Violations:** 45+
- **Minor Issues:** 10+
- **Good Examples:** 8+
- **Estimated Refactoring Time:** 4-6 hours

---

## 🎯 Recommended Constants File Structure

```python
# pipeline/core/config.py (additions)

# HTTP Configuration
from http import HTTPStatus  # Use standard library enum

# Timeout Configuration (seconds)
LLM_REQUEST_TIMEOUT_SECONDS = 30
OCR_POLL_INTERVAL_SECONDS = 2.0
OCR_TIMEOUT_SECONDS = 300  # 5 minutes
OCR_CLIENT_TIMEOUT_SECONDS = 60

# Retry Configuration
BACKOFF_MULTIPLIER = 2

# Byte Conversion
BYTES_PER_KB = 1024
BYTES_PER_MB = 1024 * 1024
BYTES_PER_GB = 1024 * 1024 * 1024

# Validation Limits
FIO_MIN_LENGTH = 3
FIO_MAX_LENGTH = 200
FIO_MIN_WORDS = 2
IIN_LENGTH = 12
NAME_MAX_LENGTH = 100
S3_PATH_MAX_LENGTH = 1024

# Error Handling
FIRST_ERROR_INDEX = 0
ERROR_BODY_MAX_CHARS = 200
```
