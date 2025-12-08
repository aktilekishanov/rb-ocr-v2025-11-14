# Dead Code Removal: SINGLE_DOC_TYPE_INVALID

## Summary

Removed unreachable error code `SINGLE_DOC_TYPE_INVALID` which was impossible to trigger due to early pipeline exit logic.

---

## What Was Removed

### 1. Error Definition
**File**: `pipeline/core/errors.py`
```python
# REMOVED:
"SINGLE_DOC_TYPE_INVALID": "Файл содержит несколько типов документов",
```

### 2. Dead Validation Check
**File**: `pipeline/orchestrator.py` (lines 401-402)
```python
# REMOVED:
if checks.get("single_doc_type_valid") is False:
    check_errors.append(make_error("SINGLE_DOC_TYPE_INVALID"))

# ADDED COMMENT:
# Note: single_doc_type_valid check removed - if single_doc_type is False,
# pipeline stops early with MULTIPLE_DOCUMENTS error (line 300)
```

### 3. Integration Guide
**File**: `kafka-consumer-integration-guide.md`
```markdown
# REMOVED from error codes list:
- `SINGLE_DOC_TYPE_INVALID` - File contains multiple document types
```

---

## Why Was This Dead Code?

### The Logic Flow

```python
# Line 296-300: Early check during doc type stage
is_single = getattr(dtc, "single_doc_type", None)
if not isinstance(is_single, bool):
    return fail_and_finalize("DTC_PARSE_ERROR", None, ctx)  # Exit
if is_single is False:
    return fail_and_finalize("MULTIPLE_DOCUMENTS", None, ctx)  # Exit
# If we reach here, is_single MUST be True
```

**Result**: By the time validation runs (line 401), `single_doc_type_valid` can ONLY be:
- `True` (if doc type check returned True)
- `None` (if validation couldn't run for some reason)
- **NEVER `False`** (because pipeline already exited with `MULTIPLE_DOCUMENTS`)

---

## What Remains

### Active Error Code: `MULTIPLE_DOCUMENTS`

**Still triggered at**: `orchestrator.py:300`

**Purpose**: Fail-fast when document contains multiple types

**Response**:
```json
{
  "verdict": false,
  "errors": [{"code": "MULTIPLE_DOCUMENTS"}]
}
```

---

## Impact Analysis

### ✅ No Breaking Changes

1. **API Responses**: No change - `SINGLE_DOC_TYPE_INVALID` was never returned
2. **Database**: No change - field was never populated with this value
3. **Client Code**: No impact - error code was never seen by clients
4. **Tests**: No tests broke (no test directory)

### ✅ Benefits

1. **Cleaner codebase** - removed unreachable code
2. **Less confusion** - removed duplicate error for same condition
3. **Better documentation** - added comment explaining why check was removed

---

## Verification

```bash
# Syntax check passed ✅
python -m py_compile pipeline/core/errors.py pipeline/orchestrator.py
```

All files compile successfully.

---

## Files Modified

1. [`pipeline/core/errors.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/errors.py) - 1 line removed
2. [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py) - 2 lines removed, 2 lines added (comment)
3. [`kafka-consumer-integration-guide.md`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/kafka-consumer-integration-guide.md) - 1 line removed

---

## Remaining Error Codes for Multiple Documents

Only one error code now exists for this validation:

| Error Code | Stage | Behavior | When Triggered |
|------------|-------|----------|----------------|
| `MULTIPLE_DOCUMENTS` | Doc Type Check (early) | Pipeline STOPS | LLM returns `single_doc_type: false` |

Clean and simple! ✅
