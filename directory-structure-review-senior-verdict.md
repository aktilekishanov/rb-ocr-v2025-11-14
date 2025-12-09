# Senior Engineering Review: Directory Structure Simplification

**Reviewer**: 200 IQ Backend Engineer  
**Date**: 2025-12-09  
**Review Type**: Pre-Implementation Critical Analysis

---

## ✅ STRENGTHS OF PROPOSED PLAN

### 1. **Excellent Goal Alignment**
- Clear reduction in complexity (5 dirs → 1 dir)
- Sequential numbering improves debuggability
- Eliminates empty folders (validation/)

### 2. **Well-Structured Plan**
- 9 logical phases
- Clear before/after comparisons
- Comprehensive testing strategy

---

## ⚠️ CRITICAL ISSUES FOUND

### **ISSUE #1: Redundant Code NOT Being Addressed**

**Problem**: The plan changes `validation_dir` references but MISSES the opportunity to eliminate entire dead code paths.

**Evidence**:
```python
# pipeline/orchestrator.py, line 460
output_dir=str(ctx.validation_dir),
filename=VALIDATION_FILENAME,
write_file=False,  # ❌ NEVER WRITES!
```

**Why this matters**:
- `validation.json` is NEVER written (`write_file=False`)
- Yet we're changing `ctx.validation_dir` → `ctx.base_dir`  
- **This is tech debt disguised as refactoring**

**Recommendation**: 
- ❌ **DON'T** change `output_dir` and `filename` parameters
- ✅ **DO** remove these parameters entirely from `validate_run()` signature
- Simplify the function to only return validation results in-memory

---

### **ISSUE #2: The "file/" Subfolder is Questionable**

**Current Proposal**:
```
runs/2025-12-09/{run_id}/
├── file/{original_filename}  # ❌ Only 1 file in a subfolder
├── 01_ocr.filtered.json
├── 02_llm_dtc.filtered.json
├── 03_llm_ext.filtered.json
└── 04_final.json
```

**Why a subfolder for 1 file?**
- No technical justification
- Adds visual clutter (`file/` directory)
- User said "no extra folders"

**Alternative - TRUE FLAT STRUCTURE**:
```
runs/2025-12-09/{run_id}/
├── 00_input.pdf               # ✅ Numbered like everything else
├── 01_ocr.filtered.json
├── 02_llm_dtc.filtered.json
├── 03_llm_ext.filtered.json
└── 04_final.json
```

**Benefits**:
- ✅ **TRULY** flat (5 files, 0 subdirectories)
- ✅ Consistent numbering scheme (00, 01, 02, 03, 04)
- ✅ Easier to navigate (`ls` shows everything)
- ✅ Matches user's request: "no extra folders"

---

### **ISSUE #3: Config Constants Still Create Coupling**

**Proposed**:
```python
OCR_FILTERED = "01_ocr.filtered.json"
LLM_DTC_FILTERED = "02_llm_dtc.filtered.json"
```

**Problem**: Constants should be in ONE place

**Better Approach**:
```python
# config.py - SINGLE SOURCE OF TRUTH
class ArtifactFilenames:
    INPUT = "00_input{ext}"  # Preserves extension
    OCR_FILTERED = "01_ocr.filtered.json"
    LLM_DTC_FILTERED = "02_llm_dtc.filtered.json"
    LLM_EXT_FILTERED = "03_llm_ext.filtered.json"
    FINAL = "04_final.json"
    
    # Ephemeral (deleted after use)
    LLM_DTC_RAW = "02_llm_dtc.raw.json"
    LLM_EXT_RAW = "03_llm_ext.raw.json"
```

**Why better**:
- Grouped by concern (artifacts)
- Clear distinction between persisted vs ephemeral
- Single import: `from config import ArtifactFilenames as AF`

---

### **ISSUE #4: Missing Opportunity for Even More Cleanup**

**Dead Code Candidate**:
The plan doesn't mention removing `stage_merge` function entirely.

**Current Status**:
- `stage_merge` is REMOVED from pipeline execution ✅
- But the **function still exists** in the codebase ❌

**Recommendation**:
```python
# DELETE this entire function (lines ~435-455)
def stage_merge(ctx: PipelineContext) -> dict[str, Any] | None:
    # ... 20 lines of dead code ...
```

---

## 🎯 OPTIMIZED PLAN - FINAL VERDICT

### **Core Changes to Proposed Plan**

#### **Change #1: Ultimate Flat Structure**
```python
def _mk_run_dirs(runs_root: Path, run_id: str) -> dict[str, Path]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    base_dir = runs_root / date_str / run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    
    return {"base": base_dir}  # ✅ Only base_dir needed!
```

#### **Change #2: Input File at Root**
```python
def stage_acquire(ctx: PipelineContext) -> dict[str, Any] | None:
    # Preserve extension, add sequential number
    ext = Path(ctx.original_filename).suffix or ".bin"
    ctx.saved_path = ctx.base_dir / f"00_input{ext}"
    util_copy_file(ctx.source_file_path, ctx.saved_path)
```

#### **Change #3: Remove Dead Parameters**
```python
# validator.py - REMOVE these parameters
def validate_run(
    user_provided_fio: dict[str, str | None],
    extractor_data: dict[str, Any],
    doc_type_data: dict[str, Any],
    # output_dir: str,  # ❌ REMOVE (never used)
    # filename: str,     # ❌ REMOVE (never used)
    # write_file: bool,  # ❌ REMOVE (always False)
) -> dict[str, Any]:
```

#### **Change #4: Delete Dead Function**
```python
# orchestrator.py - DELETE entirely
# def stage_merge(ctx: PipelineContext) -> ...
#     (remove all 20 lines)
```

---

## 📊 COMPARISON: Proposed vs Optimized

| Aspect | Proposed Plan | Optimized Plan |
|--------|---------------|----------------|
| **Subdirectories** | 1 (`file/`) | 0 (truly flat) |
| **File count** | 5 | 5 |
| **Numbering** | 01-04 (inconsistent) | 00-04 (consistent) |
| **Dead code removed** | stage_merge in pipeline | + function deletion + validator params |
| **Config organization** | Scattered constants | Grouped class |
| **Complexity** | Medium | Low |

---

## 🚨 FINAL VERDICT

### **Grade: B+ (Good, but can be A+)**

**Strengths**:
- ✅ Solid refactoring plan
- ✅ Clear phases
- ✅ Good testing strategy

**Critical Improvements Needed**:
1. **🔴 MANDATORY**: Remove `file/` subfolder (user said "no extra folders")
2. **🔴 MANDATORY**: Use `00_input{ext}` naming for true consistency
3. **🟡 RECOMMENDED**: Remove dead `output_dir`, `filename`, `write_file` params from validator
4. **🟡 RECOMMENDED**: Delete `stage_merge` function entirely
5. **🟢 NICE-TO-HAVE**: Organize constants into `ArtifactFilenames` class

---

## ✅ RECOMMENDED APPROACH

### **Option A: Proposed Plan (B+ Implementation)**
- Proceed as-is
- Fast to implement
- Leaves some tech debt

### **Option B: Optimized Plan (A+ Implementation)** ⭐ RECOMMENDED
- Add 30 minutes to implementation
- Zero subdirectories (truly flat)
- Eliminates more dead code
- Sets up for future maintainability

---

## 💡 IMPLEMENTATION RECOMMENDATION

**I recommend Option B (Optimized Plan)** for these reasons:

1. **User explicitly said**: "no extra folders" - `file/` violates this
2. **Technical excellence**: Sequential numbering `00-04` is cleaner than `file/`, `01-04`
3. **Future-proof**: Removing dead code now prevents confusion later
4. **Minimal extra cost**: ~30 minutes for significantly better result

**Would you like me to**:
- A) Proceed with **original plan** (as documented)
- B) Proceed with **optimized plan** (my recommendation)
- C) Discuss specific optimizations before deciding
