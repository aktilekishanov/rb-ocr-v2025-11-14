# Commenting Conventions (main-dev)

This document defines how we write comments and docstrings in `apps/main-dev/`.
The goal is to maximize signal and maintainability while minimizing noise and drift.

## 1. Principles
- Comment *why*, not what. Prefer self-documenting code first.
- Keep comments truthful, minimal, and up-to-date.
- Use docstrings for modules/classes/functions; inline comments only for non-obvious logic, algorithms, workarounds, and domain rules.
- Treat comments as part of the API and review them like code.

## 2. Docstring style
- Use **Google-style docstrings** for all new/updated docstrings.
- Module docstrings:
  - 3–6 lines explaining responsibility, boundaries, and main entrypoints.
- Function/method docstrings (public APIs):
  - `Args:` section for parameters.
  - `Returns:` section for return value(s).
  - `Raises:` section only when exceptions are part of the contract.

Example:
```python
"""
RB-OCR pipeline orchestrator.

Coordinates run directories, stage execution, timing, error handling,
and artifacts/manifest writing. Public entrypoint: `run_pipeline`.
"""


def validate_run(meta_path: str, merged_path: str, output_dir: str, filename: str, write_file: bool) -> dict:
    """
    Validate a run and optionally write validation.json.

    Args:
      meta_path: Path to metadata.json.
      merged_path: Path to merged.json.
      output_dir: Destination directory for validation.json.
      filename: Output filename; usually VALIDATION_FILENAME.
      write_file: If True, write validation.json; else return only in-memory result.

    Returns:
      Dict with keys: success, error, validation_path, result.

    Raises:
      OSError: On IO failures when write_file is True.
    """
```

## 3. Inline comments
- Single-line comments with one leading space after `#`.
- Place comments **above** the code they describe (not at end of line) except for very short notes.
- Only add inline comments when the intent is not obvious from code and names.

Good examples:
```python
# LLM parse failure: map to LLM_FILTER_PARSE_ERROR (file read or filter failure)
validation = validate_run(...)

# Treat stamp_present as tri-state (True/False/None) and honor STAMP_ENABLED toggle
if STAMP_ENABLED and isinstance(stamp_present_raw, bool):
    stamp_present = stamp_present_raw
```

Bad examples (avoid):
```python
i += 1  # increment i

# Call the function validate_run
validation = validate_run(...)
```

## 4. Comment taxonomy keywords
Use these prefixes for structured comments:

- `TODO(owner/issue):` actionable, time-bounded items.
  - Example: `# TODO(idp-team/JIRA-123): support multi-document runs`
- `NOTE:` rationale or design decision.
  - Example: `# NOTE: Using UTC+5 per bank policy for loan deferment docs.`
- `WORKAROUND:` temporary fix for an external issue (link if possible).
  - Example: `# WORKAROUND: Skip SSL verification for dev-ocr until certs are fixed.`
- `PERF:` performance considerations.
  - Example: `# PERF: O(n^2) FIO matching; acceptable for <= 50 variants.`
- `SECURITY:` security-sensitive notes.
  - Example: `# SECURITY: Do not log raw document contents or PII.`

## 5. Where to comment
- **Module-level**: one docstring per module that clarifies scope and key entrypoints.
- **Public functions/classes**: always have docstrings describing purpose, inputs, outputs, and relevant errors.
- **Complex logic** (matching, heuristics, merges, external protocols): brief inline comments explaining the approach.
- **Domain rules**: document business logic and policy-driven conditions.

## 6. When *not* to comment
- Do not restate the code or function name.
- Do not comment trivial control flow or simple assignments.
- Remove or update comments when behavior changes; never leave known-stale comments.

## 7. Review expectations
- PRs that alter behavior should update relevant comments/docstrings in the same change.
- Reviewers should:
  - Check comments for accuracy and clarity.
  - Flag redundant or noisy comments.
  - Ensure TODOs include owner/issue or are tracked elsewhere.

These conventions apply to all new code in `apps/main-dev/` and should be applied gradually to existing code as we touch files (following COMMENTING_PHASED_PLAN.MD).
