# PROPOSAL-2 — Change validity policy for “Приказ о выходе в декретный отпуск по уходу за ребенком”

- **Scope**: main-dev only
- **Goal**: Make validity window for the decree order equal to other doc types: use `doc_date` (issue date). If issuance date cannot be extracted, fall back to the start date from a “период с … до/по …” fragment. Compute validity as `doc_date + 365 days`.

## Current behavior (as of main-dev)
- **Policy engine**: `rbidp/core/validity.py`
  - `DOC_DECREE_ORDER = "Приказ о выходе в декретный отпуск по уходу за ребенком"` is configured with policy `"explicit_end_date"`.
  - This makes the system rely on an extracted `valid_until` date for this doc type.
- **Extractor prompt**: `rbidp/processors/agent_extractor.py`
  - Instructs the LLM to extract `valid_until` only for the decree order (end date of a stated period), and `null` for others.
- **Pipeline**:
  - `merge_outputs.py` merges {fio, doc_date, valid_until, …}.
  - `orchestrator.py` calls `compute_valid_until(doc_type, doc_date, valid_until)` and formats the result for side-by-side output.
  - `validator.validate_run` recomputes validity via `compute_valid_until(...)` and checks `is_within_validity(now <= valid_until)`.

## Requested change
- For decree documents (both: «Приказ …» и «Справка …» о выходе в декретный отпуск по уходу за ребенком), compute validity like other fixed-window documents: `valid_until = doc_date + 365 days`.
- `doc_date` should be the issuance date; if it cannot be found, use the start date from a “период с … по/до …” (RU) or “… бастап … дейін” (KZ) clause.
- Do not rely on extracting/using an explicit end date for decree docs anymore.

## Proposed solution
- **Policy**
  - Set both decree canonical types to `fixed_days` with `days = 365` in `rbidp/core/validity.py`:
    - «Приказ о выходе в декретный отпуск по уходу за ребенком»
    - «Справка о выходе в декретный отпуск по уходу за ребенком»
  - Remove the `explicit_end_date` override for decree docs (deprecated usage).
- **Extraction**
  - Update `rbidp/processors/agent_extractor.py` prompt:
    - Keep output keys unchanged: `fio`, `doc_date`, `valid_until`.
    - For all doc types, set `valid_until` strictly to `null` (Option A decision).
    - For both decree types, if issuance date is not present, parse a period expression and set `doc_date` to the start date:
      - Russian: patterns like “с DD.MM.YYYY … по DD.MM.YYYY” or “с DD.MM.YYYY … до DD.MM.YYYY”.
      - Kazakh (if present): patterns like “DD.MM.YYYY бастап … DD.MM.YYYY дейін”.
    - Continue to output `doc_date` in `DD.MM.YYYY`.
- **Pipeline impact**
  - Option A confirmed: keep `valid_until` field in the schema, always `null` from extractor; consumers should rely on policy-computed validity only.
  - `merge_outputs.py` remains compatible (it already accepts `valid_until: null`).
  - `orchestrator.py` and `validator.py` already use the policy engine. With the new `fixed_days=365`, they’ll compute validity from `doc_date` for both decree types.
  - No other changes required unless downstream logic depends on non-null `valid_until` from extractor (none found in main-dev).

## Edge cases and clarifications
- **Leap years**: Use `timedelta(days=365)` (not calendar add-one-year). Example: 01.01.2024 + 365 days = 31.12.2024.
- **Fallback trigger**: Fallback to period start date only when issuance date cannot be extracted. If both exist, prefer issuance date.
- **Period connectors**: Confirmed. Handle both RU (“с … по …”, “с … до …”) and KZ (“… бастап … дейін”) variants.
- **Scope of decree docs**: Applies to both canonical types: приказ и справка о выходе в декретный отпуск по уходу за ребенком.
- **Missing both issuance and period**: If neither can be parsed, `doc_date` remains `null` and the policy will not compute a window; validation returns `doc_date_valid = None` (unchanged behavior).

## Implementation plan (no code changes in this proposal)
- **Step 1 — Policy**
  - Edit `rbidp/core/validity.py` → in `VALIDITY_OVERRIDES`, replace decree order policy with `{"type": "fixed_days", "days": 365}`.
- **Step 2 — Extractor prompt**
  - Edit `rbidp/processors/agent_extractor.py` prompt:
    - Remove instruction to extract `valid_until` for decree order; mandate `valid_until: null` for all types.
    - Add explicit decree-order fallback rule for `doc_date` from period start (with Russian and Kazakh variants).
- **Step 3 — Sanity checks**
  - Verify `orchestrator.py` side-by-side output shows computed `valid_until` (policy-based) as before.
  - Verify `validator.py` diagnostics now show `policy_type = fixed_days` and `validity_window_days = 365` for decree orders.

## Acceptance criteria
- For decree documents (приказ и справка) with detectable issuance date, `valid_until` equals `doc_date + 365 days`.
- If issuance date absent and a period clause exists, `doc_date` equals the start date of the period and `valid_until = start + 365 days`.
- `valid_until` is no longer extracted by the LLM (always `null` in raw extractor output), but the pipeline’s computed `valid_until` is present and correct.
- Validator reports `policy_type = fixed_days` and `validity_window_days = 365` for decree documents.

## Open questions
None at this time (Option A confirmed; 365 days confirmed; RU/KZ connectors confirmed; scope = both decree types).

## Estimated effort
- Code + prompt updates: ~0.5–1 engineer-hour.

## Rollout & risk
- Low risk. If something goes wrong, revert the single-policy change and restore the prompt instruction for decree `valid_until` extraction.
