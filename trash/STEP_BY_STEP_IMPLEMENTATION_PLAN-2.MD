# STEP-BY-STEP IMPLEMENTATION PLAN — Decree Docs Validity (Option A)

This plan implements PROPOSAL-2 (Option A):
- Apply fixed validity window of 365 days for both decree types (приказ и справка).
- Keep `valid_until` in schema but always set it to null in extractor output.
- Add LLM-prompt fallback: if issuance date is missing, set `doc_date` to the start date extracted from a RU/KZ period clause.

## 1) Update policy engine (validity)
- File: `apps/main-dev/rb-ocr/rbidp/core/validity.py`
- Changes:
  - Add/confirm canonical constants (already present for the decree order). Ensure constant for the decree certificate exists or add it if missing.
  - In `VALIDITY_OVERRIDES`, set both decree types to `{"type": "fixed_days", "days": 365}`.
  - Remove/deprecate any `explicit_end_date` override for these types.
- No signature changes to `compute_valid_until`; it will ignore `valid_until` for all types under Option A.

## 2) Update extraction prompt (LLM) — IMPORTANT
- File: `apps/main-dev/rb-ocr/rbidp/processors/agent_extractor.py`
- Edits to `PROMPT` string:
  - Keep final JSON keys: `fio`, `doc_date`, `valid_until`.
  - Add rule: "For all document types, set `valid_until` strictly to `null`."
  - Add decree-specific fallback rule (apply to both canonical types):
    - If issuance date cannot be extracted, parse a period clause and set `doc_date` to the start date.
    - Russian variants to recognize: "с DD.MM.YYYY … по DD.MM.YYYY", "с DD.MM.YYYY … до DD.MM.YYYY".
    - Kazakh variants to recognize: "DD.MM.YYYY бастап … DD.MM.YYYY дейін".
  - Keep formatting rule: `doc_date` must be `DD.MM.YYYY`.
  - Remove any text that tells the LLM to extract `valid_until` for decree documents.

Suggested insertion into PROMPT (under STEP 2 — EXTRACTION RULES):

- Decree types (apply to both canonical forms — приказ и справка):
  - If the issuance date cannot be found, parse a period clause and set `doc_date` to the start date.
  - Recognize the following connectors:
    - RU: "с DD.MM.YYYY … по DD.MM.YYYY", "с DD.MM.YYYY … до DD.MM.YYYY"
    - KZ: "DD.MM.YYYY бастап … DD.MM.YYYY дейін"
  - Always output `valid_until: null`.

## 3) Merge behavior
- File: `apps/main-dev/rb-ocr/rbidp/processors/merge_outputs.py`
- No changes required (it already accepts `valid_until: null`).

## 4) Orchestrator — side-by-side
- File: `apps/main-dev/rb-ocr/rbidp/orchestrator.py`
- No functional changes required. It calls `compute_valid_until(doc_type, doc_date, valid_until)`. With the new policy, `valid_until` is computed from `doc_date` as 365 days for the decree types.
- Verify formatting via `format_date(...)` is unchanged.

## 5) Validator — diagnostics
- File: `apps/main-dev/rb-ocr/rbidp/processors/validator.py`
- No changes required to interfaces. Expect diagnostics to show:
  - `policy_type = fixed_days`
  - `validity_window_days = 365` for both decree types.

## 6) Doc type checker (for scope)
- File: `apps/main-dev/rb-ocr/rbidp/processors/agent_doc_type_checker.py`
- No structural changes. Ensure the canonical list includes both types already (they are present at indices 2 and 3 as приказ and справка).

## 7) Smoke checks after implementation
- Run a couple of decree samples:
  - With an issuance date → expect computed `valid_until = issuance + 365 days`.
  - Without issuance date but with a period → LLM sets `doc_date` to start date; expect `valid_until = start + 365 days`.
- Confirm `merged.json` keeps `valid_until: null` but `validation.json` shows policy-computed `effective_valid_until`.

## 8) Out-of-scope (for later cleanup, not in this change)
- If desired later, perform Option B cleanup: remove `valid_until` from schema and delete the `explicit_end_date` branch in `compute_valid_until`, adjusting all call sites.
