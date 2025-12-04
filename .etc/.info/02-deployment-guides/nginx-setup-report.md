# Nginx Setup & Configuration Report

**Date**: 2025-11-28  
**Server**: rb-ocr-dev-app-uv01  
**Issue**: Installing and configuring Nginx on an offline server for FastAPI and Streamlit  
**Status**: ✅ RESOLVED

---

## Executive Summary

Successfully installed Nginx on an offline Ubuntu server, configured it as a reverse proxy for both FastAPI (production API) and Streamlit (testing UI), and resolved issues related to IPv6, path-based routing, and Swagger UI integration.

---

## Problem Description

### Initial State
- **Server**: `rb-ocr-dev-app-uv01` (Offline, no internet access)
- **Goal**: Expose FastAPI service and Streamlit UI via domain `rb-ocr-dev-app-uv01.fortebank.com`
- **Constraint**: Cannot use `apt install nginx` directly due to lack of internet access.

### Challenges Encountered
1. **Missing Nginx**: Server had no web server installed.
2. **IPv6 Error**: Nginx failed to start due to IPv6 configuration in default site.
3. **Routing Strategy**: Needed a strategy to support multiple future projects on the same server.
4. **Swagger UI 404**: Interactive API docs failed to load `openapi.json` due to path prefix issues.

---

## Solution Steps

### Phase 1: Offline Installation

**Strategy**: Download packages on a connected server (colleague's server) and transfer them.

1. **Download Packages (on connected server)**:
   ```bash
   mkdir ~/nginx-packages
   cd ~/nginx-packages
   apt-get download nginx nginx-common nginx-core
   tar -czf nginx-packages.tar.gz *.deb
   ```

2. **Transfer & Install (on offline server)**:
   - Transferred `nginx-packages.tar.gz` to `rb-ocr-dev-app-uv01`.
   - Extracted and installed:
     ```bash
     sudo dpkg -i nginx-common_*.deb
     sudo dpkg -i nginx_*.deb
     ```

### Phase 2: Troubleshooting Startup Failure

**Issue**: `nginx.service` failed to start.
**Error**: `nginx: [emerg] socket() [::]:80 failed (97: Address family not supported by protocol)`
**Cause**: Default config tried to bind to IPv6 `[::]:80`, but IPv6 is disabled on the server.

**Fix**:
Commented out IPv6 listen directives in `/etc/nginx/sites-available/default`:
```nginx
# listen [::]:80 default_server;
```

### Phase 3: Configuration Strategy

**Decision**: Adopted **Path-Based Routing** to support multiple future projects without DNS changes.

**Structure**:
- `/rb-ocr/api/` → FastAPI Service (Production)
- `/rb-ocr/ui/` → Streamlit UI (Temporary Testing)
- `/rb-ocr/docs` → API Documentation
- `/rb-ocr/health` → Health Check

**Configuration File**: `/etc/nginx/sites-available/rb-ocr-dev-app-uv01`

```nginx
server {
    listen 80;
    server_name rb-ocr-dev-app-uv01.fortebank.com;

    # FastAPI Service
    location /rb-ocr/api/ {
        proxy_pass http://127.0.0.1:8000/;
        # ... proxy headers ...
    }

    # Streamlit UI
    location /rb-ocr/ui/ {
        proxy_pass http://127.0.0.1:8501/;
        # ... WebSocket headers ...
    }
}
```

### Phase 4: Fixing Swagger UI

**Issue**: Swagger UI at `/rb-ocr/docs` failed to load API definition (404 on `/openapi.json`).
**Cause**: 
1. FastAPI didn't know it was served under a prefix (`/rb-ocr/api`).
2. Swagger UI defaults to looking for `openapi.json` at the root.

**Fix Part 1: Nginx Root Route**
Added a specific route for `openapi.json` at the root level in Nginx:
```nginx
location = /openapi.json {
    proxy_pass http://127.0.0.1:8000/openapi.json;
}
```

**Fix Part 2: FastAPI Configuration**
Updated `main.py` to inform FastAPI about the root path:
```python
app = FastAPI(
    # ...
    root_path="/rb-ocr/api",  # Added this
)
```

---

## Final Configuration Summary

### URL Structure
| URL | Service | Port | Note |
|-----|---------|------|------|
| `/rb-ocr/api/` | FastAPI | 8000 | Production API |
| `/rb-ocr/ui/` | Streamlit | 8501 | Testing UI |
| `/rb-ocr/docs` | Swagger UI | 8000 | API Docs |
| `/rb-ocr/health` | Health Check | 8000 | Monitoring |

### Key Files
- **Nginx Config**: `/etc/nginx/sites-available/rb-ocr-dev-app-uv01`
- **FastAPI App**: `~/rb-loan-deferment-idp/fastapi-service/main.py`

### Verification
- **Curl Test**:
  ```bash
  curl -X POST http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/api/v1/verify ...
  ```
  Result: `200 OK` ✅

---

## Key Learnings

1. **Offline Nginx Install**: `apt-get download` is a reliable way to get `.deb` files for offline installation.
2. **IPv6 on Servers**: Always check if IPv6 is enabled before using `listen [::]:80`.
3. **Path-Based Routing**: Using prefixes (e.g., `/rb-ocr/`) is better for single-server multi-project deployments than subdomains.
4. **FastAPI behind Proxy**: Always set `root_path` in `FastAPI()` when running behind a reverse proxy with a path prefix, otherwise Swagger UI will break.

---

## Quick Reference Commands

**Reload Nginx**:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

**Restart FastAPI**:
```bash
# Assuming running manually
Ctrl+C
uvicorn main:app --host 127.0.0.1 --port 8000
```

**Check Logs**:
```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```
