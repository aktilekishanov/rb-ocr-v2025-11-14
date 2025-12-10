# 🧐 Code Review: Self-Documenting Naming

**Date:** 2025-12-10
**Target:** `fastapi-service`
**Standard:** `world_class_best_practices.md` (Section 1: Readability & Intent)

---

## 📊 Executive Summary

The codebase generally follows good naming conventions for public interfaces (API schemas), but internal implementation details often suffer from "lazy naming" (abbreviations, single letters).

**Compliance Score:** 🟡 **70% (Needs Improvement)**

> **"Variable names should reveal intent. `days_since_last_login` is infinitely better than `d`."**

---

## 🚨 Critical Violations (Must Fix)

These variables actively hinder readability and must be renamed immediately.

### 1. `pipeline/orchestrator.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 396 | `fm` | `fio_match_result` | `fm` is ambiguous (frequency modulation? file manager?). |
| 402 | `dtk` | `doc_type_known` | `dtk` forces the reader to memorize the abbreviation. |
| 406 | `dv` | `doc_date_valid` | `dv` is unclear. |
| 298 | `dtc_raw_str` | `doc_type_check_raw_json` | `dtc` is internal jargon. |
| 364 | `ext` | `extractor_result` | `ext` usually means "extension". |
| 474 | `res` | `stage_result` | `res` is too generic. |

### 2. `api/schemas.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 92 | `v` | `iin_value` | In validators, `v` is common but `iin_value` is explicit. |
| 106 | `v` | `s3_path_value` | Same as above. |

### 3. `pipeline/processors/validator.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 46 | `s` | `text` | `s` is generic string. `text` or `input_string` is better. |
| 57 | `s` | `text` | Same as above. |
| 77 | `s` | `text` | Same as above. |
| 240 | `val` | `check_result` | `val` usually means "value", but here it's a boolean result. |

### 4. `pipeline/processors/fio_matching.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 78 | `s` | `text` | `s` is generic. |
| 83 | `s` | `text` | `s` is generic. |
| 159 | `p` | `name_parts` | `p` is ambiguous. |
| 276 | `v` | `variant_key` | `v` is too short. |

### 5. `pipeline/clients/llm_client.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 74 | `e` | `http_err` | `e` is generic. |
| 108 | `e` | `url_err` | `e` is generic. |
| 126 | `e` | `ssl_err` | `e` is generic. |

### 6. `pipeline/clients/tesseract_async_client.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 41 | `f` | `file_obj` | `f` is generic. |
| 134 | `mt` | `mime_type` | `mt` is ambiguous. |
| 136 | `ext` | `file_extension` | `ext` is ambiguous. |
| 83 | `s` | `text` | `s` is generic. |
| 159 | `p` | `name_parts` | `p` is ambiguous. |
| 276 | `v` | `variant_key` | `v` is too short. |

### 7. `pipeline/processors/image_to_pdf_converter.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 44 | `im` | `image` | `im` is a common abbreviation but `image` is clearer. |
| 48 | `f` | `frame_copy` | `f` usually means file. |
| 70 | `fr` | `frame` | `fr` is unclear. |

### 6. `pipeline/utils/io_utils.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 28 | `p` | `path_obj` | `p` is ambiguous. |

### 7. `pipeline/processors/filter_llm_generic_response.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 26 | `c0` | `first_choice` | `c0` looks like a variable from a math formula. |

### 8. `pipeline/processors/filter_ocr_response.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 18 | `p` | `page_data` | `p` is ambiguous. |
| 20 | `pn` | `page_number` | `pn` forces mental mapping. |

---

## ⚠️ Minor Issues (Should Fix)

These are not critical but improving them raises the code quality to "World Class".

### 1. `main.py`
- **Line 80**: `[str(l) for l in loc]` -> `[str(loc_part) for loc_part in loc]`. `l` looks like `1`.
- **Line 141**: `tmp` -> `temp_file`.
- **Line 116**: `fio` -> `full_name_fio`. While `fio` is a domain term (ФИО), for a global standard, it's obscure. However, if the entire team uses `fio`, it might be acceptable. **Recommendation:** Keep `fio` but ensure it's defined in the glossary.

### 2. `pipeline/orchestrator.py`
- **Line 449**: `ctx` -> `pipeline_context`. `ctx` is a very common convention, but `pipeline_context` is unambiguous.
- **Line 51**: `path` -> `pdf_file_path`. `path` is too generic.

### 3. `api/middleware/exception_handler.py`
- **Line 82**: `l` -> `loc_part`. `l` looks like `1`.

---
### 16. `pipeline/core/db_config.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 114 | `e` | `health_check_err` | `e` is generic. |

### 17. `pipeline/core/settings.py`
| Line | Current Name | Proposed Name | Why? |
| :--- | :--- | :--- | :--- |
| 16 | `_env_runs` | `env_runs_dir` | `_env_runs` is slightly obscure. |
## ✅ Good Examples (Keep These)

- `days_since_last_login` (Hypothetical goal)
- `processing_time_seconds` (Explicit unit!)
- `is_within_validity` (Boolean question)
- `validate_upload_file` (Verb-Noun)

---

## 🛠 Action Plan

1.  **Refactor `pipeline/orchestrator.py`**: Rename `fm`, `dtk`, `dv` to full names.
2.  **Refactor `pipeline/processors/validator.py`**: Rename `s` to `text`.
3.  **Refactor `api/schemas.py`**: Rename `v` in validators to descriptive names.
4.  **Refactor `pipeline/processors/fio_matching.py`**: Rename `s`, `p`, `v`.
5.  **Refactor `pipeline/processors/image_to_pdf_converter.py`**: Rename `im`, `f`, `fr`.
6.  **Refactor `pipeline/utils/io_utils.py`**: Rename `p`.
7.  **Refactor `pipeline/processors/filter_llm_generic_response.py`**: Rename `c0`.
8.  **Refactor `pipeline/processors/filter_ocr_response.py`**: Rename `p`, `pn`.
9.  **Refactor `api/middleware/exception_handler.py`**: Rename `l`.
