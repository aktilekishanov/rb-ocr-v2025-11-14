# RB-OCR / IDP – Database & Storage Guide

## 1. Current Storage Model

### 1.1 Per-run directory layout

Both `main-dev/rb-ocr` and `main/rbocr/rbidp` follow the same conceptual pattern:

- **Runs root** (configured in service):
  - `runs_root/<YYYY-MM-DD>/<run_id>/`
    - `input/original/` – original uploaded file copy (and possibly converted PDF)
    - `ocr/` – OCR service raw and filtered outputs
      - `ocr_response_raw.json`
      - `ocr_response_filtered.json` (normalized `{pages: [...]}`)
    - `llm/` or `gpt/` – LLM raw/filtered outputs, merged JSON
      - `doc_type_check.raw.json`, `doc_type_check.filtered.json`
      - `extractor.raw.json`, `extractor.filtered.json`
      - `merged.json`
    - `meta/` – metadata & high-level artifacts
      - `metadata.json` – user input and document meta
      - `final_result.json` – final verdict + error codes (+ `stamp_present` when available)
      - `manifest.json` – operator-oriented summary (timing, file info, artifact paths, status, error)
      - `side_by_side.json` – comparison view (meta vs extracted fields, validity window, stamp info)
      - `stamp_check_response.json` – `{stamp_present: bool}` when stamp check runs
    - `validation/` (in main-dev) – validation results
      - `validation.json` – structured validation output

### 1.2 What lives only on disk today

- **All intermediate artifacts** (OCR raw, OCR filtered, LLM raw/filtered, merged, validation).
- **Per-run high-level artifacts** (manifest, side_by_side, final_result) are JSON files in `meta/`.
- **Timing data** and per-step durations are stored in `manifest.json` and *not* in a DB.
- **Errors and checks**:
  - Only error *codes* are written to `final_result.json` and `manifest.json`.
  - Full error objects, checks, and context live in memory during a run but are not persisted in a DB.

## 2. Is this best practice?

### 2.1 What works well

- **Filesystem as artifact store**
  - Keeps heavy, semi-structured artifacts (OCR, LLM, merged JSONs) out of the DB.
  - Folder hierarchy is intuitive (`date/run_id`) and good for low-level debugging.

- **Explicit curated artifacts**
  - `manifest.json`: single source of truth for run-level info for operators.
  - `side_by_side.json`: great for QA/inspection.
  - `final_result.json`: minimal, API-facing summary.

### 2.2 Limitations vs typical production patterns

- **No queryable history**
  - You cannot efficiently query “all failed runs for doc_type=X last 30 days” or
    “average OCR latency by doc_type per week”.
  - Analytics requires log scraping / scanning many JSONs on disk.

- **No durable run registry**
  - The only canonical ID is `run_id` in the folder name and JSONs.
  - There’s no DB of runs to support integrations (other services/kafka consumers need to parse JSONs).

- **Operational fragility**
  - Renaming/moving runs root or cleaning old folders is dangerous without a DB index.
  - Hard to implement retention policies (“keep final artifacts 90 days, raw 7 days”) in a controlled way.

- **Audit & compliance gaps**
  - For regulated flows (loan deferment, etc.) you typically need:
    - A **run table** with who/when/what/verdict.
    - Traceability to external identifiers (request_id, iin, etc.).
    - Reasonable ability to reconstruct decisions, or at least see which artifacts existed.

**Conclusion:**

- **Keeping artifacts on disk is fine and recommended.**
- **Not having a DB for run-level metadata and status is *not* best practice** for a bank/IDP scenario.

## 3. Should we introduce a Postgres database?

Yes, recommended.

**What Postgres should be used for:**

- **Run registry**: one row per pipeline run, with timestamps, verdict, status, and external correlation IDs.
- **Lightweight structured results**: extracted key fields (fio, doc_date, doc_type, stamp_present, etc.)
  for search, analytics, monitoring.
- **Error & validation tracking**: per-run error codes and validation checks.
- **Stable references to artifacts**: paths/URLs to the JSONs/files in the run folder or in S3.

**What Postgres should *not* be used for:**

- Storing full OCR raw outputs, full LLM responses, big PDFs/images.
- Storing side-by-side JSON bodies or full merged payload; those remain on disk or in S3, with **paths in DB**.

This aligns with common patterns:

- DB = **metadata / indexes / status / light extracted fields**.
- Filesystem/S3 = **large, semi-structured artifacts**.

## 4. Recommended logical data model

This section describes the **logical** model. The concrete SQL schema is in §5.

### 4.1 Core entities

- **Run** – one execution of RB-OCR/IDP pipeline for a single document.
- **RunArtifact** – named pointer to a file/json artifact produced in the run.
- **RunError** – individual error code associated with a run.
- **RunCheck** – structured validation/consistency checks (fio_match, doc_type_known, etc.).
- **RunTiming** – per-stage durations (ocr, llm/gpt, stamp, total).

In a minimal setup, `RunTiming` can be folded into `Run` as JSON; below we model it in the `runs` table.

### 4.2 What we store for each run

- **Identifiers**
  - `id` – DB primary key (UUID or bigserial).
  - `run_id` – external run identifier used in folder names and responses.
  - `correlation_id` – optional external ID (e.g. Kafka `request_id`).

- **Input / user meta**
  - `fio`, `reason`, `doc_type` (from request).
  - `iin` or other business identifiers (if applicable).

- **File metadata**
  - `original_filename`, `content_type`, `size_bytes`, `pages`.
  - `input_path` – path/URL to stored file (local path, S3 URL, or both).

- **Outcome**
  - `status` – e.g. `success`, `error`, `validation_failed`, `ocr_failed`, etc.
  - `verdict` – boolean/nullable (e.g. document valid or not).
  - `main_error_code` – primary error code when failed (duplicate of top-level error field in manifest).

- **Extracted & validation fields**
  - `extracted_fio`, `extracted_doc_type`, `extracted_doc_date`, `valid_until`.
  - `stamp_present`.
  - Validation flags: `fio_match`, `doc_type_known`, `doc_date_valid`, `single_doc_type_valid`.

- **Timing**
  - `duration_seconds`, `ocr_seconds`, `llm_seconds` (or `gpt_seconds`), `stamp_seconds`.

- **Timestamps**
  - `created_at` – request creation time (from manifest).
  - `started_at` – when pipeline started (approx `t0`).
  - `finished_at` – when pipeline completed.

- **Artifacts**
  - Columns for **key artifacts**:
    - `final_result_path`
    - `manifest_path`
    - `side_by_side_path`
    - `merged_path`
    - `ocr_filtered_path`
    - `ocr_raw_path`
    - `stamp_check_response_path`
  - Optionally a separate `run_artifacts` table for additional named artifacts.

## 5. Concrete Postgres schema (proposed)

### 5.1 Table: `runs`

Stores one row per pipeline run with high-value fields and key artifact pointers.

```sql
CREATE TABLE runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- External identifiers
    run_id              TEXT NOT NULL UNIQUE,
    correlation_id      TEXT NULL,              -- e.g. Kafka request_id
    external_request_id TEXT NULL,              -- explicit callback/request identifier

    -- Request and user meta
    fio                 TEXT NULL,
    reason              TEXT NULL,
    doc_type_requested  TEXT NULL,
    iin                 TEXT NULL,

    -- File metadata
    original_filename   TEXT NULL,
    content_type        TEXT NULL,
    size_bytes          BIGINT NULL,
    page_count          INTEGER NULL,
    input_path          TEXT NULL,             -- path/URL of stored file (local or S3)

    -- Outcome / status
    status              TEXT NOT NULL,         -- e.g. success, error, validation_failed
    verdict             BOOLEAN NULL,          -- true/false when success, null when not applicable
    main_error_code     TEXT NULL,             -- primary error

    -- Extracted fields (from merged.json / side_by_side.json)
    extracted_fio       TEXT NULL,
    extracted_doc_type  TEXT NULL,
    extracted_doc_date  DATE NULL,
    valid_until         DATE NULL,

    -- Validation flags (from validation.json / checks)
    fio_match           BOOLEAN NULL,
    doc_type_known      BOOLEAN NULL,
    doc_date_valid      BOOLEAN NULL,
    single_doc_type_valid BOOLEAN NULL,
    stamp_present       BOOLEAN NULL,

    -- Timing
    duration_seconds    DOUBLE PRECISION NULL,
    ocr_seconds         DOUBLE PRECISION NULL,
    llm_seconds         DOUBLE PRECISION NULL,
    stamp_seconds       DOUBLE PRECISION NULL,

    -- Artifact paths (local filesystem or S3 URIs)
    final_result_path       TEXT NULL,
    manifest_path           TEXT NULL,
    side_by_side_path       TEXT NULL,
    merged_path             TEXT NULL,
    ocr_filtered_path       TEXT NULL,
    ocr_raw_path            TEXT NULL,
    stamp_check_response_path TEXT NULL,

    -- Timestamps
    created_at          TIMESTAMPTZ NOT NULL,
    started_at          TIMESTAMPTZ NULL,
    finished_at         TIMESTAMPTZ NULL,

    -- Misc
    extra               JSONB NULL,

    -- Indexing
    CONSTRAINT runs_created_at_not_future CHECK (created_at <= now() + interval '1 day')
);

CREATE INDEX idx_runs_created_at       ON runs (created_at DESC);
CREATE INDEX idx_runs_status           ON runs (status);
CREATE INDEX idx_runs_verdict          ON runs (verdict);
CREATE INDEX idx_runs_doc_type         ON runs (extracted_doc_type);
CREATE INDEX idx_runs_iin_created_at   ON runs (iin, created_at DESC);
CREATE INDEX idx_runs_correlation_id   ON runs (correlation_id);
```

### 5.2 Table: `run_errors`

Stores all error codes per run (optional, but useful for analytics).

```sql
CREATE TABLE run_errors (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,
    details     TEXT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_run_errors_run_id ON run_errors (run_id);
CREATE INDEX idx_run_errors_code   ON run_errors (code);
```

### 5.3 Table: `run_artifacts` (optional)

If you foresee more artifact types, use a separate table instead of adding many columns to `runs`.

```sql
CREATE TABLE run_artifacts (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,         -- e.g. "ocr_filtered", "side_by_side"
    path            TEXT NOT NULL,         -- filesystem path or S3 URI
    content_type    TEXT NULL,             -- e.g. application/json
    size_bytes      BIGINT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX idx_run_artifacts_unique
    ON run_artifacts (run_id, name);
```

### 5.4 Table: `run_checks` (optional)

If you want flexible check sets that might grow (beyond current fixed checks):

```sql
CREATE TABLE run_checks (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,        -- e.g. "fio_match", "doc_type_known"
    value_bool  BOOLEAN NULL,
    value_text  TEXT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_run_checks_run_id ON run_checks (run_id);
CREATE INDEX idx_run_checks_name   ON run_checks (name);
```

For the current pipeline, you can keep checks as **columns on `runs`** and skip `run_checks` to reduce complexity.

## 6. Mapping from current JSONs to DB fields

This mapping is indicative; exact field names can be adjusted during implementation.

### 6.1 `manifest.json` → `runs`

Fields (main-dev `pipeline/utils/artifacts.write_manifest`):

- `run_id` → `runs.run_id`
- `created_at` → `runs.created_at`
- `timing.duration_seconds` → `runs.duration_seconds`
- `timing.stamp_seconds` → `runs.stamp_seconds`
- `timing.ocr_seconds` → `runs.ocr_seconds`
- `timing.llm_seconds` → `runs.llm_seconds`
- `user_input.fio` → `runs.fio`
- `user_input.reason` → `runs.reason`
- `user_input.doc_type` → `runs.doc_type_requested`
- `file.original_filename` → `runs.original_filename`
- `file.saved_path` → `runs.input_path`
- `file.content_type` → `runs.content_type`
- `file.size_bytes` → `runs.size_bytes`
- `artifacts.final_result_path` → `runs.final_result_path`
- `artifacts.side_by_side_path` → `runs.side_by_side_path`
- `artifacts.merged_path` → `runs.merged_path`
- `status` → `runs.status`
- `error` → `runs.main_error_code`

### 6.2 `final_result.json` → `runs` and `run_errors`

Fields (main-dev `build_final_result`):

- `run_id` (same as above; check consistency vs `manifest.json`).
- `verdict` → `runs.verdict`.
- `errors[]` (codes) → `run_errors` (with `code`), or use inline arrays in `runs.extra`.
- `stamp_present` → `runs.stamp_present` (when present).

### 6.3 `side_by_side.json` and `merged.json` → `runs`

- `side_by_side.fio.extracted` or `merged.fio` → `runs.extracted_fio`.
- `side_by_side.doc_type.extracted` or `merged.doc_type` → `runs.extracted_doc_type`.
- `side_by_side.doc_date.extracted` or `merged.doc_date` → `runs.extracted_doc_date`.
- `side_by_side.doc_date.valid_until` → `runs.valid_until`.
- `side_by_side.single_doc_type.extracted` or `merged.single_doc_type` → `runs.single_doc_type_valid` (bool/nullable).
- `side_by_side.doc_type_known.extracted` or `merged.doc_type_known` → `runs.doc_type_known`.
- `side_by_side.stamp_present.extracted` → `runs.stamp_present`.

### 6.4 `validation.json` → `runs`

From `validate_run` result (via `stage_validate_and_finalize`):

- `checks.fio_match` → `runs.fio_match`.
- `checks.doc_type_known` → `runs.doc_type_known`.
- `checks.doc_date_valid` → `runs.doc_date_valid`.
- `checks.single_doc_type_valid` → `runs.single_doc_type_valid`.
- `checks.stamp_present` → `runs.stamp_present` (or only when available).

## 7. Implementation guidelines

### 7.1 Where to integrate DB writes

In the orchestrator (main-dev example):

- **When run starts** (before `stage_acquire`):
  - Insert a `runs` row with `run_id`, `created_at`, `status='running'`, basic request meta.
  - Optionally set `started_at`.

- **After `stage_acquire`**:
  - Update `runs` with `input_path`, `original_filename`, `content_type`, `size_bytes`, `page_count`.

- **After each stage** (optional):
  - Update timing fields from `ctx.timers`.

- **On `fail_and_finalize`**:
  - Use `main_error_code` and `status='error'` or more specific.
  - Insert `run_errors` rows for each `ctx.errors`.
  - Update `finished_at`.

- **On `finalize_success`**:
  - Populate `verdict`, validation flags, extracted fields (from merged/side_by_side/validation).
  - Update `status='success'`, `finished_at`.

The filesystem behavior (writing JSONs) **stays exactly as now**; the DB layer observes and records.

### 7.2 Transaction and failure semantics

- Keep DB operations **best-effort but robust**:
  - If DB is down, pipeline can still complete and write JSONs.
  - Log DB errors, maybe set a flag in `extra` on retry.

- For critical banking flows, you may later tighten this to:
  - Require at least the `runs` row to be written, otherwise treat run as failed.

### 7.3 Retention & cleanup

Once DB exists, you can:

- Implement **filesystem cleanup jobs**:
  - Use `runs` table to identify old runs and their artifact paths.
  - Delete old heavy artifacts (e.g. OCR raw > 30 days) while keeping run metadata.

- Support **reporting & monitoring** directly from Postgres.

## 8. Summary

- Current storage is **filesystem-first**, with good artifact separation but no database-backed run registry.
- Best practice for an IDP service in a bank is to:
  - Keep artifacts on disk/S3.
  - Add a **Postgres database** that tracks: runs, statuses, verdicts, key extracted fields, timings, artifacts, errors.
- The proposed schema (`runs`, optional `run_errors` and `run_artifacts`) is intentionally **decoupled** from raw JSON structure and focuses on what is useful for:
  - Operations & monitoring
  - Analytics & reporting
  - Auditability and traceability.
