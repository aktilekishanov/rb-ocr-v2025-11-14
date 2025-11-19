# Step-by-step Implementation Plan (main-dev only)

This plan implements the updated design from PROPOSAL.MD with your choices:
- Keep early exit on `single_doc_type=false` (Option B)
- Introduce `DOC_TYPE_UNKNOWN` error code
- `doc_type_known` = detected doc type is in the canonical Dictionary (not threshold-based)
- Keep best-guess `doc_type` string in merged even when `doc_type_known=false`
- Surface `doc_type_known` in `side_by_side.json`

Scope: Only under `apps/main-dev/rb-ocr`. No changes in `apps/main`.

---

## 0) Pre-flight
- Create a working branch (local) for `main-dev` changes. (ALREADY EXISTS)
- Prepare 2–3 fixture OCR JSONs for integration tests (single type, multiple types, unknown type).

---

## 1) agent_extractor.py — remove doc_type

### Prompt changes (mandatory)
Replace the output contract to remove `doc_type` entirely. Keep `fio`, `doc_date`, `valid_until` only.

- Remove any instruction that mentions `doc_type` extraction or validation.
- Keep the rule about `valid_until` extraction when the document states a period (e.g., «с … по …»); the validator will later decide whether to use it based on the merged `doc_type`.
- Output must be exactly this JSON (no markdown fences, no extra text):

```
{
  "fio": string | null,
  "doc_date": string | null,
  "valid_until": string | null
}
```

### Code changes
- Keep function name `extract_doc_data`.
- Update prompt string to the new schema.
- No code changes required in `gpt_client.py` or `filter_gpt_generic_response.py`.

---

## 2) agent_doc_type_checker.py — new richer schema

### Prompt changes (mandatory)
- Add the canonical Dictionary and instruct fuzzy/alias normalization against it.
- Output must be exactly this JSON:

```
{
  "detected_doc_types": [string],
  "single_doc_type": true | false,
  "confidence": 0-100,
  "reasoning": string,
  "doc_type_known": true | false
}
```

- Semantics:
  - `doc_type_known = true` only if the top candidate belongs to the Dictionary.
  - Keep a concise `reasoning` string (no markdown or extra explanations).
  - `confidence` is coarse and informational (do not derive `doc_type_known` from it).
  - If multiple canonical types occur → `single_doc_type=false` (Option B will early-exit in the pipeline).

- Include the full Dictionary in the prompt:
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

- Keep the algorithmic guidance (noise filtering, candidate title detection, canonical matching, normalization, distinct detection, issuer check, default safety).

### Code changes
- Keep function name `check_single_doc_type`.
- Update the prompt string accordingly.
- No changes to how the function returns (still raw string for filtering).

---

## 3) merge_outputs.py — compose the new merged.json

### Behavior changes
- Read extractor filtered JSON and checker filtered JSON.
- Build `merged` explicitly with the following keys:
  - From extractor: `fio`, `doc_date`, `valid_until`.
  - From checker: `single_doc_type`, `doc_type_known`.
  - Set `doc_type` = first element of `detected_doc_types` if present; else `null`.
  - If `stamp_check_response.json` exists (from orchestrator), merge `{ "stamp_present": bool }`.
- Do NOT include `detected_doc_types`, `confidence`, `reasoning` in `merged.json`.

### Code changes
- Replace the current blind `dict.update()` merge with selective key assembly.
- Keep function name and signature: `merge_extractor_and_doc_type(...)`.

---

## 4) validator.py — use doc_type_known instead of doc_type_match

### Checks
- Keep:
  - `fio_match` (deterministic + fuzzy fallback already in place)
  - `doc_date_valid` via `compute_valid_until(merged.doc_type, merged.doc_date, merged.valid_until)` and `is_within_validity`
  - `single_doc_type_valid` from `merged.single_doc_type`
  - `stamp_present` (gated by `STAMP_ENABLED`)
- Replace:
  - `doc_type_match` → `doc_type_known` (read boolean from merged)

### Verdict
- All must be true:
  - `fio_match` AND `doc_type_known` AND `doc_date_valid` AND `single_doc_type_valid` AND (`stamp_present` if enabled)

### Messages/diagnostics
- Update `VALIDATION_MESSAGES["checks"]` to replace the `doc_type_match` key with `doc_type_known` and suitable RU messages.
- Keep inputs and normalization info; keep `doc_type` string in diagnostics for transparency.

---

## 5) orchestrator.py — flow and schema updates

### Doc Type Checker step
- After filtering, parse:
  - `single_doc_type` (must be bool)
  - Capture path to filtered checker output for merge
- Early exit policy (Option B):
  - If `single_doc_type is False`, append `MULTIPLE_DOCUMENTS` error and return early (as currently implemented).
- No need to enforce `doc_type_known` here; let validator and final error mapping handle it.

### Extractor step
- Update schema validation for filtered extractor output:
  - Require only `fio` and `doc_date` keys (string or null).
  - `valid_until` remains optional (string or null) when present.
  - Remove any requirement for `doc_type`.

### Merge step
- No interface change; `merge_extractor_and_doc_type` now builds a curated `merged.json`.

### Side-by-side artifacts
- Continue to read `doc_type` from merged.
- Add a new field to `side_by_side.json`:
  - `doc_type_known: { "extracted": true|false|null }`
- Keep stamp_present behavior as-is.

### Post-validation error mapping
- Replace doc-type error handling with:
  - If `doc_type_known` is False → append `DOC_TYPE_UNKNOWN`.
  - If `doc_type_known` is None → also append `DOC_TYPE_UNKNOWN`.
- Keep existing mappings for FIO, doc_date, single_doc_type, and stamp.

---

## 6) core/errors.py — add DOC_TYPE_UNKNOWN

### Changes
- Add new error code:
  - Key: `DOC_TYPE_UNKNOWN`
  - RU message: `"Не удалось определить тип документа"` (or similar wording)
- Keep legacy `DOC_TYPE_MISMATCH`/`DOC_TYPE_MISSING` defined for now but no longer used by `main-dev`.

---

## 7) Tests (main-dev)
### Integration tests
 - Single known type → `doc_type_known=true`, `single_doc_type=true`, fresh `doc_date` → verdict true.
 - Multiple types → early exit with `MULTIPLE_DOCUMENTS`.
 - Unknown type → `doc_type_known=false`, best-guess string present in `doc_type`, verdict false, error `DOC_TYPE_UNKNOWN`.
- Stamp-enabled path (if env on) → stamp Present/Absent scenarios.

---

## 8) Documentation
- Update or append to `apps/PROPOSAL.MD` status section once implemented.
- Update a short `CHANGELOG`/README under `apps/main-dev/rb-ocr`:
  - Extractor no longer outputs `doc_type`.
  - Merged schema changed; validator now uses `doc_type_known`.
  - Early exit policy retained for multiple document types.

---

## 9) Execution order (recommended)
1. Update prompts in both agents (sections 1 and 2) and adjust extractor schema checks in orchestrator.
2. Implement curated merge (section 3).
3. Implement validator changes (section 4).
4. Adjust orchestrator error mapping and side-by-side (section 5).
5. Add `DOC_TYPE_UNKNOWN` to errors (section 6).
6. Update tests (section 7) and docs (section 8).

---

## 10) Post-implementation verification
- Run the pipeline on 3 fixtures (known type, multiple types, unknown type).
- Verify `merged.json` shape and values.
- Verify `validation` result (when write_file=false) and final `final_result.json` verdict/errors.
- Confirm `side_by_side.json` includes `doc_type_known` and correct `doc_type`/validity timeline.
