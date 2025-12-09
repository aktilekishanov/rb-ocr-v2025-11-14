# Directory Structure Simplification - OPTIMIZED Implementation Plan

**Date**: 2025-12-09  
**Version**: 2.0 (Optimized - Senior Engineer Review)  
**Goal**: Truly flat directory with zero subdirectories  
**Impact**: Maximum simplicity, zero dead code, consistent numbering

---

## Current vs Target Structure

### AS-IS (Current)
```
runs/2025-12-09/{run_id}/
├── input/original/{file}
├── llm/
│   ├── doc_type_check.filtered.json
│   └── extractor.filtered.json
├── meta/
│   └── final.json
├── ocr/
│   └── ocr_response.filtered.json
└── validation/ (empty folder)
```

**Issues**:
- 5 subdirectories (unnecessary nesting)
- Empty validation folder
- No clear file ordering
- Harder to navigate/debug

### TO-BE (Optimized Target) ⭐
```
runs/2025-12-09/{run_id}/
├── 00_input.pdf
├── 01_ocr.filtered.json
├── 02_llm_dtc.filtered.json
├── 03_llm_ext.filtered.json
└── 04_final.json
```

**Benefits**:
- ✅ **TRULY FLAT**: 0 subdirectories (not even `file/`)
- ✅ **CONSISTENT NUMBERING**: 00, 01, 02, 03, 04
- ✅ **ZERO EMPTY FOLDERS**: None created
- ✅ **SEQUENTIAL CLARITY**: Numbers = processing order
- ✅ **ONE ls COMMAND**: See everything immediately

---

## Implementation Phases

### Phase 1: Update Directory Creation (SIMPLIFIED)

**File**: `pipeline/orchestrator.py`

**Current**:
```python
def _mk_run_dirs(runs_root: Path, run_id: str) -> dict[str, Path]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_dir = runs_root / date_str / run_id
    input_dir = base_dir / "input" / "original"
    ocr_dir = base_dir / "ocr"
    llm_dir = base_dir / "llm"
    meta_dir = base_dir / "meta"
    validation_dir = base_dir / "validation"
    for d in (input_dir, ocr_dir, llm_dir, meta_dir, validation_dir):
        d.mkdir(parents=True, exist_ok=True)
    return {
        "base": base_dir,
        "input": input_dir,
        "ocr": ocr_dir,
        "llm": llm_dir,
        "meta": meta_dir,
        "validation": validation_dir,
    }
```

**Target (Optimized)**:
```python
def _mk_run_dirs(runs_root: Path, run_id: str) -> dict[str, Path]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_dir = runs_root / date_str / run_id
    
    # Create only base directory - all files written here
    base_dir.mkdir(parents=True, exist_ok=True)
    
    return {"base": base_dir}
```

**Changes**:
- ✅ Remove ALL subdirectory creation
- ✅ Only create base_dir
- ✅ Return dict with single key (maintains compatibility)

---

### Phase 2: Update PipelineContext (SIMPLIFIED)

**File**: `pipeline/orchestrator.py`

**Current Properties**:
```python
@property
def input_dir(self) -> Path:
    return self.dirs["input"]

@property
def ocr_dir(self) -> Path:
    return self.dirs["ocr"]

@property
def llm_dir(self) -> Path:
    return self.dirs["llm"]

@property
def meta_dir(self) -> Path:
    return self.dirs["meta"]

@property
def validation_dir(self) -> Path:
    return self.dirs["validation"]
```

**Target (Optimized)**:
```python
# REMOVE ALL PROPERTY METHODS
# All stages now use ctx.base_dir directly
```

**Impact**: 
- Delete 25 lines of property methods
- All stages write to `ctx.base_dir`

---

### Phase 3: Update stage_acquire (NUMBERED INPUT)

**Current**:
```python
def stage_acquire(ctx: PipelineContext) -> dict[str, Any] | None:
    base_name = util_safe_filename(ctx.original_filename or ...)
    ctx.saved_path = ctx.input_dir / base_name
    util_copy_file(ctx.source_file_path, ctx.saved_path)
```

**Target (Optimized)**:
```python
def stage_acquire(ctx: PipelineContext) -> dict[str, Any] | None:
    # Preserve original extension, add sequential number
    ext = Path(ctx.original_filename).suffix or ".bin"
    ctx.saved_path = ctx.base_dir / f"00_input{ext}"
    util_copy_file(ctx.source_file_path, ctx.saved_path)
```

**Why better**:
- Consistent `00_` prefix
- Preserves file extension
- No need for filename sanitization (fixed name)

---

### Phase 4: Update stage_ocr

**Current**:
```python
def stage_ocr(ctx: PipelineContext) -> dict[str, Any] | None:
    ocr_result = ask_tesseract(..., output_dir=str(ctx.ocr_dir), ...)
    filtered_pages_path = filter_ocr_response(
        ..., str(ctx.ocr_dir), filename=OCR_PAGES
    )
```

**Target**:
```python
def stage_ocr(ctx: PipelineContext) -> dict[str, Any] | None:
    ocr_result = ask_tesseract(..., output_dir=str(ctx.base_dir), ...)
    filtered_pages_path = filter_ocr_response(
        ..., str(ctx.base_dir), filename="01_ocr.filtered.json"
    )
```

---

### Phase 5: Update stage_doc_type_check

**Current**:
```python
def stage_doc_type_check(ctx: PipelineContext) -> dict[str, Any] | None:
    dtc_raw_path = ctx.llm_dir / LLM_DOC_TYPE_RAW
    dtc_filtered_path = filter_llm_generic_response(
        str(dtc_raw_path), str(ctx.llm_dir), filename=LLM_DOC_TYPE_FILTERED
    )
```

**Target**:
```python
def stage_doc_type_check(ctx: PipelineContext) -> dict[str, Any] | None:
    dtc_raw_path = ctx.base_dir / "02_llm_dtc.raw.json"  # Ephemeral
    dtc_filtered_path = filter_llm_generic_response(
        str(dtc_raw_path), str(ctx.base_dir), filename="02_llm_dtc.filtered.json"
    )
```

---

### Phase 6: Update stage_extract

**Current**:
```python
def stage_extract(ctx: PipelineContext) -> dict[str, Any] | None:
    llm_raw_path = ctx.llm_dir / LLM_EXTRACTOR_RAW
    filtered_path = filter_llm_generic_response(
        str(llm_raw_path), str(ctx.llm_dir), filename=LLM_EXTRACTOR_FILTERED
    )
```

**Target**:
```python
def stage_extract(ctx: PipelineContext) -> dict[str, Any] | None:
    llm_raw_path = ctx.base_dir / "03_llm_ext.raw.json"  # Ephemeral
    filtered_path = filter_llm_generic_response(
        str(llm_raw_path), str(ctx.base_dir), filename="03_llm_ext.filtered.json"
    )
```

---

### Phase 7: Update fail_and_finalize & finalize_success

**Current**:
```python
def fail_and_finalize(...):
    final_path = ctx.meta_dir / "final.json"
    util_write_json(final_path, final_json)
```

**Target**:
```python
def fail_and_finalize(...):
    final_path = ctx.base_dir / "04_final.json"
    util_write_json(final_path, final_json)
```

---

### Phase 8: Update Config Constants (ORGANIZED)

**File**: `pipeline/core/config.py`

**Current**:
```python
OCR_PAGES = "ocr_response.filtered.json"
LLM_DOC_TYPE_RAW = "doc_type_check.raw.json"
LLM_DOC_TYPE_FILTERED = "doc_type_check.filtered.json"
LLM_EXTRACTOR_RAW = "extractor.raw.json"
LLM_EXTRACTOR_FILTERED = "extractor.filtered.json"
METADATA_FILENAME = "metadata.json"  # Removed
VALIDATION_FILENAME = "validation.json"  # Dead
```

**Target (Optimized)**:
```python
class ArtifactFilenames:
    """Sequential numbered filenames for run artifacts."""
    
    # Persistent files (kept for debugging)
    INPUT = "00_input{ext}"  # Template, ext filled at runtime
    OCR_FILTERED = "01_ocr.filtered.json"
    LLM_DTC_FILTERED = "02_llm_dtc.filtered.json"
    LLM_EXT_FILTERED = "03_llm_ext.filtered.json"
    FINAL = "04_final.json"
    
    # Ephemeral files (deleted after processing)
    LLM_DTC_RAW = "02_llm_dtc.raw.json"
    LLM_EXT_RAW = "03_llm_ext.raw.json"

# Backward compatibility (if needed elsewhere)
OCR_PAGES = ArtifactFilenames.OCR_FILTERED
FINAL_JSON = ArtifactFilenames.FINAL
```

**Why better**:
- Grouped by concern
- Clear persistence model
- Self-documenting
- Easy to import: `from config import ArtifactFilenames as AF`

---

### Phase 9: Remove Dead Code from Validator

**File**: `pipeline/processors/validator.py`

**Current**:
```python
def validate_run(
    user_provided_fio: dict[str, str | None],
    extractor_data: dict[str, Any],
    doc_type_data: dict[str, Any],
    output_dir: str,           # ❌ DEAD (never used)
    filename: str,              # ❌ DEAD (never used)
    write_file: bool = False,  # ❌ DEAD (always False)
) -> dict[str, Any]:
```

**Target (Optimized)**:
```python
def validate_run(
    user_provided_fio: dict[str, str | None],
    extractor_data: dict[str, Any],
    doc_type_data: dict[str, Any],
) -> dict[str, Any]:
```

**Changes**:
- Remove `output_dir`, `filename`, `write_file` parameters
- Function now ONLY validates and returns results
- No file I/O concerns

**Update caller in orchestrator.py**:
```python
# Before
validation = validate_run(
    ...,
    output_dir=str(ctx.validation_dir),
    filename=VALIDATION_FILENAME,
    write_file=False,
)

# After
validation = validate_run(
    user_provided_fio={"fio": ctx.fio},
    extractor_data=ctx.extractor_result,
    doc_type_data=ctx.doc_type_result,
)
```

---

### Phase 10: Delete Dead Function (stage_merge)

**File**: `pipeline/orchestrator.py`

**Current**: Function exists (lines ~435-455)
```python
def stage_merge(ctx: PipelineContext) -> dict[str, Any] | None:
    try:
        with stage_timer(ctx, "llm"):
            merged_path = merge_extractor_and_doc_type(...)
        # ... 15 more lines ...
    except Exception as e:
        return fail_and_finalize("MERGE_FAILED", str(e), ctx)
```

**Target**: 
```python
# DELETE ENTIRE FUNCTION
```

**Why safe**:
- Already removed from pipeline execution
- No other references in codebase
- Saves 20 lines of dead code

---

## Final Directory Structure

### Before (Current)
```
runs/2025-12-09/uuid-v4/
├── input/
│   └── original/
│       └── document.pdf
├── llm/
│   ├── doc_type_check.filtered.json
│   └── extractor.filtered.json
├── meta/
│   └── final.json
├── ocr/
│   └── ocr_response.filtered.json
└── validation/ (empty)

Subdirectories: 5
Files at root: 0
```

### After (Optimized Target) ⭐
```
runs/2025-12-09/uuid-v4/
├── 00_input.pdf
├── 01_ocr.filtered.json
├── 02_llm_dtc.filtered.json
├── 03_llm_ext.filtered.json
└── 04_final.json

Subdirectories: 0  ✅
Files at root: 5   ✅
```

**Metrics**:
- 📉 **100% reduction** in subdirectories (5 → 0)
- 📈 **∞% increase** in files at root (0 → 5)
- 🎯 **Sequential numbering**: 00, 01, 02, 03, 04
- 🧹 **Dead code removed**: validator params + stage_merge function

---

## Testing Strategy

### Unit Tests
```python
def test_mk_run_dirs_creates_only_base():
    """Test that only base directory is created."""
    dirs = _mk_run_dirs(Path("/tmp"), "test-123")
    assert "base" in dirs
    assert len(dirs) == 1  # Only base
    
def test_no_subdirectories_created():
    """Verify no subdirectories in run folder."""
    # Run full pipeline
    subdirs = list(base_dir.iterdir())
    dirs = [d for d in subdirs if d.is_dir()]
    assert len(dirs) == 0  # Zero subdirectories!
    
def test_all_files_numbered_sequentially():
    """Verify files follow 00-04 pattern."""
    files = sorted([f.name for f in base_dir.iterdir() if f.is_file()])
    assert files[0].startswith("00_")
    assert files[1].startswith("01_")
    assert files[2].startswith("02_")
    assert files[3].startswith("03_")
    assert files[4].startswith("04_")
```

### Integration Tests
```bash
# After successful run
ls -la runs/2025-12-09/{run_id}/

# Expected output (5 files, no directories):
# 00_input.pdf
# 01_ocr.filtered.json
# 02_llm_dtc.filtered.json
# 03_llm_ext.filtered.json
# 04_final.json

# Verify ZERO subdirectories
find runs/2025-12-09/{run_id}/ -type d -mindepth 1 | wc -l
# Expected: 0
```

---

## Comparison: Original vs Optimized Plan

| Feature | Original Plan | Optimized Plan |
|---------|---------------|----------------|
| **Subdirectories** | 1 (`file/`) | 0 (truly flat) ✅ |
| **Input file naming** | `file/{filename}` | `00_input{ext}` ✅ |
| **Numbering consistency** | Mixed | 00-04 sequential ✅ |
| **PipelineContext properties** | Keep as no-ops | Delete entirely ✅ |
| **Validator dead params** | Keep | Remove ✅ |
| **stage_merge function** | Keep | Delete ✅ |
| **Config organization** | Scattered | ArtifactFilenames class ✅ |
| **Dead code removed** | ~0 lines | ~50 lines ✅ |

---

## Implementation Checklist

### Core Refactoring
- [ ] Phase 1: Simplify `_mk_run_dirs()` (return only base_dir)
- [ ] Phase 2: Delete PipelineContext property methods
- [ ] Phase 3: Update stage_acquire (00_input{ext})
- [ ] Phase 4: Update stage_ocr (ctx.base_dir)
- [ ] Phase 5: Update stage_doc_type_check (ctx.base_dir)
- [ ] Phase 6: Update stage_extract (ctx.base_dir)
- [ ] Phase 7: Update fail_and_finalize & finalize_success
- [ ] Phase 8: Create ArtifactFilenames class in config

### Dead Code Removal
- [ ] Phase 9: Remove validator dead parameters
- [ ] Phase 10: Delete stage_merge function entirely
- [ ] Verify no references to deleted code

### Testing & Verification
- [ ] Test imports
- [ ] Run full pipeline (success case)
- [ ] Run error cases (OCR_FAILED, etc.)
- [ ] Verify 0 subdirectories created
- [ ] Verify 5 files with correct naming
- [ ] Check no empty folders anywhere

---

## Migration Strategy

### Deployment
1. Deploy new code
2. New runs use flat structure
3. Old runs unchanged (historical)
4. No data migration needed

### Rollback Plan
```bash
# If needed, revert to previous commit
git revert <commit-hash>
```

---

## Risks & Mitigation

### Risk 1: Code dependencies on old structure
**Mitigation**: Comprehensive grep for property usage
```bash
grep -r "ctx.input_dir" .
grep -r "ctx.ocr_dir" .
grep -r "ctx.llm_dir" .
grep -r "ctx.meta_dir" .
grep -r "ctx.validation_dir" .
```

### Risk 2: External scripts parsing structure
**Mitigation**: 
- Update documentation
- Communicate change to DevOps
- New structure is simpler to parse

### Risk 3: File extension handling
**Mitigation**: Always preserve original extension:
```python
ext = Path(filename).suffix or ".bin"
```

---

**Estimated Time**: 1.5-2 hours  
**Complexity**: Low-Medium (systematic refactoring)  
**Risk Level**: Low (isolated change, backward compatible for historical data)  
**Code Quality Improvement**: HIGH (removes 50+ lines of dead code)

---

**OPTIMIZATIONS SUMMARY**:
- ✅ 0 subdirectories (user requirement: "no extra folders")
- ✅ Consistent 00-04 numbering
- ✅ ~50 lines of dead code removed
- ✅ Organized config with ArtifactFilenames class
- ✅ Cleaner validator signature
- ✅ Production-grade implementation
