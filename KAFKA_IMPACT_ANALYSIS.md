# Kafka Integration Impact Analysis

## 1. Does the incoming Kafka event body affect the database scheme?

**YES, significantly.** 

The Kafka event contains critical business data that is currently missing from our proposed schema. To ensure full traceability and utility, the database schema **MUST** be updated to include these fields.

### Specific Changes Needed:

| Kafka Field | DB Column Recommendation | Why? |
|-------------|--------------------------|------|
| `request_id` | `external_request_id` (VARCHAR) | **Critical**. Links our internal `run_id` back to the original business request. Without this, we cannot correlate logs with the main banking system. |
| `iin` | `iin` (VARCHAR 12) | **Critical**. The IIN is the primary unique identifier for a person in the banking system. Storing just the name (FIO) is insufficient for unique identification. |
| `s3_path` | `source_s3_path` (VARCHAR) | **Important**. Provides the "source of truth" location of the file. If our local copy is deleted, we know where it came from. |
| `document_type` | `requested_doc_type_id` (INT) | **Useful**. Helps verify if the *detected* document type matches the *requested* one (e.g., did they upload a "Payment Schedule" when we asked for "Deferment Certificate"?). |
| `first_name`, `last_name`, `second_name` | `fio` (VARCHAR) OR Separate Columns | **Decision Required**. See below. |

---

## 2. The FastAPI accepts FIO as a full string, but Kafka sends separate parts. How does this affect?

This mismatch affects two areas: the **API Contract** and the **Data Processing Logic**.

### A. Impact on API Contract (The `v1/verify` endpoint)

**Current State**:
`POST /v1/verify (file, fio)`

**Problem**: 
If the "RB Loan Deferment IDP" service consumes the Kafka event and just calls the current API, **we will lose the `iin`, `request_id`, and `s3_path`**. The FastAPI service won't receive them, so it can't store them in the database.

**Required Change**:
You **MUST** update the FastAPI endpoint signature to accept these additional fields.

**New Proposed Signature**:
```python
class VerifyRequest(BaseModel):
    # New fields from Kafka
    external_request_id: str
    iin: str
    s3_path: str | None = None
    
    # Name parts (Option A: Receive separate parts)
    first_name: str
    last_name: str
    second_name: str | None = None
    
    # OR (Option B: Receive pre-assembled FIO)
    # fio: str 
```

### B. Impact on Logic (FIO Construction)

Since the OCR engine likely expects a single `fio` string to fuzzy-match against the document text, a transformation is required.

**Where should this happen?**

*   **Option 1: In the Consumer (Caller)**
    *   The "RB Loan Deferment IDP" concatenates `Last + " " + First + " " + Second` and sends it as `fio` to the API.
    *   *Pros*: API stays simpler.
    *   *Cons*: API loses the granular name data; if formatting rules change, the caller must update.

*   **Option 2: In the FastAPI Service (Recommended)**
    *   The API accepts `first_name`, `last_name`, `second_name`.
    *   The API constructs `fio = f"{last_name} {first_name} {second_name}".strip()` internally for the OCR processor.
    *   *Pros*: The API owns the logic of "how to format a name for OCR matching". We store exact atomic data in the DB (`first`, `last`, `iin`) which is much cleaner.

### Summary of "How this affects":

1.  **You cannot use the current `v1/verify` endpoint as-is** without losing data.
2.  **You need to add columns** to your database table (`iin`, `external_request_id`, `s3_path`).
3.  **You need to decide** where to join the names. **Recommendation**: Pass separate fields to the API, store separate fields in DB, and join them inside the Python code for the OCR check.
