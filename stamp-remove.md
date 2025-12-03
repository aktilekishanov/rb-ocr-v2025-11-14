# Stamp Detection Removal Plan

**Project**: RB-OCR Document Verification System  
**Date**: 2025-12-03  
**Purpose**: Complete removal of stamp detection functionality from the pipeline

---

## 1. Overview

This document provides a comprehensive analysis of all stamp detection-related components in the RB-OCR system and a step-by-step plan for their removal.

### Current State

Stamp detection has been **REMOVED** from the codebase.

### Scope

- **FastAPI Service**: Pipeline orchestrator, processors, configuration, error handling, artifacts
- **UI**: Error message mapping
- **Database Schema**: Schema design includes stamp-related fields
- **External Dependencies**: Hardcoded paths to external stamp detection script

---

## 2. Complete Inventory of Stamp-Related Components

### 2.1 Configuration

| File | Line(s) | Component | Description |
|------|---------|-----------|-------------|
| [`pipeline/core/config.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/config.py#L41) | 41 | `STAMP_ENABLED` | Environment variable flag `RB_IDP_STAMP_ENABLED` (default: False) |

### 2.2 Error Codes

| File | Line(s) | Component | Description |
|------|---------|-----------|-------------|
| [`pipeline/core/errors.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/errors.py#L37-L39) | 37-39 | Error messages | `STAMP_NOT_PRESENT`, `STAMP_CHECK_MISSING` |

### 2.3 Stamp Detection Processor (Entire Module)

| File | Lines | Description |
|------|-------|-------------|
| [`pipeline/processors/stamp_check.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/stamp_check.py) | 1-173 | **Complete module** - Wraps external stamp detector script |

**Key Functions**:
- `stamp_present_for_source()` - Main entry point
- `_run_detector()` - Calls external Python script
- `_render_pdf_to_vertical_jpg()` - PDF preprocessing
- `_is_image_path()` - Helper

**External Dependencies** (Hardcoded):
```python
DETECTOR_PY = "/home/rb_admin2/apps/main-dev/stamp-processing/.venv/bin/python"
DETECTOR_SCRIPT = "/home/rb_admin2/apps/main-dev/stamp-processing/main.py"
DETECTOR_WEIGHT = "/home/rb_admin2/apps/main-dev/stamp-processing/weights/stamp_detector.pt"
```

### 2.4 Pipeline Orchestrator

| File | Line(s) | Component | Description |
|------|---------|-----------|-------------|
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L31) | 31 | Import | `STAMP_ENABLED` config |
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L41) | 41 | Import | `stamp_present_for_source` function |
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L163) | 163 | Timing | `stamp_seconds` artifact |
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L306) | 306 | Function | `stage_extract_and_stamp()` - Stage name includes stamp |
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L339-L353) | 339-353 | Logic | Stamp detection execution block |
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L369) | 369 | Parameter | `stamp_check_response_path` passed to merge |
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L420-L425) | 420-425 | Validation | Stamp presence validation checks |
| [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py#L474) | 474 | Stage list | `stage_extract_and_stamp` in pipeline stages |

### 2.5 Merge Outputs Processor

| File | Line(s) | Component | Description |
|------|---------|-----------|-------------|
| [`pipeline/processors/merge_outputs.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/merge_outputs.py#L13) | 13 | Parameter | `stamp_check_response_path` parameter |
| [`pipeline/processors/merge_outputs.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/merge_outputs.py#L20) | 20 | Docstring | Mentions stamp_present merging |
| [`pipeline/processors/merge_outputs.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/merge_outputs.py#L57-L65) | 57-65 | Logic | Merges stamp_check_response.json into merged.json |

### 2.6 Artifacts Utilities

| File | Line(s) | Component | Description |
|------|---------|-----------|-------------|
| [`pipeline/utils/artifacts.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/utils/artifacts.py#L64-L65) | 64-65 | `build_final_result()` | Reads stamp_present from metadata.json |
| [`pipeline/utils/artifacts.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/utils/artifacts.py#L125) | 125 | `write_manifest()` | Includes `stamp_seconds` in timing |
| [`pipeline/utils/artifacts.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/utils/artifacts.py#L187-L193) | 187-193 | `build_side_by_side()` | Reads stamp_check_response.json and adds to side-by-side view |

### 2.7 UI (Streamlit)

| File | Line(s) | Component | Description |
|------|---------|-----------|-------------|
| [`ui/app.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/ui/app.py#L142) | 142 | Error mapping | `"STAMP_NOT_FOUND": "Печать не найдена"` |

### 2.8 Database Schema

| File | References | Description |
|------|-----------|-------------|
| [`DB_SCHEMA.md`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/DB_SCHEMA.md) | Multiple | Schema includes stamp-related fields |

**Tables with stamp fields**:
- `verification_runs.stamp_seconds` (line 64, 429)
- `extracted_data.stamp_present` (line 97, 442)
- `validation_checks.stamp_present` (line 129, 457)

---

## 3. Generated Artifacts

The following files are **generated at runtime** when stamp detection is enabled:

| File | Location | Description |
|------|----------|-------------|
| `stamp_check_response.json` | `runs/{date}/{run_id}/meta/` | Contains `{"stamp_present": true/false}` |
| `{filename}_with_boxes.{ext}` | `runs/{date}/{run_id}/input/original/` | Visualization image with bounding boxes |

---

## 4. Step-by-Step Removal Plan

### Phase 1: Code Removal (FastAPI Service)

#### Step 1.1: Remove Stamp Processor Module
**File**: [`pipeline/processors/stamp_check.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/stamp_check.py)

**Status**: [x] COMPLETED

---

#### Step 1.2: Update Pipeline Orchestrator
**File**: [`pipeline/orchestrator.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/orchestrator.py)

**Status**: [x] COMPLETED

---

#### Step 1.3: Update Merge Outputs Processor
**File**: [`pipeline/processors/merge_outputs.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/processors/merge_outputs.py)

**Status**: [x] COMPLETED

---

#### Step 1.4: Update Artifacts Utilities
**File**: [`pipeline/utils/artifacts.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/utils/artifacts.py)

**Status**: [x] COMPLETED

---

#### Step 1.5: Update Error Codes
**File**: [`pipeline/core/errors.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/errors.py)

**Status**: [x] COMPLETED

---

#### Step 1.6: Update Configuration
**File**: [`pipeline/core/config.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/fastapi-service/pipeline/core/config.py)

**Status**: [x] COMPLETED

---

### Phase 2: UI Updates

#### Step 2.1: Update Streamlit UI
**File**: [`ui/app.py`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/ui/app.py)

**Status**: [x] COMPLETED

---

### Phase 3: Database Schema Updates

#### Step 3.1: Update Database Schema Documentation
**File**: [`DB_SCHEMA.md`](file:///Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/DB_SCHEMA.md)

**Status**: [x] COMPLETED

---

#### Step 3.2: Database Migration (If DB Already Created)

**If the database has already been created**, you'll need a migration:

```sql
-- Migration: Remove stamp-related columns
-- File: migrations/002_remove_stamp_columns.sql

BEGIN;

-- Remove from verification_runs
ALTER TABLE verification_runs DROP COLUMN IF EXISTS stamp_seconds;

-- Remove from extracted_data
ALTER TABLE extracted_data DROP COLUMN IF EXISTS stamp_present;

-- Remove from validation_checks
ALTER TABLE validation_checks DROP COLUMN IF EXISTS stamp_present;

COMMIT;
```

---

### Phase 4: Cleanup

#### Step 4.1: Remove Environment Variable

**Action**: Remove from deployment configuration

- Docker Compose files
- Systemd service files
- `.env` files
- Deployment scripts

**Search for**: `RB_IDP_STAMP_ENABLED`

---

#### Step 4.2: Clean Up Generated Artifacts (Optional)

**Action**: Remove stamp-related files from existing runs

```bash
# Find and remove stamp_check_response.json files
find /path/to/runs -name "stamp_check_response.json" -delete

# Find and remove visualization images
find /path/to/runs -name "*_with_boxes.*" -delete
```

---

#### Step 4.3: Remove External Stamp Processing Directory (Optional)

**Location**: `/home/rb_admin2/apps/main-dev/stamp-processing/`

**Action**: Archive or delete if no longer needed

```bash
# Archive before deletion
tar -czf stamp-processing-backup-$(date +%Y%m%d).tar.gz /home/rb_admin2/apps/main-dev/stamp-processing/

# Then remove
rm -rf /home/rb_admin2/apps/main-dev/stamp-processing/
```

---

## 5. Testing Plan

After removal, verify:

### 5.1 Unit Tests
- [ ] Pipeline runs without errors
- [ ] No import errors for removed modules
- [ ] Merged JSON does not contain `stamp_present`
- [ ] Manifest does not contain `stamp_seconds`
- [ ] Side-by-side JSON does not contain stamp data

### 5.2 Integration Tests
- [ ] Full pipeline execution (PDF and image inputs)
- [ ] API `/v1/verify` endpoint returns correct response
- [ ] UI displays results without stamp errors
- [ ] Database inserts work correctly (if DB implemented)

### 5.3 Regression Tests
- [ ] All existing validation checks still work
- [ ] Error handling unchanged for other errors
- [ ] Timing metrics still recorded correctly

---

## 6. Rollback Plan

If issues arise:

1. **Revert code changes**: Use git to restore removed code
   ```bash
   git checkout HEAD~1 -- pipeline/processors/stamp_check.py
   git checkout HEAD~1 -- pipeline/orchestrator.py
   # ... etc
   ```

2. **Restore database columns** (if dropped):
   ```sql
   ALTER TABLE verification_runs ADD COLUMN stamp_seconds NUMERIC(10, 3);
   ALTER TABLE extracted_data ADD COLUMN stamp_present BOOLEAN;
   ALTER TABLE validation_checks ADD COLUMN stamp_present BOOLEAN;
   ```

3. **Re-enable environment variable**: Set `RB_IDP_STAMP_ENABLED=false` (keep disabled but code present)

---

## 7. Summary

### Files Modified: 7
1. ✅ `pipeline/processors/stamp_check.py` - **DELETED**
2. ✅ `pipeline/orchestrator.py` - **MODIFIED**
3. ✅ `pipeline/processors/merge_outputs.py` - **MODIFIED**
4. ✅ `pipeline/utils/artifacts.py` - **MODIFIED**
5. ✅ `pipeline/core/errors.py` - **MODIFIED**
6. ✅ `pipeline/core/config.py` - **MODIFIED**
7. ✅ `ui/app.py` - **MODIFIED**

### Files Updated (Documentation): 1
1. ✅ `DB_SCHEMA.md` - **MODIFIED**

### Database Migrations: 1
1. ✅ Create migration to drop stamp columns (if DB exists)

### Total Changes
- **Lines deleted**: ~200+
- **Lines modified**: ~30
- **Modules removed**: 1 complete file
- **Database columns dropped**: 3

---

## 8. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Breaking existing runs | Low | Medium | Test thoroughly before deployment |
| Database migration fails | Low | High | Test migration on staging DB first |
| Missing references | Low | Medium | Grep search for "stamp" after changes |
| External dependencies | None | None | Stamp processor is isolated |

---

## 9. Estimated Effort

- **Code changes**: 2-3 hours
- **Testing**: 1-2 hours
- **Database migration**: 30 minutes
- **Documentation**: 30 minutes
- **Total**: **4-6 hours**

---

**End of Document**
