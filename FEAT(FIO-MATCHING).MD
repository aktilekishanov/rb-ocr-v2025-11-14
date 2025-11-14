# FEAT(FIO-MATCHING): Deterministic FIO matching by patterns

## Summary
Implement a precise, deterministic matching for applicant FIO vs extracted FIO. The match becomes True if any ONE of the following exact (canonicalized) pairs match:
- Фамилия Имя Отчество vs Фамилия Имя Отчество
- Фамилия Имя vs Фамилия Имя
- Имя Отчество vs Имя Отчество
- Фамилия И. О. vs Фамилия И. О.

The current validator uses fuzzy matching (`rapidfuzz.token_sort_ratio >= 90`) on normalized strings. We will replace the decision rule with the deterministic pattern-matching above, while optionally keeping fuzzy as a guarded fallback (feature flag) for safety during rollout.

## Current state (as of DEV)
- File: `apps/main-dev/rb-ocr/rbidp/processors/validator.py`
  - Normalizes FIO with `_norm_text` → `kz_to_ru` → `latin_to_cyrillic`.
  - Computes `fio_match` using `fuzz.token_sort_ratio(fio_meta_norm, fio_norm) >= 90`.
  - `fio_match` is one of the 5 mandatory checks gating `verdict`.

## Design overview
- Create a small, focused FIO module that:
  1) Normalizes inputs using the same pipeline as validator (whitespace, casefold, KZ→RU, Latin→Cyrillic).
  2) Parses FIO into parts: last name, first name, patronymic (all optional, robust to hyphens and extra spaces).
  3) Builds canonical variants for four formats:
     - FULL: `Фамилия Имя Отчество`
     - LF: `Фамилия Имя`
     - FP: `Имя Отчество`
     - L_IO: `Фамилия И. О.` (initials; dots optional in compare)
  4) Compares equal-typed variants between application and document. If any pair matches, `fio_match=True`.
  5) Optionally: apply fuzzy fallback behind a feature flag if no deterministic match.

## Module and API
- New module: `apps/main-dev/rb-ocr/rbidp/processors/fio_matching.py`
- Public API:
  ```python
  from dataclasses import dataclass
  from typing import Optional, Dict

  @dataclass
  class NameParts:
      last: Optional[str]
      first: Optional[str]
      patro: Optional[str]

  def normalize_for_name(s: str) -> str: ...  # whitespace collapse, casefold, kz_to_ru, latin_to_cyrillic

  def parse_fio(s: str) -> NameParts: ...     # robust split, handle hyphens, ignore extra punctuation

  def build_variants(p: NameParts) -> Dict[str, str]:
      """
      Returns canonical strings per variant key among {"FULL", "LF", "FP", "L_IO"} if viable.
      - FULL: "{last} {first} {patro}"
      - LF: "{last} {first}"
      - FP: "{first} {patro}"
      - L_IO: "{last} {F.} {P.}" (allow compare ignoring dots)
      """

  def equals_canonical(a: str, b: str) -> bool: ...  # single-space, casefold, unify punctuation rules

  def fio_match(app_fio: str, doc_fio: str, *, enable_fuzzy_fallback: bool = False, fuzzy_threshold: int = 90) -> tuple[bool, dict]:
      """
      Returns (match_bool, diagnostics_dict)
      - Try FULL↔FULL, LF↔LF, FP↔FP, L_IO↔L_IO (in this order).
      - If none match and enable_fuzzy_fallback=True, evaluate fuzzy as last resort.
      - Diagnostics include matched_variant, compared_values, and any fuzzy score.
      """
  ```

Notes:
- For initials compare, treat `И.О.`, `И. О.`, `ИО`, `И О` as equivalent (ignore dots/spaces between initials when comparing).
- Keep hyphens as-is inside tokens (e.g., `Петров-Сидоров`).

## Project-wide changes
- **Add**: `rbidp/processors/fio_matching.py` (new module; pure functions + dataclass)
- **Refactor (minimal)** in `rbidp/processors/validator.py`:
  - Replace direct fuzzy decision with call to `fio_match(...)`.
  - Keep `score_before/score_after` diagnostics for transparency but do not gate `fio_match` on them.
  - Add diagnostics fields: `fio_matched_variant`, `fio_meta_variant_value`, `fio_doc_variant_value`, `fio_fuzzy_score` (if fallback used).
- **Config (optional)** in `rbidp/core/config.py`:
  - `FIO_ENABLE_FUZZY_FALLBACK: bool = False`
  - `FIO_FUZZY_THRESHOLD: int = 90`
  - If you prefer no code config change, pass flags from validator as constants.
- **Tests**: `apps/main-dev/rb-ocr/tests/test_fio_matching.py` covering all variants, transliteration, hyphens, and punctuation.

## Implementation steps
1) Create `fio_matching.py`
   - Implement `normalize_for_name`, reusing logic from validator: `_norm_text`, `kz_to_ru`, `latin_to_cyrillic`.
     - Best practice: do not duplicate logic; import existing helpers from `validator.py` for now, or (optionally) extract them to a shared `rbidp/core/text.py` if you plan broader reuse. Keep this refactor minimal in first iteration.
   - Implement `parse_fio`:
     - Remove extraneous punctuation except hyphens.
     - Split by spaces; map 1..N tokens to parts heuristically:
       - 3+ tokens: take first three as `last, first, patro` (conservative); store extras in diagnostics.
       - 2 tokens: `last, first` and `patro=None`.
       - 1 token or empty: insufficient; only initials variant may be derivable.
     - Detect and strip trailing dots in initials candidates.
   - Implement `build_variants`:
     - Produce strings with single spaces, casefolded.
     - For `L_IO`, derive first-letter initials for `first` and `patro` if both exist; representation: `"{last} {F}{sep}{P}"` with `sep` canonicalized (store canonical without dots; accept dotted forms during equals).
   - Implement `equals_canonical` and `fio_match` according to API above.

2) Update `validator.py`
   - Import and call `fio_match`:
     ```python
     from rbidp.processors.fio_matching import fio_match

     # inside validate_run(...)
     fio_match_bool, fio_diag = fio_match(
         fio_meta_raw, fio_raw,
         enable_fuzzy_fallback=FIO_ENABLE_FUZZY_FALLBACK,
         fuzzy_threshold=FIO_FUZZY_THRESHOLD,
     )
     fio_match = fio_match_bool
     ```
   - Extend `diagnostics` to include `fio_diag` fields.
   - Keep the rest of checks unchanged.

3) Add unit tests
   - `tests/test_fio_matching.py`:
     - FULL↔FULL: `"Иванов Иван Иванович"` vs `"Иванов Иван Иванович"` → True
     - LF↔LF: `"Иванов Иван"` vs `"Иванов Иван"` → True
     - FP↔FP: `"Иван Иванович"` vs `"Иван Иванович"` → True
     - L_IO↔L_IO: `"Иванов И. И."` vs `"Иванов И.И."` → True
     - Dots/spaces variants: `"Иванов И О"` vs `"Иванов И.О."` → True
     - Hyphen last names: `"Петров-Сидоров Иван Иванович"` → match across variants
     - Cyrillic/Latin/kz: `"Иванов"` typed with Latin lookalikes → normalize to match
     - Negative cases: mismatched last/first/patro should be False if deterministic variants don’t match
     - Optional: fuzzy fallback test if flag enabled

4) Documentation
   - Update `PROJECT_DESCRIPTION.MD` (optional) to note deterministic FIO matching.
   - Keep `DEPLOYMENT_GUIDE.MD` unchanged.

5) Rollout
   - Local DEV: run Streamlit, test new cases in UI (side_by_side + diagnostics show matched variant).
   - Server [DEV]: deploy and smoke-test; toggle fallback flag as needed.
   - Observe error rates; if stable, deploy to [PROD].

## Matching rules (canonicalization details)
- Case-insensitive, whitespace-collapsed.
- KZ→RU substitutions then Latin→Cyrillic lookalikes.
- Hyphens preserved within tokens.
- Initials comparison ignores dots and internal spaces between initials.
- For `LF`/`FP`/`FULL`, comparison is exact equality of canonical strings.

## Diagnostics (added fields)
- `fio_matched_variant`: one of `FULL`, `LF`, `FP`, `L_IO`, or `None`.
- `fio_meta_variant_value`, `fio_doc_variant_value`: the two canonical strings that matched (when matched).
- `fio_fuzzy_score`: present only if fallback was used.
- `fio_parse`: serialized `NameParts` for meta and doc for debugging.

## Risk and mitigation
- Risk: deterministic equality may reduce tolerance to OCR noise.
  - Mitigation: feature-flagged fuzzy fallback; keep internal diagnostics for monitoring.
- Risk: ambiguous multi-token names (e.g., 4 tokens).
  - Mitigation: conservative 3-token parse and monitor; refine parser if needed.

## Open questions
- Should we accept cross-variant matches (e.g., `LF` vs `FULL`)? Currently spec requires like-for-like only. We can extend later via config.
- Should patronymic-less forms be permitted in production flows? Spec already covers `LF` and `FP` variants.

## Acceptance criteria
- `fio_match` returns True iff any same-variant canonical pair matches among FULL/LF/FP/L_IO.
- Unit tests cover all outlined cases.
- Validator shows matched variant in diagnostics and uses it for verdict gating.

## Estimated effort
- Implementation: ~2–4h
- Tests: ~1–2h
- DEV deploy and validation: ~1h

## Change log (planned)
- Add: `rbidp/processors/fio_matching.py`
- Update: `rbidp/processors/validator.py` (use new matcher; add diagnostics)
- Optional Add: `rbidp/core/config.py` flags `FIO_ENABLE_FUZZY_FALLBACK`, `FIO_FUZZY_THRESHOLD`
- Add: `apps/main-dev/rb-ocr/tests/test_fio_matching.py`
