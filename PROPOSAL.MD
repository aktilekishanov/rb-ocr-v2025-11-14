# Proposal: Pipeline and GPT processors redesign (main-dev only)

## Summary
- **Goal**: Move `doc_type` determination fully into the Doc Type Checker agent; simplify the Extractor to only produce `fio`, `doc_date`, `valid_until`; update merge, validator, and orchestrator accordingly.
- **Scope**: Only `apps/main-dev/rb-ocr` code. No changes to `apps/main`.
- **Key outcomes**:
  - Extractor no longer emits `doc_type`.
  - Doc Type Checker emits richer contract: `detected_doc_types`, `single_doc_type`, `confidence`, `reasoning`, `doc_type_known`.
  - `merged.json` becomes the single source for `doc_type`, taken from the checker.
  - Validator uses `doc_type_known` instead of `doc_type_match`.

## Evaluation of the idea
- **Pros**
  - **Separation of concerns**: classification in one place; extraction simplified → easier to prompt/tune each task.
  - **Explainability**: reasoning, confidence, and candidates from the checker enable better diagnostics and later UI.
  - **Consistency**: single authoritative `doc_type` in merge; fewer cross-agent disagreements.
- **Cons/Risks**
  - **Back-compat**: Any consumer expecting `doc_type` from extractor or a `doc_type_match` check must be adapted.
  - **Validity policy coupling**: `compute_valid_until` depends on `doc_type`; now it will rely on checker’s `doc_type` instead of extractor’s (should be fine, but worth testing edge cases).

## Proposed design

### 1) Extractor agent (agent_extractor.py)
- **Prompt/schema change**:
  - Remove `doc_type` entirely from output.
  - Keep fields: `fio`, `doc_date`, `valid_until`.
  - Keep the current logic for `valid_until` extraction (explicit end date like “с … по …”). The downstream validity policy will decide whether to use it based on `doc_type`.
- **Output JSON**:
  ```json
  {
    "fio": string | null,
    "doc_date": string | null,
    "valid_until": string | null
  }
  ```
- **Other**: No changes to `filter_gpt_generic_response` or `gpt_client` required.

### 2) Doc Type Checker agent (agent_doc_type_checker.py)
- **Prompt/schema change** to output:
  ```json
  {
    "detected_doc_types": [string],
    "single_doc_type": true | false,
    "confidence": 0-100,
    "reasoning": string,
    "doc_type_known": true | false
  }
  ```
- **Semantics**:
  - `detected_doc_types`: canonicalized titles (best-first). If none → empty array.
  - `single_doc_type`: whether the file contains exactly one document type.
  - `doc_type_known`: whether the detected doc type is on the list Dictionary (true) vs unknown/ambiguous (false).
  - `confidence`: coarse confidence in the top candidate (for diagnostics/thresholding later).
  - `reasoning`: concise rationale for audit/debug.


### 2.1) Dictionary

1. Лист временной нетрудоспособности (больничный лист)
2. Приказ о выходе в декретный отпуск по уходу за ребенком
3. Справка о выходе в декретный отпуск по уходу за ребенком
4. Выписка из стационара (выписной эпикриз)
5. Больничный лист на сопровождающего (если предусмотрено)
6. Заключение врачебно-консультативной комиссии (ВКК)
7. Справка об инвалидности
8. Справка о степени утраты общей трудоспособности
9. Приказ о расторжении трудового договора
10. Справка о расторжении трудового договора
11. Справка о регистрации в качестве безработного
12. Приказ работодателя о предоставлении отпуска без сохранения заработной платы
13. Справка о неполучении доходов
14. Уведомление о регистрации в качестве лица, ищущего работу
15. Лица, зарегистрированные в качестве безработных


### 3) Merge (merge_outputs.py) and merged.json
- **Merge rule**:
  - Start with extractor fields (`fio`, `doc_date`, `valid_until`).
  - Append checker fields: `single_doc_type`, `doc_type_known`.
  - Add `doc_type` = `detected_doc_types[0]` if present, else `null`.
  - Preserve optional `stamp_present` if a detector wrote it.
- **Resulting merged.json**:
  ```json
  {
    "fio": string | null,
    "doc_date": string | null,
    "valid_until": string | null,
    "single_doc_type": true | false,
    "doc_type": string | null,
    "doc_type_known": true | false
  }
  ```

### 4) Validator (validators.py)
- **Replace** `doc_type_match` with `doc_type_known`.
- **Checks** produced:
  - `fio_match`: as-is (deterministic matcher + fuzzy fallback).
  - `doc_type_known`: boolean (from merged).
  - `doc_date_valid`: as-is (`compute_valid_until(doc_type, doc_date, valid_until)` + `is_within_validity`).
  - `single_doc_type_valid`: as-is (must be true if provided false → invalid).
  - `stamp_present`: unchanged, gated by `STAMP_ENABLED`.
- **Verdict** (must all be true):
  - `fio_match` AND `doc_type_known` AND `doc_date_valid` AND `single_doc_type_valid` AND (`stamp_present` if enabled).
- **Errors mapping** adjustments:
  - When `doc_type_known` is false or None → add `DOC_TYPE_UNKNOWN`.
  - Remove usage of `DOC_TYPE_MISMATCH`.
- **Messages**: Update `VALIDATION_MESSAGES["checks"]` accordingly (rename key to `doc_type_known`).

### 5) Orchestrator (orchestrator.py)
- **Doc Type Checker step**:
  - Parse new keys from filtered checker output (including `doc_type_known`).
  - Option A (recommended): do NOT early-return when `single_doc_type` is false; let validator produce the final verdict and error list. This centralizes business rules and side-by-side building.
  - Option B: keep existing early exit on `single_doc_type` false (producing `MULTIPLE_DOCUMENTS`) if you want a faster fail-path. Validator remains simpler but will be bypassed in that branch. (I CHOOSE OPTION B FOR NOW)
- **Extractor step schema check**:
  - Remove requirement for `doc_type` key; require only `fio`, `doc_date`; optional `valid_until` type check stays.
- **Side-by-side meta**:
  - `doc_type.extracted` should now come from merged (which comes from checker), not extractor (already uses merged → OK).
  - Add `doc_type_known` under a new `doc_type_known` section if we want visibility.
  - `valid_until` display stays; effective valid-until is still computed from merged.

### 6) Config and errors
- No filename changes in `core/config.py`.
- In `core/errors.py`:
  - Optionally deprecate `DOC_TYPE_MISMATCH`.
  - Reuse `DOC_TYPE_MISSING` for unknown/ambiguous doc type, or introduce `DOC_TYPE_UNKNOWN` with a suitable RU message. (I CHOOSE TO INTRODUCE DOC_TYPE_UNKNOWN)

### 7) Tests (main-dev only)
- Update/add tests under `apps/main-dev/rb-ocr/tests`:
  - **Extractor contract**: ensure `doc_type` is absent; verify `fio`, `doc_date`, `valid_until` parsing.
  - **Checker contract**: ensure schema and type correctness; cases with empty `detected_doc_types`, low confidence, `single_doc_type=false`.
  - **Merge**: confirm merged.json matches the new shape; `doc_type` taken from checker; `doc_type_known` plumbed.
  - **Validator**: scenarios for `doc_type_known=false`, `single_doc_type=false`, fresh/expired `doc_date`, FIO mismatch; verdict logic.
  - **Orchestrator integration**: end-to-end with mocked GPT/ocr to assert artifacts and final verdict/errors.

## Open questions
- **Early exit on multiple documents?** Keep existing early failure (Option B) or centralize decision in validator (Option A). Default suggestion: Option A (no early exit) for uniform result artifacts.
user's answer: I choose Option B

- **When `doc_type_known=false` but `detected_doc_types` contains a best-guess**:
  - Should `merged.doc_type` still carry the guess (as text) or be forced to `null`? Suggest: keep the best-guess string for observability; verdict still fails via `doc_type_known=false`.
user's answer: I choose to keep the best-guess string for observability

- **Confidence threshold**: Do we want to derive `doc_type_known` internally via threshold (e.g., ≥75) or let the agent set it explicitly? Suggest: let the agent set `doc_type_known`; we can log confidence for future tuning.
user's answer: I choose to let the agent set `doc_type_known`

- **UI/Manifest**: Do we want `doc_type_known` surfaced in `side_by_side.json` for debugging?
user's answer: I choose to surface `doc_type_known` in `side_by_side.json` for debugging

## Implementation plan (no code changes yet)
- **[Extractor]** Update prompt and schema; remove `doc_type`. Adjust orchestrator schema checks. (todo-extractor-002)
- **[Doc Type Checker]** Update prompt to new schema. (todo-dtc-003)
- **[Merge]** Compose `merged.json` from extractor + checker per schema; include `doc_type`, `doc_type_known`, `single_doc_type`. (todo-merge-004)
- **[Validator]** Replace `doc_type_match` with `doc_type_known` in checks, messages, errors, verdict. (todo-validator-005)
- **[Orchestrator]** Parse new checker keys; keep option B on `single_doc_type=false`; update side-by-side. (todo-orchestrator-006)
- **[Tests]** Update/add unit/integration tests aligned to new contracts. (todo-tests-007)
- **[Docs]** Update README/CHANGELOG in main-dev to reflect new flows. (todo-docs-008)

## Acceptance criteria
- End-to-end run produces `merged.json` with the new fields and shapes.
- `validator` returns `checks` containing `doc_type_known` (no `doc_type_match`).
- `verdict` is true only if `fio_match`, `doc_type_known`, `doc_date_valid`, and `single_doc_type_valid` are all true (and `stamp_present` when enabled).
- No references to extractor `doc_type` remain; all code paths build `doc_type` from the checker output.
- All updated tests pass in `apps/main-dev`.
