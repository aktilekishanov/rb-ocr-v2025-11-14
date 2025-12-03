# File Retention Strategy - Answer

## Question: Should we delete the original uploaded file?

**YES - Eventually you should delete it, but with a retention policy.**

---

## Recommended Retention Policy

### For Uploaded Files (`input/original/*`)

**Retention Period**: **30 days**

**Rationale**:
1. ✅ **Compliance/Audit**: Keep files for a reasonable period in case of disputes or re-verification requests
2. ✅ **Debugging**: If there's a processing error, you can re-run the file through the pipeline
3. ✅ **Storage Cost**: After 30 days, the file can be retrieved from the original source (`source_s3_path` in MinIO) if needed
4. ✅ **Disk Space**: Prevents unlimited growth of storage

**Implementation**:
```bash
# Daily cron job (runs at 2 AM)
find /app/runs -type f -name "*.pdf" -mtime +30 -delete
find /app/runs -type f -name "*.jpg" -mtime +30 -delete
find /app/runs -type f -name "*.png" -mtime +30 -delete

# Or delete entire run directories older than 30 days
find /app/runs -type d -mtime +30 -exec rm -rf {} +
```

---

## Question: Should we store file metadata in the database?

**YES - Absolutely!**

Even after deleting the physical file, you should **keep the metadata** in the database.

### Why Store These Fields?

```sql
original_filename VARCHAR(500) NOT NULL,  -- ✅ KEEP
file_path VARCHAR(1000),                  -- ✅ KEEP
content_type VARCHAR(100),                -- ✅ KEEP
file_size_bytes INTEGER,                  -- ✅ KEEP
```

### Justification for Each Field:

| Field | Keep? | Why? |
|-------|-------|------|
| `original_filename` | ✅ **YES** | **Critical**. Shows what the user uploaded. Useful for debugging ("they uploaded a JPG instead of PDF"). Also needed for audit trail. |
| `file_path` | ✅ **YES** | **Important**. Shows where the file *was* stored. Even if deleted, you know the location pattern. Also, if the file still exists, you can retrieve it. |
| `content_type` | ✅ **YES** | **Useful**. Helps identify file type issues. If someone uploaded a Word doc instead of PDF, this will show it. |
| `file_size_bytes` | ✅ **YES** | **Analytics**. Track average file sizes, identify unusually large files that might cause processing issues. |

---

## Recommended Data Flow

### Timeline for a Single Run:

```
Day 0: File uploaded
  ├─ File saved to: /app/runs/2025-12-03/20251203_094357_abc12/input/original/document.pdf
  ├─ DB record created with file_path, original_filename, content_type, file_size_bytes
  └─ Processing completes, all data extracted to DB

Day 1-29: File exists on disk
  ├─ Can be retrieved if needed for re-processing
  └─ DB still has all metadata

Day 30: File deleted by cleanup cron
  ├─ Physical file removed from disk
  ├─ DB metadata STILL EXISTS
  └─ If file needed again, can be retrieved from source_s3_path (MinIO)

Day 90: Database record archived (optional)
  └─ Move to cold storage or delete DB record (success runs only)
```

---

## Updated Database Schema Recommendation

**Keep all 4 fields**:

```sql
CREATE TABLE verification_runs (
    run_id VARCHAR(50) PRIMARY KEY,
    
    -- External source (can re-download if needed)
    source_s3_path VARCHAR(500),        -- Where file came from (MinIO)
    
    -- File metadata (KEEP even after file deletion)
    original_filename VARCHAR(500) NOT NULL,  -- ✅ What user uploaded
    file_path VARCHAR(1000),                  -- ✅ Where we saved it
    content_type VARCHAR(100),                -- ✅ MIME type
    file_size_bytes INTEGER,                  -- ✅ File size
    
    -- Add a flag to track if file still exists
    file_deleted_at TIMESTAMP WITH TIME ZONE, -- ✅ When file was deleted (NULL = still exists)
    
    -- ... rest of schema
);
```

### New Field: `file_deleted_at`

**Purpose**: Track when the physical file was deleted.

**Usage**:
```sql
-- Check if file still exists
SELECT run_id, file_path, file_deleted_at
FROM verification_runs
WHERE run_id = '20251203_094357_abc12';

-- If file_deleted_at IS NULL → file still exists
-- If file_deleted_at IS NOT NULL → file was deleted, but metadata remains
```

**Cleanup Script** (updated):
```python
import os
from datetime import datetime, timedelta
from database.connection import SessionLocal
from database.models import VerificationRun

def cleanup_old_files():
    """Delete files older than 30 days and mark in DB"""
    db = SessionLocal()
    cutoff_date = datetime.now() - timedelta(days=30)
    
    # Find runs with files older than 30 days
    old_runs = db.query(VerificationRun).filter(
        VerificationRun.created_at < cutoff_date,
        VerificationRun.file_deleted_at.is_(None)  # File not yet deleted
    ).all()
    
    for run in old_runs:
        if run.file_path and os.path.exists(run.file_path):
            try:
                os.remove(run.file_path)
                run.file_deleted_at = datetime.now()
                print(f"Deleted file: {run.file_path}")
            except Exception as e:
                print(f"Failed to delete {run.file_path}: {e}")
    
    db.commit()
    db.close()
```

---

## Summary

### ✅ What to Do:

1. **Store all 4 file metadata fields** in the database
2. **Keep the physical file for 30 days** after processing
3. **Delete the file after 30 days** via automated cleanup
4. **Keep the metadata in DB** even after file deletion
5. **Add `file_deleted_at` field** to track deletion timestamp
6. **Use `source_s3_path`** to re-download from MinIO if needed later

### ❌ What NOT to Do:

1. ❌ Don't delete file metadata from DB when deleting the physical file
2. ❌ Don't keep files forever (disk space will explode)
3. ❌ Don't delete files immediately after processing (need for debugging)

### 🎯 Benefits:

- **Audit Trail**: Always know what file was processed, even if deleted
- **Debugging**: Can identify file type issues from metadata
- **Analytics**: Track file size trends, content type distribution
- **Recovery**: Can re-download from `source_s3_path` if needed
- **Compliance**: Metadata retained for regulatory requirements
- **Cost**: Disk space controlled, but data preserved

---

## Final Recommendation

**Keep the schema as-is, but add one field**:

```sql
-- Add to verification_runs table
file_deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL
```

This gives you full traceability while managing disk space efficiently.
