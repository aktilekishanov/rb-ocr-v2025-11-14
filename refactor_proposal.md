# Refactor Proposal — main-dev (RB-OCR IDP)

## Executive Summary
- **Goal**: Improve code quality, maintainability, testability, and deployment safety.
- **Approach**: Incremental refactor across architecture, configuration, data modeling, prompts, testing, and DevEx.
- **As-Is Score**: 6.5 / 10
- **To-Be Score**: 9.0 / 10

---

## How the system works (current)
- **UI (Streamlit)**: `main-dev/rb-ocr/app.py`
  - Collects `fio`, `reason`, `doc_type`, accepts file upload, displays verdict and diagnostics.
- **Orchestrator**: `rbidp/orchestrator.py`
  - End-to-end pipeline: save input → OCR → filter pages → GPT doc-type checker → GPT extractor → merge → validity → validation → outputs (final_result, side_by_side, manifest).
  - Heavy function `run_pipeline(...)` orchestrates I/O, timers, error handling, and artifact emission.
- **Clients**:
  - `clients/tesseract_async_client.py`: async HTTP client for OCR service, plus sync wrapper.
  - `clients/gpt_client.py`: calls internal GPT endpoint.
- **Processors**:
  - `agent_doc_type_checker.py`: GPT prompt to classify canonical doc type(s).
  - `agent_extractor.py`: GPT prompt to extract `fio` and `doc_date` (decree RU/KZ period fallback by LLM).
  - `merge_outputs.py`: curates merged.json keys.
  - `validator.py`: validity policy + checks, yields diagnostics.
  - `filter_*`: normalize provider responses.
- **Core**:
  - `core/validity.py`: policies, compute validity, fixed windows.
  - `core/config.py`: filenames, limits, toggles.
  - `core/dates.py`: date parsing.
  - `core/errors.py`: error codes/messages.

---

## Key Findings (as-is)
- **Orchestrator monolith (large function)**
  - `run_pipeline` is ~700+ LOC with repeated error-handling/manifest writing blocks, mixing concerns (I/O, timing, validation, presentation) → hard to test and evolve.
- **Ad-hoc data contracts**
  - JSON dicts passed across stages without strict schemas; many manual type checks (`if not isinstance(...): raise`), risk of drift.
- **Configuration gaps**
  - Hardcoded endpoints and behavior (e.g., GPT URL in `gpt_client.py`, CSS/UI constants, reasons_map in app.py). Few env toggles beyond `STAMP_ENABLED`.
- **Security/Networking**
  - `gpt_client.py` disables SSL verification via `_create_unverified_context()`.
- **Prompt management**
  - Prompts are embedded as large triple-quoted strings in code; no versioning or tests; hard to diff.
- **Error handling duplication**
  - Many try/except blocks with near-identical result/manifest writing logic.
- **Artifacts/I-O heavy by default**
  - Frequent read/write of intermediate JSONs; suitable for debugging, but slow for prod.
- **Validation/diagnostics coupling**
  - `validator.py` mixes business rules and presentation-friendly diagnostics.
- **Minimal test coverage**
  - Only `tests/test_fio_matching.py` present; critical flows (validity, prompts, orchestrator) lack tests.
- **Inconsistent naming and checkpoints**
  - “CHECKPOINT … RESTORE IF CRASHES” comments and historical code blocks left in files; reduces clarity.
- **Internationalization**
  - RU strings sprinkled in code; not centralized; partial KZ handling in prompts only.

---

## Refactor Plan (phased)

### Phase 0 — Hygiene and DevEx
- **Formatting & linting**: Adopt Black, Ruff, isort; add pre-commit.
- **Typing**: Enable mypy (strict on core and processors gradually).
- **Project metadata**: Add `pyproject.toml`, define entry points, lock versions.
- **CI hooks**: Lint + type-check + unit tests on PR.

### Phase 1 — Architecture and Orchestrator
- **Split `run_pipeline` into stages** with a typed `PipelineContext`:
  - acquire → ocr → filter_pages → doc_type_check → extract → merge → validate → render_outputs.
- **Shared utilities**
  - `io_utils.py`: read/write json, safe file ops.
  - `timing.py`: context manager for stage timers to avoid duplicated timing code.
  - `artifacts.py`: builder for manifest/side_by_side/final_result.
- **Error handling**
  - Centralize `fail_and_finalize(code, details, context)` to eliminate repetition.

### Phase 2 — Data Modeling and Validation
- **Pydantic models (or dataclasses + validation)** for:
  - OCR pages, DocTypeCheck result, Extractor result, Merged, Validation result, SideBySide, Manifest.
- **Schema contracts**
  - Fail early with clear messages; simplify downstream checks.

### Phase 3 — Configuration & Security
- **Config**
  - Move all endpoints, feature toggles, and limits to env-driven `Settings` (pydantic-settings or dynaconf).
  - Reasons/doc-type mapping loaded from JSON/YAML config for UI.
- **Security**
  - Restore SSL verification by default; allow toggle only in dev via env.
  - Add timeouts/retries/backoff for external calls.

### Phase 4 — Prompts & NLP Layer
- **Prompt templates**
  - Store prompts under `rbidp/prompts/` with version tags.
  - Keep tests with representative texts; snapshot expected JSON shapes.
- **Adapters**
  - Abstract GPT provider: allow local mock, different endpoints, streaming.

### Phase 5 — Testing Strategy
- **Unit tests**
  - Validity policies, date parsing edge cases, doc-type canonicalization, extractor fallback rules.
- **Integration tests**
  - Orchestrator happy paths and error paths (mock OCR/GPT).
- **Golden files**
  - Sample inputs → expected merged/validation/side_by_side outputs.

### Phase 6 — Observability & Ops
- **Structured logging** with context (run_id, stage, duration, status).
- **Metrics** for stage durations, error counts, GPT/OCR latencies.
- **Feature flags** to reduce artifact I/O in prod (keep in dev/QA).

---

## Concrete Recommendations
- **Break up orchestrator**: pure functions per stage; return typed results; one place to persist artifacts.
- **Introduce models**: `DocTypeCheck`, `ExtractorOut`, `Merged`, `ValidationDiagnostics`, `SideBySide`, `Manifest`.
- **Centralize strings**: move RU messages to `core/messages_ru.py`; expose message_for via mapping.
- **Normalize canonical doc types**: enum in `core/doc_types.py`, decouple alias normalization rules from prompt text.
- **Improve `gpt_client`**: configurable base URL, verified SSL; common request wrapper with retries.
- **Prompts**: externalize, version, and test; build minimal Jinja templates for readability.
- **Dates**: extend `parse_doc_date` with month-name patterns if needed (today it’s strict dd.mm.yyyy/iso/slash); keep LLM fallback for decree as designed.
- **UI**: move `reasons_map` to config; add “Other” reason/doc type via configuration, not hardcode.
- **Artifacts**: guard heavy disk I/O behind `ARTIFACTS_ENABLED` env; always keep final_result/manifest.

---

## Risks and Mitigations
- **Behavior drift**: Add unit tests before refactor; snapshot prompts and sample outputs.
- **Integration breakage**: Keep stage-by-stage feature flags, ship behind toggles.
- **Performance**: Reduce file I/O in prod; keep debug artifacts in dev.

---

## Acceptance Criteria
- Orchestrator split into composable, tested stages with typed inputs/outputs.
- Pydantic models validate cross-stage contracts.
- Prompts externalized and versioned.
- Configured endpoints and toggles via env; SSL verify on.
- CI with lint, type-check, tests; baseline coverage on core/validators.

---

## Scoring
- **As-Is (6.5/10)**
  - Strengths: Clear pipeline, artifacts for debugging, minimal but consistent config, working MVP.
  - Weaknesses: Large orchestrator, ad-hoc schemas, hardcoded endpoints/strings, prompt sprawl, low tests, duplicated error/manifest logic.
- **To-Be (9.0/10)**
  - Typed contracts, modular stages, secure/configurable clients, externalized prompts, robust tests and CI, better logs/metrics, cleaner UI config.

---

## Refactor Roadmap (timebox)
- Week 1: Phase 0–1 (hygiene; split orchestrator; shared utils; no behavior change).
- Week 2: Phase 2–3 (models + config + secure clients; limited surface) + unit tests.
- Week 3: Phase 4–5 (prompts externalized; integration tests) + observability hooks.
- Week 4: Hardening and documentation.
