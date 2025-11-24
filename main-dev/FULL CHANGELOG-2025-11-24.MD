# FULL CHANGELOG — 2025-11-24 (apps/main-dev)

This changelog describes all substantive changes made under `apps/main-dev/`
up to 2025-11-24, grouped by area. It focuses on the **main-dev** branch of
RB-OCR and covers both code and documentation.

The refactor goals were to:

- Adopt provider-agnostic `llm` naming (instead of `gpt`).
- Stabilize error handling, validation, and artifact layout.
- Introduce typed DTOs and versioned prompts.
- Implement a phased commenting and documentation plan.
- Remove or quarantine legacy/duplicate code paths.

No intentional public API behavior changes were made; the focus was
structure, naming, and documentation.

---

## 1. Orchestrator and pipeline structure

**File:** `rb-ocr/pipeline/orchestrator.py`

- Kept the staged pipeline design (`run_pipeline` with stages: acquire,
  OCR, doc-type check, extraction, merge, validate, finalize).
- Renamed internal artifacts and timers to use provider-agnostic `llm`
  naming:
  - Manifest timing now uses `llm_seconds` instead of `gpt_seconds`.
  - LLM artifacts use `llm_merged_path` keys.
- Wired a dedicated `validation/` directory under each run root:
  - `ctx.validation_dir` added and used for `validation/validation.json`
    (full validation output) instead of writing validation under `llm/`.
- Introduced and wired the `LLM_FILTER_PARSE_ERROR` error code into the
  LLM-related stages to distinguish filter/JSON-parse errors from
  schema/contract errors.
- Ensured `UNKNOWN_ERROR` is used as a generic fallback when unexpected
  exceptions reach `fail_and_finalize`.
- Added a Google-style **module docstring** describing the orchestrator
  responsibilities, run directory layout, and public entrypoint.
- Added a detailed **docstring for `run_pipeline`**, documenting:
  - Parameters (FIO, reason, doc type, source path, content type,
    runs root).
  - Return shape: verdict, errors, artifact paths, and error semantics.

---

## 2. LLM client and provider-agnostic naming

**File:** `rb-ocr/pipeline/clients/llm_client.py`

- Introduced `llm_client.py` as the canonical LLM client (replacing the
  old `gpt_client.py` in main-dev):
  - `call_fortebank_llm(prompt, model, temperature, max_tokens) -> str`.
  - `ask_llm(...) -> str` helper that parses OpenAI-like responses and
    returns plain text (falling back to raw JSON if parsing fails).
- Uses the internal ForteBank endpoint
  `https://dl-ai-dev-app01-uv01.fortebank.com/openai/v1/completions/v2`.
- Added a module docstring describing its role.
- Added **WORKAROUND/SECURITY** notes in the docstring regarding
  `ssl._create_unverified_context()` being used for dev DMZ
  environments and pointing out that this must be hardened for
  production.

**Legacy cleanup:**

- In `apps/main-dev` the `gpt_client.py` path is no longer used; new
  code imports `ask_llm` from `pipeline.clients.llm_client`. The
  legacy rbidp client remains only under `apps/main/` for the old app.

---

## 3. OCR client and Textract client

**File:** `rb-ocr/pipeline/clients/tesseract_async_client.py`

- Introduced an async Tesseract client (`TesseractAsyncClient`) and
  convenience wrappers:
  - `ask_tesseract_async(file_path, ...)` for fully async flows.
  - `ask_tesseract(pdf_path, ...)` synchronous wrapper that optionally
    converts images to PDF via `convert_image_to_pdf` and writes
    `ocr_response_raw.json` under the `ocr/` directory.
- Ensured the output contract:
  - `success`, `error`, `raw_obj`, `raw_path`, `converted_pdf` keys.

**File:** `rb-ocr/pipeline/clients/textract_client.py`

- Retained the ForteBank Textract client but aligned docs and
  conventions:
  - Added a module docstring describing it as the dev OCR endpoint.
  - Added a WORKAROUND/SECURITY note around
    `ssl._create_unverified_context()` similar to the LLM client.

---

## 4. Processors — LLM and OCR stages

### 4.1 Doc-type checker and extractor

**Files:**

- `rb-ocr/pipeline/processors/agent_doc_type_checker.py`
- `rb-ocr/pipeline/processors/agent_extractor.py`

Changes:

- Both processors now import `ask_llm` from `pipeline.clients.llm_client`
  instead of any GPT-specific client.
- Externalized prompts into versioned files and simplified processors to
  small prompt loaders and call sites.
- Added module-level docstrings describing:
  - Their roles (doc-type vs data extraction).
  - How they build prompts from OCR pages and call the LLM.
- Defined `_prompt_path(version)` helpers pointing to:
  - `pipeline/prompts/dtc/{version}.prompt.txt` for doc-type.
  - `pipeline/prompts/extractor/{version}.prompt.txt` for extractor.
- Added Google-style docstrings for the public functions:
  - `check_single_doc_type(pages_obj: dict) -> str`.
  - `extract_doc_data(pages_obj: dict) -> str`.
  - Documented input (normalized OCR pages) and output (raw LLM JSON
    string for downstream filtering).
- Clarified **prompt versioning and placeholder semantics**:
  - Prompt files live under `pipeline/prompts/...`.
  - They are versioned as `v1.prompt.txt`, `v2.prompt.txt`, etc.
  - Each template must contain exactly one `{}` placeholder where the
    pages JSON is injected via `template.replace("{}", pages_json_str,
    1)`.

### 4.2 Generic LLM response filter

**File:** `rb-ocr/pipeline/processors/filter_llm_generic_response.py`

- Replaced GPT-specific naming with provider-agnostic LLM naming.
- Added a module docstring describing its role:
  - Normalize multi-line JSONL / OpenAI-style envelopes into a single
    JSON object for typed DTO validation.
- Improved `filter_llm_generic_response` docstring to describe the
  strategy per line:
  - Try to parse a dict; when present, extract OpenAI-like
    `choices[0].message.content` or `text`.
  - Skip provider prompt-echo dicts that contain `Model` and `Content`.
  - Try to parse strings as nested JSON.
  - Return the first successful dict, or `{}` if none found.

### 4.3 OCR and Textract response filters

**Files:**

- `rb-ocr/pipeline/processors/filter_ocr_response.py`
- `rb-ocr/pipeline/processors/filter_textract_response.py`

- Unified behavior for building per-page text JSON objects of the form:
  `{"pages": [{"page_number": int | None, "text": str}, ...]}`.
- Kept existing docstrings but aligned them with the new DTO contracts.

### 4.4 FIO matching

**File:** `rb-ocr/pipeline/processors/fio_matching.py`

- Introduced detailed FIO matching logic with deterministic and fuzzy
  components:
  - `NameParts` dataclass (last, first, patro).
  - Normalization helpers (`normalize_for_name`, KZ→RU, Latin→Cyrillic
    mappings).
  - Variant construction (`FULL`, `LF`, `FP`, `L_I`, `L_IO`, `L`).
  - Variant detection heuristics and initials normalization.
  - `fio_match(app_fio, doc_fio, enable_fuzzy_fallback=True, ...)`
    returning `(match_bool, diagnostics)`.
- Added module-level and function-level docstrings explaining:
  - Normalization rules.
  - Variant semantics.
  - Matching strategy and diagnostic fields.
- Removed the legacy `rb-ocr/rbidp/utils/io_utils.py` and
  `rb-ocr/rbidp/utils/timing.py` plus `rb-ocr/tests/test_fio_matching.py`
  under the old `rbidp` namespace as part of de-duplication.

### 4.5 Stamp check

**File:** `rb-ocr/pipeline/processors/stamp_check.py`

- Kept the external stamp detector integration.
- Added a module docstring describing its purpose and optional nature.
- Marked hardcoded detector paths as a **WORKAROUND** with guidance to
  move them to env/config-driven settings.

### 4.6 Validator

**File:** `rb-ocr/pipeline/processors/validator.py`

- Centralized run-level validation based on merged extractor/doc-type
  outputs.
- Uses deterministic FIO matching via `fio_match` and retains legacy
  RapidFuzz-based scores as additional diagnostics.
- Added module docstring summarizing checks (FIO, doc type known,
  doc-date validity, single-doc constraint, stamp presence).
- Added a detailed docstring for `validate_run(meta_path, merged_path,
  output_dir, filename, write_file)` describing:
  - Inputs and outputs.
  - When `validation.json` is written vs in-memory only.
  - Shape of the result summary (`checks`, `verdict`, `diagnostics`).

---

## 5. Core modules — config, settings, errors, dates, validity

### 5.1 Configuration and settings

**Files:**

- `rb-ocr/pipeline/core/config.py`
- `rb-ocr/pipeline/core/settings.py`

- `config.py` centralizes filenames, limits, and feature flags (including
  `OCR_PAGES`, `METADATA_FILENAME`, `VALIDATION_FILENAME`, and various
  path names).
- `settings.py` provides `RUNS_DIR` with an env override via
  `RB_IDP_RUNS_DIR`.
- Added concise module docstrings describing responsibilities and
  boundaries.

### 5.2 Errors

**File:** `rb-ocr/pipeline/core/errors.py`

- Established a centralized error-code registry with Russian messages.
- Updated naming from GPT-specific to LLM-specific where appropriate:
  - Introduced `LLM_FILTER_PARSE_ERROR` to replace
    `GPT_FILTER_PARSE_ERROR` in main-dev.
- Added a user-facing message for `UNKNOWN_ERROR` to avoid UI fallback.
- Removed unused legacy codes (`DOC_TYPE_MISMATCH`, `DOC_TYPE_MISSING`)
  from the main-dev map to simplify the taxonomy.
- Added a module docstring describing the role of this registry and the
  helper functions.

**File:** `main/rbocr/rbidp/core/errors.py` (legacy app)

- Left the older app mostly intact but renamed the filter-parse error
  code to `LLM_FILTER_PARSE_ERROR` while preserving its legacy
  semantics.
- Removed an obsolete, checkpointed block of alternate error-code
  definitions that had been commented out.

### 5.3 Date and validity utilities

**Files:**

- `rb-ocr/pipeline/core/dates.py`
- `rb-ocr/pipeline/core/validity.py`

- `dates.py`:
  - Provides `parse_doc_date` (multi-format date parsing) and
    `now_utc_plus(hours=5)`.
  - Added clear docstrings explaining expected formats and offset
    semantics.
- `validity.py`:
  - Provides `compute_valid_until(doc_type, doc_date_str)` and
    `is_within_validity(valid_until_dt, now_dt)`.
  - Added docstrings documenting policies, tri-state return values, and
    the relationship between policy windows and effective dates.

---

## 6. DTO models

**File:** `rb-ocr/pipeline/models/dto.py`

- Introduced Pydantic-based (or lightweight fallback) DTOs for key data
  contracts used across the pipeline:
  - `DocTypeCheck`
  - `ExtractorResult`
  - `OCRPage`, `OCRPages`
- Added a module docstring describing the goal: stable, typed
  contracts between stages.
- Added short class docstrings summarizing each model.

---

## 7. Utilities — IO, artifacts, timing

### 7.1 IO utilities

**File:** `rb-ocr/pipeline/utils/io_utils.py`

- Contains helpers for `ensure_parent`, `safe_filename`, `write_json`,
  `read_json`, and `copy_file`.
- Added module and function docstrings detailing guarantees and
  behaviors:
  - Always creates parent directories before write/copy.
  - Uses UTF-8 with `ensure_ascii=False` for JSON.
  - `safe_filename` normalization rules and fallback.

### 7.2 Artifacts

**File:** `rb-ocr/pipeline/utils/artifacts.py`

- `build_final_result`:
  - Writes `meta/final_result.json` with a minimal public contract:
    `run_id`, boolean `verdict`, and error **codes** only.
  - Returns an internal summary including full error objects and the
    final-result path.
- `write_manifest`:
  - Writes `meta/manifest.json` with `run_id`, `created_at`, timing
    metrics (`duration_seconds`, `llm_seconds`, `ocr_seconds`,
    `stamp_seconds`), file info, and artifact paths.
- `build_side_by_side`:
  - Builds `meta/side_by_side.json`, a human-facing comparison of meta
    vs extracted fields (FIO, doc type, doc date, validity window,
    single-doc flag, doc-type-known flag, and stamp presence).
- Added module and function docstrings clarifying:
  - The distinction between contract artifacts (final_result, manifest)
    and diagnostic views (side_by_side).
  - How `compute_valid_until` and `format_date` are used to populate
    validity info.

### 7.3 Timing

**File:** `rb-ocr/pipeline/utils/timing.py`

- Provides `StageTimers` and `stage_timer(ctx, name)`.
- Added module docstring explaining that StageTimers are used to
  accumulate per-stage wall-clock seconds for manifest metrics.
- Added docstrings for `StageTimers` and `timer` describing
  accumulation behavior and context-manager usage.

Legacy `rb-ocr/rbidp/utils/io_utils.py` and `rb-ocr/rbidp/utils/timing.py`
were removed as no longer needed in main-dev.

---

## 8. App entrypoint (Streamlit UI)

**File:** `rb-ocr/app.py`

- Updated references from GPT to LLM in user-facing labels and timing
  display (`LLM (сек)` using `llm_seconds`).
- Confirmed that the UI reads from the new manifest fields and
  validation artifacts when available.
- Added a concise module docstring describing the app’s responsibility
  and its relationship to the pipeline.

---

## 9. Prompts and domain knowledge

**Directory:** `rb-ocr/pipeline/prompts/`

- Created `README.md` explaining:
  - Directory structure (`dtc/`, `extractor/`).
  - Versioning scheme (`v1.prompt.txt`, `v2.prompt.txt`, ...).
  - Placeholder convention (exactly one `{}` per template for pages
    JSON injection).
  - Backward-compatibility expectations when changing prompt content.

- Confirmed that processors load prompts via `_prompt_path(version)`
  helpers and do not embed prompt text inline.

---

## 10. Commenting and documentation

**Files:**

- `CONTRIBUTING_COMMENTS.MD`
- `COMMENTING_PHASED_PLAN.MD`
- `PROJ_STRUCT_CURRENT_STATE.MD`
- `refactor_artifacts.md`
- `CHANGES_INSPECTION.MD`
- `CHANGELOG.TXT`

Key changes:

- `CONTRIBUTING_COMMENTS.MD`:
  - Defines the commenting conventions for main-dev: Google-style
    docstrings, structured comment taxonomy (TODO, NOTE, WORKAROUND,
    PERF, SECURITY), and when to comment vs not comment.
- `COMMENTING_PHASED_PLAN.MD`:
  - Documents a phased rollout (Phases 0–6) for adding
    high-signal comments and docstrings across the codebase.
  - All phases up to Phase 6 have now been implemented in main-dev.
- `PROJ_STRUCT_CURRENT_STATE.MD` and `refactor_artifacts.md`:
  - Updated to reflect `llm_client.py`, `filter_llm_generic_response.py`,
    `ctx.llm_dir`, and the dedicated `validation/` folder.
- `CHANGES_INSPECTION.MD`:
  - Records the inspection of the refactor, including remaining risks
    and recommendations.
  - Now explicitly references `CONTRIBUTING_COMMENTS.MD` and
    `COMMENTING_PHASED_PLAN.MD` as the authorities on commenting.
- `CHANGELOG.TXT`:
  - Captures earlier refactor milestones (package rename, utilities,
    typed DTOs, timing, and artifact layout); this `FULL CHANGELOG`
    augments it with a complete snapshot as of 2025-11-24.

---

## 11. Legacy and hygiene clean-up

- Removed old `rb-ocr/rbidp/utils/io_utils.py` and
  `rb-ocr/rbidp/utils/timing.py` that duplicated new utilities.
- Removed `rb-ocr/tests/test_fio_matching.py` under the old `rbidp`
  namespace; FIO matching is now tested indirectly via the main-dev
  pipeline.
- Cleaned up a checkpointed alternate error-code block in
  `main/rbocr/rbidp/core/errors.py` that was commented out and no
  longer used.
- Confirmed there are no remaining runtime uses of GPT-specific naming
  (`gpt_`), aside from literal model identifiers such as `"gpt-4o"`.

---

## 12. Backward compatibility and behavior

- All changes in **main-dev** were made with the explicit constraint of
  preserving public behavior:
  - `run_pipeline` signature and high-level behavior remain the same.
  - Artifact contracts (JSON shapes) remain compatible, with the
    addition of `validation/validation.json` as an optional,
    out-of-band diagnostic artifact.
  - UI continues to render results based on
    `final_result.json`, `manifest.json`, and `side_by_side.json`.
- The **main** app under `apps/main/` retains its original
  `rbocr/rbidp` layout and remains isolated from the main-dev refactor.

---

## 13. Summary

As of 2025-11-24, `apps/main-dev/` has:

- A provider-agnostic, LLM-centric pipeline with clear artifact and
  validation structure.
- Centralized error codes and typed DTO contracts.
- Versioned prompts and documented placeholder conventions.
- A fully implemented commenting and documentation plan, including
  module and API docstrings for all critical entrypoints.
- Cleaned-up legacy `rbidp` utilities and error-code scaffolding.

These changes aim to make the RB-OCR main-dev pipeline easier to
maintain, reason about, and extend, while keeping the external behavior
stable for consumers.
