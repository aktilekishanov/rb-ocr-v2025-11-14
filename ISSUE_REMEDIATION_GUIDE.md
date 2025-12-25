# Issue Remediation Guide - FastAPI Service
## Simple Explanations & Step-by-Step Implementation Plans

**Date**: 2025-12-25  
**Project**: RB-OCR Document Verification API  
**Total Issues**: 8

---

## Quick Reference

| # | Issue | Severity | Effort | File |
|---|-------|----------|--------|------|
| 1 | Module-Level Global State | HIGH | 4h | `pipeline/core/db_config.py` |
| 2 | Singleton Webhook Client | MEDIUM | 2h | `services/webhook_client.py` |
| 3 | Missing Rate Limiting | HIGH | 3h | All endpoints |
| 4 | Blocking PDF Operations | MEDIUM | 1.5h | `pipeline/orchestrator.py` |
| 5 | High Code Complexity | HIGH | 3h | `pipeline/processors/fio_matching.py` |
| 6 | SRP Violation | HIGH | 4h | `services/processor.py` |
| 7 | Interface Segregation | MEDIUM | 2h | `pipeline/orchestrator.py` |
| 8 | Race Condition | FIXED | 0h | Already addressed |

---

## Issue #1: Module-Level Global State

### 🤔 Simple Explanation

**Problem**: Database connection pool is a global variable that everyone accesses magically.

**Analogy**: It's like having ONE shared toolbox in a building's hallway. Everyone grabs tools from it without asking, and you can't replace it with a fake toolbox for testing.

**Why it's bad**:
- 🔴 Can't test with mock database
- 🔴 Thread safety issues
- 🔴 Configuration locked at startup
- 🔴 Hidden dependencies

### ✅ Solution: Dependency Injection

**Goal**: Pass the database manager explicitly instead of grabbing it from thin air.

### 📋 Implementation Steps

#### Step 1: Create DatabaseManager class (1h)
```python
# Create: pipeline/core/database_manager.py

class DatabaseManager:
    """Manages database pool lifecycle."""
    
    def __init__(self, host, port, database, user, password):
        self.host = host
        # ... store config
        self._pool = None
    
    async def connect(self):
        """Initialize pool."""
        self._pool = await asyncpg.create_pool(...)
    
    async def get_pool(self):
        """Get connection pool."""
        return self._pool
```

#### Step 2: Store in app state (30min)
```python
# Update: core/lifespan.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    db = DatabaseManager(...)
    await db.connect()
    app.state.db_manager = db  # Store here
    yield
    await db.disconnect()
```

#### Step 3: Create dependency (15min)
```python
# Create: core/dependencies.py

async def get_db_manager(request: Request):
    return request.app.state.db_manager
```

#### Step 4: Inject in routes (1h)
```python
# Update: api/routes/verify.py

from core.dependencies import get_db_manager

@router.post("/v1/verify")
async def verify(
    db: DatabaseManager = Depends(get_db_manager)  # Inject here
):
    pool = await db.get_pool()
    # ... use pool
```

#### Step 5: Update all callers (1.5h)
Update `services/tasks.py`, `pipeline/utils/db_client.py` to accept `db_manager` parameter.

---

## Issue #2: Singleton Webhook Client

### 🤔 Simple Explanation

**Problem**: One global webhook client created at import time.

**Analogy**: Office has ONE shared phone that's permanently connected to a number. Can't change the number, can't use a fake phone for testing.

**Why it's bad**:
- 🔴 Can't mock in tests
- 🔴 Configuration locked when file imports
- 🔴 Tests interfere with each other

### ✅ Solution: Dependency Injection

**Goal**: Create webhook client on-demand and pass it where needed.

### 📋 Implementation Steps

#### Step 1: Remove global (5min)
```python
# Update: services/webhook_client.py

# REMOVE: webhook_client = WebhookClient()

# ADD:
def create_webhook_client_from_env():
    return WebhookClient(
        url=os.getenv("WEBHOOK_URL"),
        # ...
    )
```

#### Step 2: Store in app state (15min)
```python
# Update: core/lifespan.py

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... database setup
    
    webhook = create_webhook_client_from_env()
    app.state.webhook_client = webhook
    yield
```

#### Step 3: Create dependency (10min)
```python
# Update: core/dependencies.py

async def get_webhook_client(request: Request):
    return request.app.state.webhook_client
```

#### Step 4: Inject everywhere (1.5h)
Update routes and `services/tasks.py` to accept `webhook` parameter.

---

## Issue #3: Missing Rate Limiting

### 🤔 Simple Explanation

**Problem**: No limits on how many requests users can send.

**Analogy**: Restaurant with no seating limit or reservation system. Chaos when 10,000 people show up at once.

**Why it's bad**:
- 🔴 API abuse / DoS attacks
- 🔴 Resource exhaustion (memory, CPU, database)
- 🔴 Cost explosion
- 🔴 Service unavailable for real users

### ✅ Solution: slowapi Rate Limiter

**Goal**: Limit requests per IP/client (e.g., 10 per minute).

### 📋 Implementation Steps

#### Step 1: Install slowapi (10min)
```bash
pip install slowapi==0.1.9
```

#### Step 2: Create rate limiter (30min)
```python
# Create: core/rate_limit.py

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/hour"]
)

async def rate_limit_handler(request, exc):
    """Return RFC 7807 error for rate limit."""
    return JSONResponse(
        status_code=429,
        content={
            "type": "/errors/RATE_LIMIT_EXCEEDED",
            "title": "Rate limit exceeded",
            "status": 429,
            "detail": "Too many requests. Retry in 60s.",
        },
        headers={"Retry-After": "60"}
    )
```

#### Step 3: Register in app (15min)
```python
# Update: main.py

from core.rate_limit import limiter, rate_limit_handler
from slowapi.errors import RateLimitExceeded

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
```

#### Step 4: Apply to endpoints (2h)
```python
# Update: api/routes/verify.py

from core.rate_limit import limiter

@router.post("/v1/verify")
@limiter.limit("10/minute")  # 10 req/min per client
async def verify_document(request: Request, ...):
    # ... existing code
```

#### Step 5: Testing (30min)
```python
def test_rate_limit():
    # Make 11 requests
    for i in range(11):
        resp = client.post("/v1/verify", ...)
    
    # 11th should be 429
    assert resp.status_code == 429
```

---

## Issue #4: Blocking PDF Operations

### 🤔 Simple Explanation

**Problem**: Counting PDF pages blocks the entire server.

**Analogy**: Waiter stops serving all customers to personally watch one dish being cooked. Everyone waits.

**Why it's bad**:
- 🔴 Server freezes during PDF operations
- 🔴 Other requests wait unnecessarily
- 🔴 Large PDFs cause timeouts
- 🔴 Poor performance

### ✅ Solution: Thread Pool Executor

**Goal**: Run PDF operations in background thread so server stays responsive.

### 📋 Implementation Steps

#### Step 1: Create async wrapper (30min)
```python
# Update: pipeline/orchestrator.py

def _count_pdf_pages_sync(pdf_path: str):
    """Runs in thread - OK to block."""
    import pypdf
    reader = pypdf.PdfReader(pdf_path)
    return len(reader.pages)

async def _count_pdf_pages_async(pdf_path: str):
    """Async version using thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,  # Default thread pool
        _count_pdf_pages_sync,
        pdf_path
    )
```

#### Step 2: Use in pipeline (30min)
```python
@stage("acquire")
async def _stage_acquire_async(self, ctx):
    # ... existing code ...
    
    if pdf:
        pages = await _count_pdf_pages_async(path)
        if pages > MAX_PDF_PAGES:
            raise StageError("PDF_TOO_MANY_PAGES")
```

#### Step 3: Testing (30min)
```python
@pytest.mark.asyncio
async def test_pdf_counting_async():
    # Verify it doesn't block event loop
    count_task = asyncio.create_task(_count_pdf_pages_async(path))
    await asyncio.sleep(0.1)  # Do other work
    result = await count_task
    assert result == 10
```

---

## Issue #5: High Code Complexity

### 🤔 Simple Explanation

**Problem**: `fio_match()` function has 104 lines and complexity 15 (should be <10).

**Analogy**: Recipe with 104 steps in one paragraph. Super confusing!

**Why it's bad**:
- 🔴 Hard to read and understand
- 🔴 Hard to test (one giant function)
- 🔴 Hard to debug when something breaks
- 🔴 Hard to modify safely

### ✅ Solution: Extract Strategy Functions

**Goal**: Break into small functions that each do ONE thing.

### 📋 Implementation Steps

#### Step 1: Extract matching strategies (2h)
```python
# Create: pipeline/processors/fio_matching_strategies.py

def try_exact_match(app_variants, doc_variants, variant_key):
    """Strategy 1: Try exact canonical match."""
    app_val = app_variants.get(variant_key)
    doc_val = doc_variants.get(variant_key)
    
    if app_val and doc_val and equals_canonical(app_val, doc_val):
        return True, {"matched_variant": variant_key, ...}
    return None

def try_lio_special_case(app_variants, doc_fio):
    """Strategy 2: L_IO raw form match."""
    # ... 15 lines
    return None

def try_fuzzy_match(app_val, doc_val, threshold):
    """Strategy 3: Fuzzy matching."""
    # ... 15 lines
    return None
```

#### Step 2: Refactor main function (1h)
```python
# Update: pipeline/processors/fio_matching.py

def fio_match(app_fio, doc_fio, fuzzy_threshold=85):
    """Main orchestrator - now simple!"""
    # Parse
    app_parts = parse_fio(app_fio)
    doc_parts = parse_fio(doc_fio)
    
    # Try strategies in order
    if result := try_exact_match(...):
        return result
    
    if result := try_lio_special_case(...):
        return result
    
    if result := try_fuzzy_match(...):
        return result
    
    return False, build_no_match_result(...)
```

**Benefits**: Each function <20 lines, complexity <5, easy to test individually.

---

## Issue #6: SRP Violation in DocumentProcessor

### 🤔 Simple Explanation

**Problem**: `DocumentProcessor` does too many things.

**Analogy**: One employee handles hiring, firing, payroll, and office supplies. Should be 4 separate jobs!

**Responsibilities**:
1. S3 client initialization
2. Pipeline runner initialization
3. Document processing
4. Kafka event processing

**Why it's bad**:
- 🔴 Changes to S3 affect document processing
- 🔴 Hard to test in isolation
- 🔴 Unclear what the class actually does

### ✅ Solution: Split into Focused Classes

**Goal**: One class per responsibility.

### 📋 Implementation Steps

#### Step 1: Create S3Service (1h)
```python
# Create: services/s3_service.py

class S3Service:
    """Handles S3 operations only."""
    
    def __init__(self, client: S3Client):
        self.client = client
    
    async def download_file(self, s3_path: str):
        """Download from S3, return local path."""
        tmp_file = tempfile.NamedTemporaryFile(delete=False)
        self.client.download_file(s3_path, tmp_file.name)
        return tmp_file.name
```

#### Step 2: Create DocumentService (1.5h)
```python
# Create: services/document_service.py

class DocumentService:
    """Handles document processing only."""
    
    def __init__(self, runner: PipelineRunner):
        self.runner = runner
    
    async def process_file(self, file_path, fio):
        """Process single file."""
        result = await self.runner.run_async(
            fio=fio,
            source_file_path=file_path,
            original_filename=os.path.basename(file_path)
        )
        return result
```

#### Step 3: Create KafkaService (1h)
```python
# Create: services/kafka_service.py

class KafkaService:
    """Handles Kafka event processing."""
    
    def __init__(self, s3: S3Service, doc: DocumentService):
        self.s3 = s3
        self.doc = doc
    
    async def process_event(self, event_data):
        """Download from S3 and process."""
        s3_path = event_data["s3_path"]
        local_path = await self.s3.download_file(s3_path)
        
        try:
            return await self.doc.process_file(local_path, fio)
        finally:
            os.unlink(local_path)
```

#### Step 4: Update routes (30min)
Use dependency injection to get services.

---

## Issue #7: Interface Segregation

### 🤔 Simple Explanation

**Problem**: `PipelineRunner` exposes too many internal methods.

**Analogy**: TV remote with 100 buttons when you only need 5. Confusing!

**Current**:
- `run()` ← what you actually use
- `_stage_acquire()` ← internal
- `_stage_ocr()` ← internal
- `_build_error_final_json()` ← internal
- 10+ more internal methods ← clutter

**Why it's bad**:
- 🔴 Unclear what's the actual API
- 🔴 Might accidentally call internal methods
- 🔴 Hard to maintain backward compatibility

### ✅ Solution: Proper Encapsulation

### 📋 Implementation Steps

#### Step 1: Rename internals (1h)
```python
# Update: pipeline/orchestrator.py

class PipelineRunner:
    # PUBLIC API - what users should call
    def run(self, ...):
        """Execute pipeline."""
        ...
    
    async def run_async(self, ...):
        """Async execution."""
        ...
    
    # PRIVATE - use double underscore
    def __stage_acquire(self, ctx):  # Was _stage_acquire
        """Internal stage."""
        ...
    
    def __stage_ocr(self, ctx):  # Was _stage_ocr
        ...
    
    def __build_error_json(self, ctx, code):  # Was _build_error_final_json
        ...
```

#### Step 2: Update internal calls (1h)
Update all internal calls to use `__method` instead of `_method`.

**Benefits**: Clear public API, name mangling prevents accidental access.

---

## Issue #8: Race Condition Prevention

### 🤔 Simple Explanation

**Problem**: Webhook status might be updated before database row exists.

**Status**: ✅ **ALREADY FIXED!**

The code already has proper fix:

```python
async def insert_run_then_webhook(...):
    """Atomically insert run then send webhook."""
    
    # 1. Insert row FIRST
    success = await insert_verification_run(final_json)
    if not success:
        return  # Don't send webhook if insert failed
    
    # 2. THEN update webhook status
    await send_webhook_and_persist(...)
```

**Why it's correct**:
- ✅ Database row guaranteed to exist before update
- ✅ No race condition
- ✅ Proper error handling

**No action needed!**

---

## Summary Table

| Issue | Status | Priority | Next Steps |
|-------|--------|----------|------------|
| 1. Global State | 🟡 TODO | HIGH | Start with DatabaseManager class |
| 2. Singleton | 🟡 TODO | MEDIUM | Remove global webhook_client |
| 3. Rate Limiting | 🟡 TODO | HIGH | Install slowapi, apply to routes |
| 4. Blocking PDF | 🟡 TODO | MEDIUM | Add async wrapper |
| 5. Complexity | 🟡 TODO | HIGH | Extract strategy functions |
| 6. SRP Violation | 🟡 TODO | HIGH | Split into 3 services |
| 7. Interface | 🟡 TODO | MEDIUM | Rename with __ prefix |
| 8. Race Condition | ✅ DONE | N/A | Already fixed |

---

## Recommended Order

### Week 1: Critical Security
1. **Rate Limiting** (3h) - Prevents DoS attacks
2. **Global State** (4h) - Enables proper testing

### Week 2: Code Quality
3. **Singleton** (2h) - Improves testability
4. **Blocking PDF** (1.5h) - Better performance

### Week 3: Refactoring
5. **Complexity** (3h) - Easier maintenance
6. **SRP Violation** (4h) - Better architecture
7. **Interface** (2h) - Cleaner API

**Total Effort**: ~20 hours over 3 weeks

---

## Testing Checklist

After each fix:
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing in development
- [ ] Performance benchmarks
- [ ] Code review
- [ ] Documentation updated

---

**Document Version**: 1.0  
**Last Updated**: 2025-12-25
