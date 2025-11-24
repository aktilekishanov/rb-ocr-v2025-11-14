# Changes Inspection Report (main-dev)

Date: 2025-11-21
Scope: apps/main-dev

## Method
- Reviewed Python sources under `rb-ocr/` including orchestrator, clients, processors, utils, models, core.
- Searched for legacy `gpt` references, outdated imports, and mismatched artifact/timing keys.
- Checked newly added files (`llm_client.py`, `filter_llm_generic_response.py`) and removals.
- Verified manifest/timing wiring and UI consumption.

## High-level Status
- No broken imports detected after renames.
- No remaining runtime uses of `gpt` naming in code (only model id strings like `"gpt-4o"` and documentation references remain).
- Service should run with unchanged behavior, given required dependencies are present.

## Findings and Risks

- [ok] Imports and file references
  - Orchestrator imports `filter_llm_generic_response` from the new file — OK.
  - Processors import `ask_llm` from `clients/llm_client.py` — OK.
  - Removed files `clients/gpt_client.py` and `processors/filter_gpt_generic_response.py` are not referenced anywhere — OK.

- [minor] Error codes consistency
  - New code returns `"UNKNOWN_ERROR"` via `fail_and_finalize` but it has no user-facing message in `core/errors.py`. This does not crash; UI displays fallback (`code` or `message`).
  - Renamed `GPT_FILTER_PARSE_ERROR` → `LLM_FILTER_PARSE_ERROR` in errors map; this code is not currently used anywhere in the pipeline. No crash risk, but consider standardizing error taxonomy.

- [minor] Timing metrics semantics
  - `llm_seconds` accumulates time across multiple stages (doc-type, extractor, merge, validation) where `stage_timer(ctx, "llm")` is used. UI reads `llm_seconds` — consistent and non-breaking.
  - If you want stricter semantics (inference-only), split timers into `llm_inference_seconds`, `merge_seconds`, `validation_seconds`.

- [minor] Validation directory currently unused
  - `validation/` is created but `validate_run(..., output_dir=str(ctx.llm_dir), write_file=False)` keeps validation results in-memory and under `llm/`. No crash; but inconsistent with the new folder’s intent.

- [minor] Docs out-of-date
  - `PROJ_STRUCT_CURRENT_STATE.MD`, `refactor_artifacts.md`, `CHANGELOG.TXT`, `REFACTOR_PROJECT_STRUCTURE.md` still mention some legacy items (for example older `gpt`-specific names). Harmless, but confusing.

- [minor] Security / env hardcodes
  - `clients/llm_client.py` uses `_create_unverified_context()` (skips SSL verification). This mirrors prior behavior; acceptable for dev, not ideal for prod.
  - `processors/stamp_check.py` contains absolute paths to detector resources. Protected by `STAMP_ENABLED` flag defaulting to False, but should be configurable.

- [potential] Dependencies not enforced could cause runtime failures
  - `validators.py` requires `rapidfuzz`.
  - OCR path uses `httpx` and `Pillow` (for image conversion), and optionally `PyMuPDF` (fitz).
  - `_count_pdf_pages` optionally uses `pypdf` or `PyPDF2`, with fallback heuristic; safe, but install recommended.
  - Absence of these packages will cause runtime errors in relevant paths.

- [minor] Stray files and empty folders
  - `.DS_Store` under `rb-ocr/pipeline/` and empty `packages/`, `stamp-processing/` directories. No crash, but noisy.

## Proposed Fixes (No code changes applied yet)

1) Error codes UX
- Add `"UNKNOWN_ERROR": "Неизвестная ошибка"` to `pipeline/core/errors.py` for better UI messaging.
- Review error taxonomy; wire `LLM_FILTER_PARSE_ERROR` where appropriate.

2) Validation outputs
- If desired, write validation to `validation/validation.json`:
  - In `stage_validate_and_finalize`, set `output_dir=str(ctx.validation_dir)` and `write_file=True`.
  - Keep current behavior behind a feature flag if needed.

3) Timing clarity (optional)
- Replace generic `"llm"` timer usages in merge/validation with stage-specific names:
  - `merge`, `validation`; keep `llm_inference` for inference-only.
- Update manifest and UI accordingly (non-breaking if displayed labels updated).

4) Configuration hardening
- In `core/settings.py`, add optional envs:
  - `RB_IDP_LLM_BASE_URL`, `RB_IDP_LLM_VERIFY_SSL` (bool), `RB_IDP_LLM_MODEL_ID`.
- Update `llm_client.py` to consume these; default to current values for backward compatibility.
- In `processors/stamp_check.py`, move detector paths to env-driven settings with sensible defaults.

5) Dependencies
- Add or update `requirements.txt`/`pyproject.toml` to include:
  - `streamlit`, `httpx`, `Pillow`, `rapidfuzz`, `pypdf` (or `PyPDF2`), `pymupdf` (optional for stamp PDF rendering).
- Optionally add guarded imports/fallbacks in validator for `rapidfuzz` to avoid hard crashes.

6) Docs refresh
- Update references from `gpt` to provider-agnostic `llm` naming in:
  - `PROJ_STRUCT_CURRENT_STATE.MD`
  - `refactor_artifacts.md`
  - `CHANGELOG.TXT`
  - `REFACTOR_PROJECT_STRUCTURE.md`
- Reflect that `ctx.llm_dir` is the canonical path and that `validation/validation.json` is the dedicated validation artifact.
- Ensure contributors follow `CONTRIBUTING_COMMENTS.MD` and `COMMENTING_PHASED_PLAN.MD` for all new and updated comments.

7) Repo hygiene
- Remove `.DS_Store` under `rb-ocr/pipeline/` and consider adding a broader `.gitignore` pattern at repo root.
- Remove empty `packages/` and `stamp-processing/` unless reserved for imminent work.

## Verification Checklist (after applying fixes)
- Run Streamlit app and complete a full run:
  - Upload PDF and image; verify OCR results saved to `ocr/` and filtered `ocr_response_filtered.json`.
  - Confirm LLM steps produce `doc_type_check.*.json`, `extractor.*.json`, and `merged.json` under `llm/`.
  - Confirm `manifest.json` contains `llm_seconds`, `ocr_seconds`, `stamp_seconds` (if enabled).
  - UI shows “LLM (сек)” and renders `side_by_side.json`.
  - If enabled, `validation/validation.json` is created and consistent with final verdict.
- Check that no imports fail and no references to deleted files exist.

## Conclusion
- Current refactor is consistent and should not crash the service, assuming dependencies are installed and STAMP is left disabled (or configured). The items above are recommended to improve robustness, clarity, and production readiness.
