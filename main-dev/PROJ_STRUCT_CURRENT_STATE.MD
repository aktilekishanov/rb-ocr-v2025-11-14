# Project Structure — Current State (main-dev)

## Evaluation
- Score: 83/100
- Rationale:
  - Strengths: clear `pipeline/` package, centralized settings (`RUNS_DIR`), provider-agnostic `llm/` artifacts, standardized JSON filenames, staged orchestrator with timing and centralized error handling, versioned prompts, typed DTOs.
  - Gaps: repo contains generated files (`__pycache__/`, `.DS_Store`), no pyproject/packaging/tooling/tests/CI, empty placeholders (`packages/`, `stamp-processing/`), environment docs not externalized.

## Top-level
```
apps/
  main-dev/
    REFACTOR_PROJECT_STRUCTURE.md
    PROJ_STRUCT_CURRENT_STATE.MD   <-- this file
    CHANGELOG.TXT                  <-- generated changelog
    packages/                      # (empty)
    stamp-processing/              # (empty)
    rb-ocr/
      app.py                       # Streamlit UI
      runs/                        # runtime artifacts root (default)
      pipeline/
        orchestrator.py
        clients/
          llm_client.py
          tesseract_async_client.py
          textract_client.py
        core/
          config.py                # filenames, limits, flags
          settings.py              # provides RUNS_DIR (env override RB_IDP_RUNS_DIR)
          dates.py
          errors.py
          validity.py
        models/
          dto.py                   # DocTypeCheck, ExtractorResult, OCRPages
        processors/
          agent_doc_type_checker.py
          agent_extractor.py
          filter_llm_generic_response.py
          filter_ocr_response.py
          filter_textract_response.py
          fio_matching.py
          merge_outputs.py
          stamp_check.py
          validator.py
        prompts/
          dtc/
            v1.prompt.txt
          extractor/
            v1.prompt.txt
        utils/
          artifacts.py
          io_utils.py
          timing.py
```

## Runtime artifacts (per run)
- Root: `rb-ocr/runs/<YYYY-MM-DD>/<run_id>/`
  - `input/original/` — saved upload and visuals
  - `ocr/` — OCR outputs (`ocr_response_raw.json`, `ocr_response_filtered.json`)
  - `llm/` — LLM outputs
    - `doc_type_check.raw.json`, `doc_type_check.filtered.json`
    - `extractor.raw.json`, `extractor.filtered.json`
    - `merged.json`
  - `validation/` — `validation.json` (full validation result, if written)
  - `meta/` — `metadata.json`, `manifest.json`, `final_result.json`, `side_by_side.json`, `stamp_check_response.json`

## Behavior highlights
- UI (`app.py`) imports `RUNS_DIR` from `pipeline.core.settings` and ensures the folder exists.
- Orchestrator creates `llm/` on disk; `ctx.llm_dir` exposes that folder to the pipeline.
- Doc-type and extractor prompts are versioned files and loaded at runtime.
- Filtered JSONs are validated into typed models (pydantic or lightweight fallback).

## Noted gaps / improvements (non-blocking)
- Add `.gitignore` entries for `__pycache__/`, `.DS_Store`, and runtime dirs if needed.
- Introduce `pyproject.toml` with tooling (formatter, linter, type checker) and tests/CI.
- Consider removing empty placeholder folders or document their intent.
- Document environment variables in a `.env.example` (e.g., `RB_IDP_RUNS_DIR`, feature flags).
