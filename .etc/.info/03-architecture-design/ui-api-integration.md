&lt;!-- STATUS: KEEP - This guide documents the UI-to-API integration architecture and is still relevant for understanding how the Streamlit UI calls the FastAPI service. Useful for onboarding and troubleshooting. --&gt;

# UI to API Integration Guide

## Overview

This guide explains how to modify the `main-dev` Streamlit UI to call the `/v1/verify` endpoint from the `fastapi-service` instead of running the pipeline locally.

## Current Architecture

### FastAPI Service (`fastapi-service`)
- **Location**: `/apps/fastapi-service/`
- **Main Endpoint**: `POST /v1/verify`
- **Purpose**: Standalone API service that wraps the document verification pipeline
- **Input**: 
  - `file`: PDF or image file (multipart/form-data)
  - `fio`: Full name (form field)
- **Output** (JSON):
  ```json
  {
    "run_id": "20251126_140523_abc12",
    "verdict": true,
    "errors": [],
    "processing_time_seconds": 12.4
  }
  ```

### Main-Dev UI (`main-dev`)
- **Location**: `/apps/main-dev/rb-ocr/`
- **Entry Point**: `app.py` (Streamlit application)
- **Current Behavior**: Calls `run_pipeline()` from `pipeline.orchestrator` directly
- **Purpose**: User interface for document upload and result visualization

---

## Migration Strategy

### Goal
Transform `main-dev/rb-ocr/app.py` from a **local pipeline executor** to a **pure UI client** that calls the FastAPI service.

### High-Level Changes

1. **Remove local pipeline execution** (lines 101-107 in `app.py`)
2. **Add HTTP client** to call FastAPI service
3. **Transform API response** to match current UI expectations
4. **Keep all UI/UX logic intact** (diagnostics, visualizations, timings)

---

## Implementation Steps

### Step 1: Add HTTP Client Dependency

Create or update `requirements.txt` in `main-dev/rb-ocr/`:

```txt
streamlit>=1.28.0
requests>=2.31.0
```

### Step 2: Modify `app.py`

#### A. Add imports at the top

```python
import requests
from typing import Optional
```

#### B. Add configuration constants (after imports, before page setup)

```python
# FastAPI service configuration
FASTAPI_SERVICE_URL = os.getenv("FASTAPI_SERVICE_URL", "http://localhost:8000")
VERIFY_ENDPOINT = f"{FASTAPI_SERVICE_URL}/v1/verify"
```

#### C. Create API client function

Add this function before the form section (around line 50):

```python
def call_verify_api(file_path: str, filename: str, fio: Optional[str]) -> dict:
    """
    Call the FastAPI /v1/verify endpoint.
    
    Args:
        file_path: Path to the uploaded file
        filename: Original filename
        fio: Full name (optional)
    
    Returns:
        dict: API response with run_id, verdict, errors, processing_time_seconds
    
    Raises:
        requests.HTTPError: If API call fails
    """
    with open(file_path, "rb") as f:
        files = {"file": (filename, f, "application/octet-stream")}
        data = {"fio": fio or ""}
        
        response = requests.post(
            VERIFY_ENDPOINT,
            files=files,
            data=data,
            timeout=120  # 2 minutes timeout
        )
        response.raise_for_status()
        return response.json()
```

#### D. Replace pipeline execution logic

**Current code (lines 100-107):**
```python
with st.spinner("Обрабатываем документ..."):
    result = run_pipeline(
        fio=fio or None,
        source_file_path=str(tmp_path),
        original_filename=uploaded_file.name,
        content_type=getattr(uploaded_file, "type", None),
        runs_root=RUNS_DIR,
    )
```

**New code:**
```python
with st.spinner("Обрабатываем документ..."):
    try:
        api_response = call_verify_api(
            file_path=str(tmp_path),
            filename=uploaded_file.name,
            fio=fio or None
        )
        
        # Transform API response to match expected format
        result = {
            "run_id": api_response["run_id"],
            "verdict": api_response["verdict"],
            "errors": api_response["errors"],
            "processing_time_seconds": api_response["processing_time_seconds"],
            # Note: API doesn't return these paths, so diagnostics won't be available
            "final_result_path": None,
        }
        
    except requests.exceptions.RequestException as e:
        st.error(f"Ошибка при вызове API: {str(e)}")
        st.stop()
```

#### E. Handle missing diagnostics

Since the API doesn't return file paths to `final_result.json`, `side_by_side.json`, etc., you have two options:

**Option 1: Disable diagnostics sections** (simplest)

Wrap all diagnostic code blocks (lines 126-228) in a condition:

```python
# Diagnostics: show final_result.json for full context
final_result_path = result.get("final_result_path")
if final_result_path:  # Will be None when using API
    # ... existing diagnostic code ...
```

**Option 2: Extend API to return diagnostics** (recommended for production)

Modify `fastapi-service` to optionally return diagnostic data in the response.

---

### Step 3: Remove Unused Imports

After migration, remove these imports from `app.py`:

```python
from pipeline.core.config import STAMP_ENABLED  # If not used elsewhere
from pipeline.orchestrator import run_pipeline  # No longer needed
from pipeline.core.settings import RUNS_DIR     # No longer needed
```

---

### Step 4: Environment Configuration

Create a `.env` file in `main-dev/rb-ocr/` (or configure via system environment):

```bash
# FastAPI service URL
FASTAPI_SERVICE_URL=http://localhost:8000

# For production deployment
# FASTAPI_SERVICE_URL=http://rb-ocr-api:8000
```

Load environment variables in `app.py`:

```python
from dotenv import load_dotenv
load_dotenv()  # Add this near the top of the file
```

Add to `requirements.txt`:
```txt
python-dotenv>=1.0.0
```

---

## Deployment Scenarios

### Scenario 1: Local Development

1. **Terminal 1** - Start FastAPI service:
   ```bash
   cd /apps/fastapi-service
   uvicorn main:app --reload --port 8000
   ```

2. **Terminal 2** - Start Streamlit UI:
   ```bash
   cd /apps/main-dev/rb-ocr
   streamlit run app.py
   ```

3. Access UI at `http://localhost:8501`

### Scenario 2: Docker Compose

Create `docker-compose.yml` in `/apps/`:

```yaml
version: '3.8'

services:
  fastapi-service:
    build: ./fastapi-service
    container_name: rb-ocr-api
    ports:
      - "8000:8000"
    volumes:
      - ./fastapi-service/runs:/app/runs
    environment:
      - LOG_LEVEL=INFO

  streamlit-ui:
    build: ./main-dev
    container_name: rb-ocr-ui
    ports:
      - "8501:8501"
    environment:
      - FASTAPI_SERVICE_URL=http://fastapi-service:8000
    depends_on:
      - fastapi-service
```

Create `Dockerfile` in `main-dev/`:

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY rb-ocr/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY rb-ocr/ .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

### Scenario 3: Production (Separate Servers)

If FastAPI and UI are on different servers:

```bash
# On UI server
export FASTAPI_SERVICE_URL=http://api-server.example.com:8000
streamlit run app.py
```

---

## Error Handling

### Connection Errors

Add robust error handling:

```python
def call_verify_api(file_path: str, filename: str, fio: Optional[str]) -> dict:
    try:
        with open(file_path, "rb") as f:
            files = {"file": (filename, f, "application/octet-stream")}
            data = {"fio": fio or ""}
            
            response = requests.post(
                VERIFY_ENDPOINT,
                files=files,
                data=data,
                timeout=120
            )
            response.raise_for_status()
            return response.json()
            
    except requests.exceptions.Timeout:
        raise Exception("API request timed out (>120s). Service may be overloaded.")
    except requests.exceptions.ConnectionError:
        raise Exception(f"Cannot connect to API at {VERIFY_ENDPOINT}. Is the service running?")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 500:
            raise Exception(f"API internal error: {e.response.json().get('detail', 'Unknown error')}")
        raise Exception(f"API error ({e.response.status_code}): {e.response.text}")
```

### Display errors in UI

```python
with st.spinner("Обрабатываем документ..."):
    try:
        api_response = call_verify_api(...)
        result = {...}
    except Exception as e:
        st.error(f"❌ Ошибка при обработке документа")
        st.exception(e)
        st.stop()
```

---

## Testing the Integration

### Test Checklist

- [ ] FastAPI service starts successfully (`http://localhost:8000/docs`)
- [ ] Health check works (`http://localhost:8000/health`)
- [ ] Streamlit UI loads without errors
- [ ] File upload works
- [ ] API call succeeds and returns verdict
- [ ] Errors are displayed correctly when verdict=False
- [ ] Processing time is shown
- [ ] Connection errors are handled gracefully
- [ ] Timeout errors are handled (test with large files)

### Manual Test

1. Start both services
2. Upload a test document via UI
3. Verify the response matches expected format
4. Check FastAPI logs for the request
5. Verify `run_id` is generated correctly

---

## Benefits of This Architecture

### Separation of Concerns
- **UI Layer** (`main-dev`): Pure presentation, no business logic
- **API Layer** (`fastapi-service`): All processing logic, reusable

### Scalability
- Scale UI and API independently
- Multiple UI instances can share one API
- API can be called by other clients (mobile apps, scripts, etc.)

### Maintainability
- Pipeline changes only affect `fastapi-service`
- UI changes don't require pipeline redeployment
- Easier to test components in isolation

### Deployment Flexibility
- Deploy UI and API on different servers
- Use load balancers for API
- Easier to implement caching, rate limiting, etc.

---

## Optional Enhancements

### 1. Add Loading Progress

```python
with st.spinner("Обрабатываем документ..."):
    progress_bar = st.progress(0)
    progress_bar.progress(25, text="Загрузка файла...")
    
    api_response = call_verify_api(...)
    progress_bar.progress(100, text="Готово!")
    time.sleep(0.5)
    progress_bar.empty()
```

### 2. Cache API Responses

```python
@st.cache_data(ttl=3600)
def call_verify_api_cached(file_bytes: bytes, filename: str, fio: str):
    # Save bytes to temp file and call API
    ...
```

### 3. Add Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def call_verify_api(file_path: str, filename: str, fio: Optional[str]) -> dict:
    ...
```

### 4. Display API Metadata

```python
st.sidebar.markdown("### API Info")
st.sidebar.text(f"Endpoint: {VERIFY_ENDPOINT}")
st.sidebar.text(f"Run ID: {result['run_id']}")
st.sidebar.text(f"Time: {result['processing_time_seconds']}s")
```

---

## Migration Checklist

- [ ] Install `requests` library in `main-dev`
- [ ] Add `FASTAPI_SERVICE_URL` configuration
- [ ] Implement `call_verify_api()` function
- [ ] Replace `run_pipeline()` call with API call
- [ ] Transform API response to match UI expectations
- [ ] Handle missing diagnostic paths
- [ ] Add error handling for API failures
- [ ] Remove unused imports
- [ ] Test locally with both services running
- [ ] Update deployment documentation
- [ ] Configure environment variables for production

---

## Troubleshooting

### Issue: "Connection refused"
**Solution**: Ensure FastAPI service is running on the expected port.

### Issue: "404 Not Found"
**Solution**: Check `VERIFY_ENDPOINT` URL is correct (`/v1/verify`).

### Issue: "Timeout"
**Solution**: Increase timeout value or optimize pipeline performance.

### Issue: "500 Internal Server Error"
**Solution**: Check FastAPI logs for detailed error messages.

### Issue: Missing diagnostics
**Solution**: Either disable diagnostic UI sections or extend API to return file paths.

---

## Summary

By following this guide, you will:

1. **Decouple** the UI from the pipeline logic
2. **Enable** the Streamlit app to call the FastAPI service
3. **Maintain** all existing UI features (verdict display, error messages, timings)
4. **Prepare** for scalable, production-ready deployment

The key change is replacing the direct `run_pipeline()` call with an HTTP request to `/v1/verify`, transforming the response to match the UI's expectations.
