# Error Code Analysis: MULTIPLE_DOCUMENTS vs SINGLE_DOC_TYPE_INVALID

## TL;DR: They're Used at Different Pipeline Stages

**Verdict**: These are **NOT duplicates** - they represent the same validation failure detected at different points in the pipeline.

---

## The Two Error Codes

```python
# From pipeline/core/errors.py
ERROR_MESSAGES_RU = {
    "MULTIPLE_DOCUMENTS": "Файл содержит несколько типов документов",
    "SINGLE_DOC_TYPE_INVALID": "Файл содержит несколько типов документов",
}
```

Same Russian message, but different contexts!

---

## When Each is Used

### `MULTIPLE_DOCUMENTS` - Early Failure (LLM Doc Type Check)

**Location**: [`orchestrator.py:300`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L300)

**Context**: During the **document type check stage** (before extraction)

```python
# Line 296-300
is_single = getattr(dtc, "single_doc_type", None)
if not isinstance(is_single, bool):
    return fail_and_finalize("DTC_PARSE_ERROR", None, ctx)
if is_single is False:
    return fail_and_finalize("MULTIPLE_DOCUMENTS", None, ctx)  # ← FAIL FAST
```

**What happens:**
- ❌ Pipeline **STOPS immediately**
- ❌ No extraction runs
- ❌ No validation runs
- ❌ No final result
- Response: HTTP 200, verdict=false, NO run_id stored in DB

**Why it exists:** Fast-fail optimization - don't waste resources on extraction if document is already invalid.

---

### `SINGLE_DOC_TYPE_INVALID` - Late Failure (Final Validation)

**Location**: [`orchestrator.py:402`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L402)

**Context**: During **final validation stage** (after extraction completed)

```python
# Line 401-402
if checks.get("single_doc_type_valid") is False:
    check_errors.append(make_error("SINGLE_DOC_TYPE_INVALID"))  # ← VALIDATION FAILURE
```

**What happens:**
- ✅ Pipeline **continues to completion**
- ✅ Extraction ran successfully
- ✅ All validations checked
- ✅ Full result with all check fields
- Response: HTTP 200, verdict=false, run_id stored in DB

**Why it exists:** Comprehensive validation - collect ALL failures, not just the first one.

---

## The Key Difference

| Aspect | `MULTIPLE_DOCUMENTS` | `SINGLE_DOC_TYPE_INVALID` |
|--------|---------------------|---------------------------|
| **Stage** | Doc type check (early) | Final validation (late) |
| **Pipeline behavior** | STOP immediately | Continue to end |
| **Extraction runs?** | ❌ No | ✅ Yes |
| **Other checks run?** | ❌ No | ✅ Yes |
| **Database record?** | ❌ No run_id | ✅ Full run_id with all fields |
| **Error location** | `ctx.errors` (system) | `check_errors` (business) |

---

## Why Two Different Codes?

### Architectural Reasons:

1. **Different Error Categories**
   - `MULTIPLE_DOCUMENTS` = **System/Pipeline Error** (LLM stage failed)
   - `SINGLE_DOC_TYPE_INVALID` = **Business Validation Error** (final check failed)

2. **Different Debugging Needs**
   - `MULTIPLE_DOCUMENTS` → "LLM detected multiple docs, stopped pipeline"
   - `SINGLE_DOC_TYPE_INVALID` → "Validation check failed after extraction"

3. **Different Data Availability**
   - `MULTIPLE_DOCUMENTS` → Minimal context (no extraction data)
   - `SINGLE_DOC_TYPE_INVALID` → Full context (extraction + all checks)

---

## Real-World Example

### Scenario: PDF contains passport + driver's license

#### Path 1: Early Detection (MULTIPLE_DOCUMENTS)

```
1. OCR extracts text ✅
2. LLM doc type check: "single_doc_type": false
3. ❌ Pipeline STOPS with MULTIPLE_DOCUMENTS
   - No extraction attempted
   - No FIO check
   - No date check
   
Database: NO RECORD (pipeline failed early)

Response:
{
  "verdict": false,
  "errors": [{"code": "MULTIPLE_DOCUMENTS"}],
  "run_id": null  // No run_id!
}
```

#### Path 2: Late Detection (SINGLE_DOC_TYPE_INVALID)

**IF** the doc type check somehow passed but validation caught it:

```
1. OCR extracts text ✅
2. LLM doc type check PASSES (or returns indeterminate) ✅
3. LLM extraction runs ✅
4. Validation checks:
   - fio_match: check ✅
   - doc_type_known: check ✅
   - doc_date_valid: check ✅
   - single_doc_type_valid: FALSE ❌
5. ✅ Pipeline COMPLETES with SINGLE_DOC_TYPE_INVALID

Database: FULL RECORD (all fields populated)

Response:
{
  "run_id": "550e8400-...",
  "verdict": false,
  "errors": [{"code": "SINGLE_DOC_TYPE_INVALID"}],
  "extracted_fio": "Иванов И.И.",  // Available!
  "check_fio_match": true,
  "check_single_doc_type": false
}
```

---

## Should We Keep Both?

### Option 1: Keep Both (Current Design) ✅

**Pros:**
- ✅ Distinguishes pipeline stage
- ✅ Clearer debugging ("where did it fail?")
- ✅ Different data availability

**Cons:**
- ❌ Confusing to have two codes for same validation
- ❌ Requires documentation

---

### Option 2: Merge Into One Code ⚠️

**Change:**
```python
ERROR_MESSAGES_RU = {
    # Remove MULTIPLE_DOCUMENTS
    "SINGLE_DOC_TYPE_INVALID": "Файл содержит несколько типов документов",
}

# orchestrator.py line 300
if is_single is False:
    return fail_and_finalize("SINGLE_DOC_TYPE_INVALID", None, ctx)  # Same code

# orchestrator.py line 402
if checks.get("single_doc_type_valid") is False:
    check_errors.append(make_error("SINGLE_DOC_TYPE_INVALID"))  # Same code
```

**Pros:**
- ✅ Simpler - only one code to remember
- ✅ Consistent error message

**Cons:**
- ❌ Can't distinguish early vs late failure
- ❌ Loses debugging context

---

### Option 3: Better Naming (RECOMMENDED) ✅

**Make the PURPOSE clear in the code names:**

```python
ERROR_MESSAGES_RU = {
    # Early detection (LLM stage)
    "MULTIPLE_DOCUMENTS_DETECTED": "Файл содержит несколько типов документов",
    
    # Late detection (validation stage)
    "SINGLE_DOC_TYPE_INVALID": "Файл содержит несколько типов документов",
}
```

**OR:**

```python
ERROR_MESSAGES_RU = {
    # Early detection (fatal - stops pipeline)
    "MULTIPLE_DOCUMENTS": "Файл содержит несколько типов документов (обнаружено при проверке типа)",
    
    # Late detection (validation - pipeline complete)
    "SINGLE_DOC_TYPE_INVALID": "Файл содержит несколько типов документов (обнаружено при валидации)",
}
```

**Pros:**
- ✅ Clear distinction in code
- ✅ Maintains debugging context
- ✅ Different messages for user/logs

---

## Recommendation

### Short-term: Keep both, update integration guide ✅

Update [`kafka-consumer-integration-guide.md`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/../kafka-consumer-integration-guide.md) to clarify:

```markdown
- `MULTIPLE_DOCUMENTS` - Document has multiple types (detected at LLM check stage, pipeline stopped)
- `SINGLE_DOC_TYPE_INVALID` - Document has multiple types (detected at validation stage, full extraction available)
```

### Long-term: Better naming ✅

Rename to make purpose explicit:
- `MULTIPLE_DOCUMENTS` → `DOC_TYPE_CHECK_FAILED_MULTIPLE` (clear it's from doc type check)
- `SINGLE_DOC_TYPE_INVALID` → `VALIDATION_MULTIPLE_DOCUMENTS` (clear it's from validation)

---

## Code Location Summary

**Definition**: [`pipeline/core/errors.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/errors.py)

**Usage**:
1. `MULTIPLE_DOCUMENTS` - Line 300 of [`orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L300)
2. `SINGLE_DOC_TYPE_INVALID` - Line 402 of [`orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L402)

**Validator logic**: [`validator.py:200-209`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/validator.py#L200-L209)

---

## Bottom Line

**Not a bug, it's a (poorly named) feature!**

The codes serve different purposes:
- One stops the pipeline early (fast-fail)
- One reports validation failure after full processing

**Action**: Either keep both with updated docs, or rename them to make the distinction obvious.
