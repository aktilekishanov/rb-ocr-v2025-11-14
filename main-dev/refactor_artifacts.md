# Artifact Layout Refactor — Evaluation and Proposal

## 1. Current State (observed)

### 1.1. Directory layout per run
Root: `rb-ocr/runs/<YYYY-MM-DD>/<run_id>/`

- `input/original/`
  - Original uploaded file (copied from source path).
  - Stamp visualization images (if stamp check runs on image/PDF input).

- `ocr/`
  - `ocr_response_raw.json` — raw OCR JSON from Dev-OCR (Tesseract async).
  - `ocr_response_filtered.json` — normalized per-page text (`{"pages": [{"page_number", "text"}, ...]}`).

- `llm/` (accessed via `ctx.llm_dir`)
  - `doc_type_check.raw.json` — raw LLM output for doc-type classifier (as streamed/logged).
  - `doc_type_check.filtered.json` — filtered JSON from `filter_gpt_generic_response`.
  - `extractor.raw.json` — raw LLM output for extractor.
  - `extractor.filtered.json` — filtered JSON from `filter_gpt_generic_response`.
  - `merged.json` — curated fusion of doc-type + extractor (+ stamp_present if available).
  - `validation.json` — reserved filename for downstream validation result (currently used as in-memory result; on-disk may be disabled via `write_file=False`).

- `meta/`
  - `metadata.json` — user-input metadata (fio, reason, doc_type) and context.
  - `final_result.json` — minimal final file for UI/consumer (run_id, verdict, error codes, optional stamp_present).
  - `manifest.json` — authoritative manifest including timings, file info, artifact paths, status, and error code.
  - `side_by_side.json` — curated comparison view (fio/doc_type/doc_date, validity window, stamp_present).
  - `stamp_check_response.json` — small JSON from stamp detector (e.g., `{ "stamp_present": true|false }`).

### 1.2. Write paths (summary of logic)

- `_mk_run_dirs` (orchestrator):
  - Creates `input/original`, `ocr`, `llm`, `meta` under a dated run root.

- `stage_acquire`:
  - Copies the uploaded file into `input/original/`.
  - Writes `metadata.json` into `meta/`.

- `stage_ocr`:
  - Calls Dev-OCR via `ask_tesseract` and writes `ocr_response_raw.json` into `ocr/`.
  - Builds `ocr_response_filtered.json` into `ocr/`.

- `stage_doc_type_check`:
  - Writes raw classifier output to `llm/doc_type_check.raw.json`.
  - Writes filtered output to `llm/doc_type_check.filtered.json`.

- `stage_extract_and_stamp`:
  - Writes raw extractor output to `llm/extractor.raw.json` (then deletes raw file after filtering).
  - Writes filtered extractor output to `llm/extractor.filtered.json`.
  - If stamp is enabled and available, writes `meta/stamp_check_response.json`.

- `stage_merge`:
  - Reads `llm/doc_type_check.filtered.json` and `llm/extractor.filtered.json`.
  - Writes curated `llm/merged.json`.
  - Writes `meta/side_by_side.json`.

- `stage_validate_and_finalize` + `utils.artifacts`:
  - Uses `meta/metadata.json` and `llm/merged.json` for validation.
  - Builds a structured in-memory `validation` result (and could write `llm/validation.json` if `write_file=True`).
  - Writes `meta/final_result.json` and `meta/manifest.json`.

### 1.3. Strengths

- Function-oriented filenames (doc_type_check.*, extractor.*, merged.json, validation.json).
- Clear separation of concerns:
  - `input/` — what user gave.
  - `ocr/` — provider-agnostic OCR layer.
  - `llm/` — provider-agnostic LLM layer + fusion + (potential) validation.
  - `meta/` — run-level metadata and "final" artifacts.
- Timing and error metadata centralized in `manifest.json` and `final_result.json`.
- Access to paths is mostly via helper functions and constants (`core/config.py`).


## 2. Issues vs. "World’s Best" Practices

### 2.1. Mixed responsibilities in `llm/`

- `llm/` currently holds both:
  - **Core model I/O artifacts** (raw/filtered LLM outputs, merged.json).
  - **(Potential) validation output** (`validation.json`).
- From a layering perspective, validation is more of a **post-processing / decision** layer that consumes merged data and domain rules; it is conceptually closer to `meta/` outputs (final decision) than to raw LLM I/O.

**Impact:**
- Slightly blurs the boundary between "model outputs" and "decision/diagnostic outputs".
- Increases coupling if more downstream steps are added (e.g., audit logs, manual overrides).

### 2.2. Diagnostics vs. contract artifacts

- There is a mix of:
  - **Contract artifacts**: Consumed by external systems / UI (e.g., `final_result.json`, `manifest.json`, `merged.json`).
  - **Diagnostic / debug artifacts**: `*.raw.json`, `side_by_side.json`, full `validation.json` payload.
- They are not explicitly distinguished in directory layout or naming, which can make retention policies and size control more difficult (e.g., deciding what is safe to delete).

### 2.3. Tight coupling to per-run tree in code

- Many functions assume a specific per-run layout and filenames inline (even if via constants), e.g. `ctx.llm_dir` assumed to be the root for all LLM artifacts.
- While this is not wrong, it makes it harder to:
  - Split long-term archives vs. short-term debug artifacts.
  - Mount only part of the tree in a restricted environment (e.g., keeping only `final_result.json` and `manifest.json`).

### 2.4. Stamp and validation artifacts are buried

- Stamp result lives in `meta/stamp_check_response.json` but is only partially surfaced:
  - `final_result.json` *tries* to include `stamp_present`.
  - `side_by_side.json` optionally includes `stamp_present`.
- Validation result (when/if written) would be `llm/validation.json`, which might not be an obvious place to look for a reviewer compared to `meta/`.


## 3. Proposed Improved Structure

### 3.1. Refined per-run layout

Keep the same top-level shape, but clarify responsibilities and long-term vs. diagnostic artifacts.

```
rb-ocr/runs/<date>/<run_id>/
  input/
    original/
      <uploaded_file>
      <stamp_visuals>...

  ocr/
    ocr_response.raw.json          # raw provider result
    ocr_response.pages.json        # filtered per-page text (was ocr_response_filtered.json)

  llm/
    doc_type_check.raw.json        # raw LLM output
    doc_type_check.filtered.json   # filtered LLM JSON (contract with downstream)
    extractor.raw.json             # raw LLM output
    extractor.filtered.json        # filtered LLM JSON (contract with downstream)
    merged.json                    # curated fusion from doc_type_check/extractor/stamp

  validation/
    validation.json                # full validation result (checks, verdict, diagnostics)

  meta/
    metadata.json                  # user input & high-level context
    final_result.json              # minimal final contract (run_id, verdict, error codes, stamp_present)
    manifest.json                  # manifest + timings + paths
    side_by_side.json              # human-facing comparison view
    stamp_check_response.json      # raw stamp detector result
```

Key changes:

- **Introduce a dedicated `validation/` folder**:
  - Move `validation.json` out of `llm/` into `validation/`.
  - Treat validation as a separate logical stage that consumes merged.json.
- **Make filtered OCR filename more descriptive**:
  - Optionally rename `ocr_response_filtered.json` → `ocr_response.pages.json` (or `ocr_pages.json`) for clarity.
- **Keep diagnostic vs. contract artifacts clearly separated by location + filename**:
  - `input/`, `ocr/`, `llm/` = raw/filtered model pipelines.
  - `validation/`, `meta/` = decision and final outputs.

### 3.2. Logical grouping

- **Model layers**
  - `ocr/` and `llm/` hold data close to the model providers and normalization steps.
- **Decision layer**
  - `validation/validation.json` holds rich diagnostics and detailed checks.
- **Contract layer**
  - `meta/final_result.json` and `meta/manifest.json` are the **primary contracts** for external systems and UI.

### 3.3. Naming and discoverability

- `validation/validation.json` is easier to discover for reviewers and support:
  - Anyone can infer: "Look into `validation/` for detailed decisions."
- `ocr_response.pages.json` (or similar) expresses that this is the per-page structured view, not just a generic "filtered" blob.


## 4. Refactor Plan (Artifacts-only)

This plan assumes you keep the current function signatures and overall orchestrator flow.

### Step 1 — Introduce `validation/` folder

- In `_mk_run_dirs`:
  - Add `validation_dir = base_dir / "validation"` and create it.
  - Extend `dirs` dict to include a key for validation (e.g., `"validation": validation_dir`).
- In `PipelineContext`, add a `validation_dir` property that reads from `dirs["validation"]`.

_No behavior change yet; just prepare the directory._

### Step 2 — Write full validation result to `validation/validation.json`

- In `stage_validate_and_finalize` / `validator.validate_run`:
  - Switch `output_dir` from `ctx.gpt_dir` to `ctx.validation_dir`.
  - Enable `write_file=True` so that `validation.json` is actually written.
- Ensure `VALIDATION_FILENAME` remains `"validation.json"`.

_Result:_ detailed validation artifact is clearly separated under `validation/`.

### Step 3 — Optionally rename OCR filtered file

_Optional but recommended for clarity._

- In `core/config.py`, change:
  - `OCR_PAGES = "ocr_response.pages.json"` (or `ocr_pages.json`).
- All call sites (filter_ocr_response/filter_textract_response) will automatically start using the new name.

### Step 4 — Update manifest references

- In `utils.artifacts.write_manifest`:
  - Keep `final_result_path` and `side_by_side_path` as-is.
  - Optionally add `validation_path` from `artifacts` if present, so manifest links directly to `validation/validation.json`.
- In orchestrator, when validation is run and written, populate `ctx.artifacts["validation_path"]`.

### Step 5 — Retention and flags (later)

_Not required now, but recommended when you add maintenance scripts:_

- Introduce flags in settings for artifact retention, e.g.:
  - `ARTIFACTS_KEEP_LLMM_RAW` to control whether `*.raw.json` are kept or deleted.
  - `ARTIFACTS_KEEP_VALIDATION` if validation JSON is large and only needed in certain environments.


## 5. Evaluation Summary

- **Current structure score (artifacts only):** 80/100
  - Strong separation of source vs. artifacts and function-oriented naming.
  - Clear flow from `input/` -> `ocr/` -> `llm/` -> `meta/`.
  - Some mixing of responsibilities (validation under `llm/`, diagnostics vs. contracts not clearly separated).

- **Proposed structure target:** 92/100
  - Explicit `validation/` stage directory.
  - Better naming for OCR filtered output.
  - `meta/` clearly reserved for contracts and user-facing summaries.
  - Easier future retention and debugging policies.
