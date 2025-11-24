# Refactor Project Structure (main-dev)

## Goals
- Align directory layout, naming, and artifact storage with best practices.
- Improve clarity, testability, and deployability (air-gapped ready).
- Separate source code vs. runtime artifacts and configuration.

## Current State (observed)
Root: `apps/main-dev`
- `rb-ocr/`
  - `app.py` (Streamlit UI)
  - `pipeline/` (package; renamed from the original `rbidp/`)
    - `orchestrator.py` (staged pipeline)
    - `clients/`, `processors/`, `core/`, `utils/`
  - `runs/` (per-run artifacts; empty by default)
- `packages/`, `stamp-processing/` (empty)

Artifact layout (per run): `rb-ocr/runs/<YYYY-MM-DD>/<run_id>/`
- `input/original/` saved upload and stamp visualization
- `ocr/` OCR outputs
- `gpt/` LLM doc-type and extractor outputs (raw/filtered), `merged.json`
- `meta/` `metadata.json`, `final_result.json`, `manifest.json`, `side_by_side.json`, `stamp_check_response.json`

Issues
- Artifact dir `gpt/` is vendor-specific naming; should be provider-agnostic (e.g., `llm/`).
- Source tree and runtime artifacts are mixed under the same project folder (`rb-ocr/runs/`).
- No top-level `pyproject.toml`, no tests folder, no prompts folder, no env-driven settings module.
- A `.DS_Store` exists under package (should be ignored).

## Score (0–100)
- Structure and artifact layout: 65/100
  - Strengths: clear per-run isolation; manifest and final/side_by_side present; filenames centralized in `core/config.py`.
  - Gaps: provider-specific folder name; runtime artifacts co-located with source; missing standard project scaffolding (pyproject, tests, config), no retention policy, prompts not externalized.

## Proposed Best-Practice Structure (Core)
```
apps/
  main-dev/
    packages/                           # optional: reserved for future packages
    rb-ocr/                             # main app
      app.py                            # Streamlit UI (kept as-is)
      pipeline/                         # python package (source)
        __init__.py
        orchestrator.py                 # staged pipeline (current consolidated file)
        clients/
        core/
          config.py                     # filenames and constants
          settings.py                   # env-driven settings
          doc_types.py
          messages_ru.py
        processors/
        prompts/                        # versioned prompt templates
          dtc/
          extractor/
        models/                         # pydantic models
        utils/
      runs/                             # runtime artifacts
        <YYYY-MM-DD>/<run_id>/
          input/original/
          ocr/
          llm/                          # provider-agnostic, replaces `gpt/`
          meta/
    stamp-processing/                   # optional: future stamp processing
```

Key naming and storage conventions
- Use provider-agnostic folder `llm/` instead of `gpt/`.
- Keep raw vs filtered filenames explicit and function-oriented (not provider-oriented), e.g.:
  - `doc_type_check.raw.json`, `doc_type_check.filtered.json`
  - `extractor.raw.json`, `extractor.filtered.json`
  - `merged.json`, `validation.json` (if written), `side_by_side.json`
- Persist final outputs in `meta/`: `manifest.json`, `final_result.json`, `side_by_side.json`, `stamp_check_response.json`.
- Gate heavy artifacts via `ARTIFACTS_ENABLED` (env). Always keep `manifest.json` and `final_result.json`.
- Add retention policy: `RUNS_RETENTION_DAYS` env; optional `scripts/cleanup_runs.py`.

Settings
- Introduce `core/settings.py` (pydantic-settings) to load:
  - Service endpoints, timeouts/retries, SSL verify and CA bundle path.
  - Feature flags: `STAMP_ENABLED`, `ARTIFACTS_ENABLED`.
  - Paths: `RUNS_DIR` default `./rb-ocr/runs`.
  - Limits: `MAX_PDF_PAGES`.

Migration Plan (Core)
1. Keep artifacts at `rb-ocr/runs/`; centralize `RUNS_DIR` in `core/settings.py`.
2. Rename `gpt/` → `llm/`; update paths in orchestrator and processors.
3. Standardize JSON filenames to function-oriented names; adjust `core/config.py`.
4. Add `models/` (pydantic) and refactor processors to use typed contracts.
5. Add `prompts/` with versioned templates; update processors to load from files.

Backwards Compatibility
- Keep the public `run_pipeline` entry point stable in `pipeline.orchestrator` (same signature and semantics).

Rollback & Safety
- All changes are relocations/renames and config indirections; code paths and business logic remain intact.
- Start with path indirection (settings) to enable directory moves with minimal risk.
