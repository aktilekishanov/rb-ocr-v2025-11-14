# COMMENTING_PHASED_PLAN.MD

Goal: Establish a world-class, low-risk plan to add high-signal comments and docstrings across `apps/main-dev/` that improve maintainability and comprehension without creating noise or drift.

Guiding principles:
- Comment why, not what. Prefer self-documenting code first.
- Keep comments truthful and minimal; update or remove when behavior changes.
- Use docstrings for modules/classes/functions; inline comments only for non-obvious logic, algorithms, workarounds, and domain rules.
- Follow a consistent docstring style (Google or NumPy). Keep one style throughout.
- Treat comments as part of the API and review them like code.

Acceptance criteria (for each phase):
- Comments are accurate, concise, and add understanding.
- No redundant or stale comments. CI/lint passes.
- No public behavior changes.

---

## Phase 0 — Setup and conventions (1-2 hrs)
- Choose docstring style: Google-style docstrings (preferred) and single-line inline comments with one leading space after `#`.
- Define comment taxonomy keywords and usage:
  - TODO(owner/issue): actionable, time-bounded items
  - NOTE: rationale or design choice
  - WORKAROUND: temporary fix for external issue (link if possible)
  - PERF: performance considerations
  - SECURITY: security-sensitive notes
- Add a short "Commenting Conventions" section to CONTRIBUTING.md (or create if missing).
- Add a docstring linter/formatter if available (optional).

Deliverable: Conventions recorded; tooling decisions made.

---

## Phase 1 — Critical entrypoints and contracts (0.5 day)
Scope (highest ROI first):
- `rb-ocr/app.py` (Streamlit entrypoint)
- `rb-ocr/pipeline/orchestrator.py` (core orchestration and error/timing)
- `rb-ocr/pipeline/core/` (errors.py, config.py, settings.py, validity.py, dates.py)
- `rb-ocr/pipeline/models/dto.py` (data contracts)

Tasks:
- Add module-level docstrings summarizing responsibility and boundaries.
- Add function/class docstrings for public APIs describing:
  - Purpose
  - Parameters and types (where not obvious)
  - Returns (shape/contract)
  - Exceptions or error codes
- Inline comments only for non-obvious steps (e.g., timers, artifact keys, merge semantics).

Acceptance:
- Each file has a 3-6 line module docstring.
- Public functions/classes documented; no redundant inline commentary.

---

## Phase 2 — LLM/OCR processors and clients (0.5 day)
Scope:
- `pipeline/processors/` (agent_* , filter_* , merge_outputs.py, validator.py, fio_matching.py, image_to_pdf_converter.py, stamp_check.py)
- `pipeline/clients/` (llm_client.py, tesseract_async_client.py, textract_client.py)

Tasks:
- Docstrings for public functions, esp. I/O contracts and side effects (files written, env influence).
- Inline comments for:
  - Algorithms/heuristics (fio matching, filtering strategies)
  - Error mapping semantics (e.g., LLM_FILTER_PARSE_ERROR vs schema errors)
  - External calls and expected response shapes
- Mark WORKAROUNDs for SSL skip and hardcoded paths; suggest env-driven alternatives.

Acceptance:
- Every processor/client has clear input/output/contracts.
- Non-obvious logic has brief, high-signal commentary.

---

## Phase 3 — Utilities and shared helpers (0.25 day)
Scope:
- `pipeline/utils/` (io_utils.py, artifacts.py, timing.py)

Tasks:
- Docstrings for utility functions (what they guarantee, error behavior).
- Inline comments for subtle behaviors (e.g., manifest field semantics, timers accumulation, safe_filename rules).

Acceptance:
- Utilities are self-explanatory with minimal inline notes.

---

## Phase 4 — Prompts and domain knowledge (0.25 day)
Scope:
- `pipeline/prompts/` and the modules that consume them.

Tasks:
- Add brief README in `pipeline/prompts/` describing versioning, format expectations, and how processors load them.
- In processors, add comments clarifying prompt placeholders and stability requirements.

Acceptance:
- Prompt flow is discoverable and versioning intent is clear.

---

## Phase 5 — Documentation alignment and hygiene (0.25 day)
Tasks:
- Ensure CHANGES_INSPECTION.MD and related docs reference the commenting conventions.
- Remove any legacy comments that refer to removed modules or names (e.g., GPT-specific internals).
- Ensure comments do not duplicate documentation; link out when needed.

Acceptance:
- Comments and docs reflect the same conventions and terminology.

---

## Phase 6 — Review, verify, and stabilize (0.25-0.5 day)
Tasks:
- Run a focused review pass: comments vs code accuracy.
- Verify no sensitive data is exposed in comments.
- Ensure all TODOs include owner/issue or are converted to tickets.

Acceptance:
- No stale or misleading comments. Team sign-off.

---

## Execution plan (you can hand off parts)
- Work file-by-file in the order above; submit small PRs per phase.
- Keep diffs limited to comments/docstrings; avoid mixing refactors.
- For each PR, include a short checklist confirming:
  - Style adhered to
  - No public behavior changed
  - Comments add understanding and are up-to-date

---

## Example templates

Module docstring (top of file):
"""RB-OCR pipeline orchestrator.
Coordinates run directories, stage execution, timing, error handling,
and artifacts/manifest writing. Public entrypoint: `run_pipeline`.
"""

Function docstring (Google style):
"""Validate a run and optionally write validation.json.

Args:
  meta_path: Path to metadata.json.
  merged_path: Path to merged.json.
  output_dir: Destination directory for validation.json.
  filename: Output filename; defaults to VALIDATION_FILENAME.
  write_file: If True, write validation.json; else return only in-memory result.

Returns:
  Dict with keys: success, error, validation_path, result.

Raises:
  OSError: On IO failures when write_file is True.
"""

Inline comment (high-signal):
# LLM parse failure: map to LLM_FILTER_PARSE_ERROR (file read or filter failure)

---

## Handoff checklist for each part
- Scope listing (files)
- Commenting approach summary
- Concrete acceptance criteria
- Any risks (e.g., confusing domain logic) and open questions

When you’re ready, share the phase number and the target files; I’ll implement comments per this plan.
