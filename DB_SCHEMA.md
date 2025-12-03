# PostgreSQL Database Schema - Minimum Viable Product
**RB-OCR Document Verification System**

> **Version**: 1.0 MVP  
> **Date**: 2025-12-02  
> **Philosophy**: Normalized, simple, extensible

---

## Overview

This schema is designed to:
- ✅ Store all verification runs with full traceability
- ✅ Link internal runs to external Kafka requests
- ✅ Track processing stages and timing
- ✅ Store extracted data and validation results
- ✅ Support basic queries and analytics
- ❌ No complex views, triggers, or partitioning (can add later)

---

## Table Structure

### 1. `verification_runs` (Main Table)

**Purpose**: One row per verification request. This is the central table.

```sql
CREATE TABLE verification_runs (
    -- Primary Keys
    run_id VARCHAR(50) PRIMARY KEY,  -- Internal: "20251126_130742_cc65e"
    
    -- External Integration (from Kafka)
    external_request_id VARCHAR(100),  -- Links to banking system
    iin VARCHAR(12),                   -- Person's IIN (ИИН)
    source_s3_path VARCHAR(500),       -- Where file came from (MinIO)
    requested_doc_type_id INTEGER,     -- What they said they uploaded (optional)
    
    -- Person Info (from Kafka event)
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    second_name VARCHAR(100),          -- Отчество (can be NULL)
    
    -- File Info
    original_filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000),           -- Where we saved it locally
    content_type VARCHAR(100),
    file_size_bytes INTEGER,
    
    -- Processing Status
    status VARCHAR(20) NOT NULL CHECK (status IN ('processing', 'success', 'error')),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Final Result
    verdict BOOLEAN,                   -- True = all checks passed
    
    -- Performance Metrics
    duration_seconds NUMERIC(10, 3),
    ocr_seconds NUMERIC(10, 3),
    llm_seconds NUMERIC(10, 3),
    stamp_seconds NUMERIC(10, 3)
);

-- Basic indexes for common queries
CREATE INDEX idx_runs_external_request ON verification_runs(external_request_id);
CREATE INDEX idx_runs_iin ON verification_runs(iin);
CREATE INDEX idx_runs_created_at ON verification_runs(created_at DESC);
CREATE INDEX idx_runs_status ON verification_runs(status);
```

**When to write**: 
- **Stage 1 (Acquire)**: Insert row with `run_id`, external fields, person info, file info, `status='processing'`
- **Stage 6 (Finalize)**: Update with `verdict`, `completed_at`, `status='success'` or `'error'`, timing metrics

---

### 2. `extracted_data` (OCR/LLM Results)

**Purpose**: Store what we extracted from the document.

```sql
CREATE TABLE extracted_data (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL REFERENCES verification_runs(run_id) ON DELETE CASCADE,
    
    -- Extracted Fields (from LLM)
    extracted_fio VARCHAR(255),        -- What OCR found in document
    extracted_doc_date VARCHAR(50),    -- Date on document (as string)
    extracted_doc_type VARCHAR(100),   -- What type we detected
    
    -- Document Characteristics
    single_doc_type BOOLEAN,           -- True if only one doc in image
    doc_type_known BOOLEAN,            -- True if we recognize the type
    stamp_present BOOLEAN,             -- True if stamp detected
    
    -- OCR Text (for debugging/search)
    ocr_text TEXT,                     -- Full extracted text
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_extracted_run_id ON extracted_data(run_id);
```

**When to write**:
- **Stage 5 (Merge)**: Insert row with all extracted data from `merged.json`

**Note**: One-to-one relationship with `verification_runs` (each run has exactly one extraction result).

---

### 3. `validation_checks` (Individual Check Results)

**Purpose**: Store the result of each validation check (FIO match, date valid, etc.).

```sql
CREATE TABLE validation_checks (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL REFERENCES verification_runs(run_id) ON DELETE CASCADE,
    
    -- Check Results (from validator)
    fio_match BOOLEAN,                 -- Does extracted FIO match input?
    doc_type_known BOOLEAN,            -- Is doc type recognized?
    doc_date_valid BOOLEAN,            -- Is date within valid range?
    single_doc_type_valid BOOLEAN,     -- Is it a single document?
    stamp_present BOOLEAN,             -- Is stamp present? (if enabled)
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_validation_run_id ON validation_checks(run_id);
```

**When to write**:
- **Stage 6 (Validate)**: Insert row with all check results from `validation.json`

**Note**: One-to-one relationship with `verification_runs`.

---

### 4. `errors` (Error Tracking)

**Purpose**: Store errors that occurred during processing. One run can have multiple errors.

```sql
CREATE TABLE errors (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL REFERENCES verification_runs(run_id) ON DELETE CASCADE,
    
    error_code VARCHAR(50) NOT NULL,   -- "FIO_MISMATCH", "OCR_FAILED", etc.
    error_details TEXT,                -- Optional detailed message
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_errors_run_id ON errors(run_id);
CREATE INDEX idx_errors_code ON errors(error_code);
```

**When to write**:
- **Any Stage**: Insert a row whenever an error is detected
- **Stage 6 (Validate)**: Insert rows for failed validation checks

**Note**: One-to-many relationship (one run can have multiple errors).

---

## Data Flow by Pipeline Stage

Here's exactly when to write to each table:

### Stage 1: Acquire (File Upload)

```python
# INSERT into verification_runs
INSERT INTO verification_runs (
    run_id,
    external_request_id,
    iin,
    source_s3_path,
    requested_doc_type_id,
    first_name,
    last_name,
    second_name,
    original_filename,
    file_path,
    content_type,
    file_size_bytes,
    status,
    created_at
) VALUES (
    '20251202_162540_abc12',
    '123123',                    -- from Kafka
    '960125000000',              -- from Kafka
    'some_s3_address',           -- from Kafka
    4,                           -- from Kafka (optional)
    'Иван',                      -- from Kafka
    'Иванов',                    -- from Kafka
    'Иванович',                  -- from Kafka
    'document.pdf',
    '/app/runs/2025-12-02/20251202_162540_abc12/input/original/document.pdf',
    'application/pdf',
    87036,
    'processing',
    NOW()
);
```

### Stage 2-4: OCR, Doc Type Check, Extract

**No database writes** - just processing in memory.

### Stage 5: Merge

```python
# INSERT into extracted_data
INSERT INTO extracted_data (
    run_id,
    extracted_fio,
    extracted_doc_date,
    extracted_doc_type,
    single_doc_type,
    doc_type_known,
    stamp_present,
    ocr_text
) VALUES (
    '20251202_162540_abc12',
    'Иванов Иван Иванович',      -- from merged.json
    '15.11.2025',                -- from merged.json
    'Справка о расторжении',     -- from merged.json
    true,                        -- from merged.json
    true,                        -- from merged.json
    false,                       -- from stamp check
    'Full OCR text here...'      -- from ocr_pages.json
);
```

### Stage 6: Validate & Finalize

```python
# INSERT into validation_checks
INSERT INTO validation_checks (
    run_id,
    fio_match,
    doc_type_known,
    doc_date_valid,
    single_doc_type_valid,
    stamp_present
) VALUES (
    '20251202_162540_abc12',
    false,                       -- from validation.json
    true,
    true,
    true,
    false
);

# INSERT into errors (for each failed check)
INSERT INTO errors (run_id, error_code) VALUES 
    ('20251202_162540_abc12', 'FIO_MISMATCH');

# UPDATE verification_runs (final status)
UPDATE verification_runs SET
    verdict = false,             -- from validation result
    status = 'success',          -- processing completed
    completed_at = NOW(),
    duration_seconds = 4.51,
    ocr_seconds = 0.25,
    llm_seconds = 4.23,
    stamp_seconds = NULL
WHERE run_id = '20251202_162540_abc12';
```

---

## Connecting Runs with External Requests

### The Link

```
Kafka Event (request_id: 123123)
    ↓
RB Loan Deferment IDP downloads file
    ↓
Calls POST /v1/verify with external_request_id=123123
    ↓
FastAPI creates run_id=20251202_162540_abc12
    ↓
Database stores BOTH:
    - run_id (internal)
    - external_request_id (external)
```

### Query Examples

```sql
-- Find our internal run from external request
SELECT run_id, verdict, status 
FROM verification_runs 
WHERE external_request_id = '123123';

-- Find all runs for a specific person
SELECT run_id, created_at, verdict 
FROM verification_runs 
WHERE iin = '960125000000'
ORDER BY created_at DESC;

-- Get full details of a run
SELECT 
    vr.run_id,
    vr.external_request_id,
    vr.iin,
    vr.first_name || ' ' || vr.last_name || ' ' || COALESCE(vr.second_name, '') as full_name,
    vr.verdict,
    vr.status,
    ed.extracted_fio,
    ed.extracted_doc_type,
    vc.fio_match,
    vc.doc_date_valid
FROM verification_runs vr
LEFT JOIN extracted_data ed ON vr.run_id = ed.run_id
LEFT JOIN validation_checks vc ON vr.run_id = vc.run_id
WHERE vr.run_id = '20251202_162540_abc12';

-- Get all errors for a run
SELECT error_code, error_details 
FROM errors 
WHERE run_id = '20251202_162540_abc12';
```

---

## About `requested_doc_type_id`

Since you don't use `doc_type` in your verification pipeline, here's what to do:

**Option 1: Store it anyway (Recommended)**
```sql
requested_doc_type_id INTEGER,  -- Just store it, don't use it
```
- **Pros**: Future-proofing. If later you want to compare "what they said" vs "what we detected", you have the data.
- **Cons**: None really, it's just one integer column.

**Option 2: Ignore it completely**
- Don't add the column at all.
- **Pros**: Simpler schema.
- **Cons**: If requirements change, you'll need a migration.

**My Recommendation**: **Store it**. It costs nothing and gives you flexibility. You can always ignore it in queries.

---

## Schema Diagram

```
┌─────────────────────────────────────────┐
│       verification_runs (main)          │
│─────────────────────────────────────────│
│ PK: run_id                              │
│     external_request_id (from Kafka)    │
│     iin (from Kafka)                    │
│     first_name, last_name, second_name  │
│     file_path, status, verdict          │
│     created_at, completed_at            │
│     duration_seconds, ocr_seconds, ...  │
└─────────────────────────────────────────┘
         │                │              │
         │                │              │
         ▼                ▼              ▼
┌──────────────┐  ┌──────────────┐  ┌──────────┐
│extracted_data│  │validation_   │  │  errors  │
│              │  │  checks      │  │          │
│FK: run_id    │  │FK: run_id    │  │FK: run_id│
│extracted_fio │  │fio_match     │  │error_code│
│extracted_date│  │doc_date_valid│  │details   │
│ocr_text      │  │stamp_present │  │          │
└──────────────┘  └──────────────┘  └──────────┘
   (1-to-1)          (1-to-1)        (1-to-many)
```

---

## Complete SQL Schema

```sql
-- ============================================================================
-- RB-OCR Minimum Viable Database Schema
-- ============================================================================

-- Main table: one row per verification request
CREATE TABLE verification_runs (
    -- Primary key
    run_id VARCHAR(50) PRIMARY KEY,
    
    -- External integration (from Kafka)
    external_request_id VARCHAR(100),
    iin VARCHAR(12),
    source_s3_path VARCHAR(500),
    requested_doc_type_id INTEGER,
    
    -- Person info (from Kafka)
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    second_name VARCHAR(100),
    
    -- File info
    original_filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000),
    content_type VARCHAR(100),
    file_size_bytes INTEGER,
    
    -- Processing status
    status VARCHAR(20) NOT NULL CHECK (status IN ('processing', 'success', 'error')),
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    
    -- Final result
    verdict BOOLEAN,
    
    -- Performance metrics
    duration_seconds NUMERIC(10, 3),
    ocr_seconds NUMERIC(10, 3),
    llm_seconds NUMERIC(10, 3),
    stamp_seconds NUMERIC(10, 3)
);

-- Extracted data from OCR/LLM
CREATE TABLE extracted_data (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL REFERENCES verification_runs(run_id) ON DELETE CASCADE,
    
    extracted_fio VARCHAR(255),
    extracted_doc_date VARCHAR(50),
    extracted_doc_type VARCHAR(100),
    single_doc_type BOOLEAN,
    doc_type_known BOOLEAN,
    stamp_present BOOLEAN,
    ocr_text TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Validation check results
CREATE TABLE validation_checks (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL REFERENCES verification_runs(run_id) ON DELETE CASCADE,
    
    fio_match BOOLEAN,
    doc_type_known BOOLEAN,
    doc_date_valid BOOLEAN,
    single_doc_type_valid BOOLEAN,
    stamp_present BOOLEAN,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Errors (one-to-many)
CREATE TABLE errors (
    id SERIAL PRIMARY KEY,
    run_id VARCHAR(50) NOT NULL REFERENCES verification_runs(run_id) ON DELETE CASCADE,
    
    error_code VARCHAR(50) NOT NULL,
    error_details TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- Indexes (minimum set for performance)
-- ============================================================================

-- verification_runs indexes
CREATE INDEX idx_runs_external_request ON verification_runs(external_request_id);
CREATE INDEX idx_runs_iin ON verification_runs(iin);
CREATE INDEX idx_runs_created_at ON verification_runs(created_at DESC);
CREATE INDEX idx_runs_status ON verification_runs(status);

-- extracted_data indexes
CREATE INDEX idx_extracted_run_id ON extracted_data(run_id);

-- validation_checks indexes
CREATE INDEX idx_validation_run_id ON validation_checks(run_id);

-- errors indexes
CREATE INDEX idx_errors_run_id ON errors(run_id);
CREATE INDEX idx_errors_code ON errors(error_code);
```

---

## Future Improvements (Not MVP)

When you're ready to optimize further, consider:

1. **Partitioning**: Partition `verification_runs` by month for faster queries
2. **Materialized Views**: Create views for dashboards
3. **Full-text Search**: Add GIN index on `ocr_text` for text search
4. **Retention Policy**: Automated cleanup of old runs
5. **Audit Trail**: Add `created_by`, `ip_address` columns
6. **Performance**: Add composite indexes based on actual query patterns

---

## Summary

**4 Tables**:
1. `verification_runs` - Main table (1 row per request)
2. `extracted_data` - OCR/LLM results (1-to-1)
3. `validation_checks` - Validation results (1-to-1)
4. `errors` - Error tracking (1-to-many)

**Key Relationships**:
- `external_request_id` links to Kafka event
- `run_id` is your internal identifier
- `iin` identifies the person uniquely

**Write Pattern**:
- Stage 1: INSERT into `verification_runs`
- Stage 5: INSERT into `extracted_data`
- Stage 6: INSERT into `validation_checks` and `errors`, UPDATE `verification_runs`

This schema is **normalized**, **simple**, and **extensible**. You can start with this and add complexity as needed.
