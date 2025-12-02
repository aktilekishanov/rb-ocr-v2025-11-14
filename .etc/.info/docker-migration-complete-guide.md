# ULTIMATE GUIDE: Docker Migration for RB-OCR Services
## Complete Implementation from Start to Finish

**Date**: 2025-11-28 to 2025-12-02  
**Project**: RB Loan Deferment IDP - Docker Containerization  
**Objective**: Migrate FastAPI service and Streamlit UI from systemd/venv to Docker containers on offline Debian 12 server

---

## Table of Contents
1. [Project Context](#project-context)
2. [System Requirements](#system-requirements)
3. [Phase 0: Docker Availability Check](#phase-0-docker-availability-check)
4. [Phase 1: Dockerfile Creation](#phase-1-dockerfile-creation)
5. [Phase 2: Docker Compose Configuration](#phase-2-docker-compose-configuration)
6. [Phase 3: Building AMD64 Images](#phase-3-building-amd64-images)
7. [Phase 4: Fixing Healthchecks](#phase-4-fixing-healthchecks)
8. [Phase 5: Fixing Swagger UI URLs](#phase-5-fixing-swagger-ui-urls)
9. [Phase 6: Server Deployment](#phase-6-server-deployment)
10. [Phase 7: Verification](#phase-7-verification)
11. [Docker Architecture](#docker-architecture)
12. [Troubleshooting](#troubleshooting)

---

## Project Context

### What We Had (Before Docker)
- **FastAPI Service**: Running as systemd service with Gunicorn on port 8000
- **Streamlit UI**: Running manually or as systemd service on port 8501
- **Nginx**: Reverse proxy already configured with path-based routing
  - `/rb-ocr/api/` → FastAPI (localhost:8000)
  - `/rb-ocr/ui/` → Streamlit (localhost:8501)
- **Installation**: Python venv with manually installed dependencies

### What We Built (After Docker)
- **Dockerized Backend**: `rb-ocr-backend:latest` container running FastAPI + Gunicorn
- **Dockerized UI**: `rb-ocr-ui:latest` container running Streamlit
- **Docker Compose**: Orchestrates both services with health checks and dependencies
- **Platform**: Built for `linux/amd64` (server architecture)

### Key Benefits of Docker Migration
1. **Isolation**: Each service runs in its own container with dependencies
2. **Consistency**: Exact same environment on dev machine and server
3. **Easy Updates**: Rebuild image, export tarball, deploy
4. **Automatic Restart**: `restart: always` ensures services come back after crashes/reboots
5. **Health Monitoring**: Docker monitors health and restarts unhealthy containers
6. **No Venv Issues**: All dependencies baked into images

---

## System Requirements

### Development Machine (MacBook)
- **OS**: macOS (Apple Silicon M1/M2/M3 or Intel)
- **Tools**: Docker Desktop 28.5.1+
- **Architecture**: Will build for `linux/amd64` (cross-compilation)

### Server (Production)
- **OS**: Debian GNU/Linux 12 (bookworm)
- **Architecture**: x86_64 (AMD64)
- **Docker**: 28.5.1
- **Docker Compose**: v2.40.2
- **Network**: **NO internet access** (critical constraint!)
- **User**: `rb_admin`
- **Project Root**: `~/rb-loan-deferment-idp/`

---

## PHASE 0: Docker Availability Check

### Objective
Confirm Docker is already installed on the offline server to avoid manual installation

**Date**: 2025-11-28 17:44

---

### Step 0.1: Check Docker on Server

```bash
# On server via SSH
docker --version
docker compose version
```

**Expected Output**:
```
Docker version 28.5.1, build e180ab8
Docker Compose version v2.40.2
```

**Result**: ✅ Docker already installed! No offline installation needed.

**Documented in**: `server-important-info.md`

---

## PHASE 1: Dockerfile Creation

### Objective
Create Dockerfiles for both backend (FastAPI) and frontend (Streamlit)

**Date**: 2025-11-28 17:44-17:48

---

### Step 1.1: Create Backend Dockerfile

**File**: `fastapi-service/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create runs directory
RUN mkdir -p /app/runs && chmod 777 /app/runs

EXPOSE 8000

# Run with Gunicorn
CMD ["gunicorn", "main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

**Key Points**:
- Base: `python:3.11-slim` (lightweight Debian base)
- System deps: `tesseract-ocr` (OCR), `libgl1` (OpenCV), `curl` (healthchecks)
- **Why `libgl1` not `libgl1-mesa-glx`**: Debian Bookworm deprecated the old package
- **Why `curl`**: Required for Docker healthchecks
- Gunicorn with 4 workers for production concurrency

---

### Step 1.2: Create UI Dockerfile

**File**: `ui/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (if any needed for streamlit/pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
```

**Key Points**:
- `build-essential`: For compiling Python packages with C extensions
- `curl`: For Streamlit healthcheck
- Streamlit's built-in health endpoint: `/_stcore/health`
- Binds to `0.0.0.0` to accept connections from outside container

---

### Step 1.3: Create UI Requirements

**File**: `ui/requirements.txt`

```
streamlit>=1.28.0
requests>=2.31.0
python-dotenv>=1.0.0
```

**Minimal dependencies** - UI is now just a client calling the API

---

## PHASE 2: Docker Compose Configuration

### Objective
Create orchestration file to manage both services together

**Date**: 2025-11-28 17:48

---

### Step 2.1: Create docker-compose.yml

**File**: `docker-compose.yml` (in project root)

```yaml
version: '3.8'

services:
  backend:
    build: ./fastapi-service
    platform: linux/amd64
    image: rb-ocr-backend:latest
    container_name: rb-ocr-backend
    restart: always
    ports:
      - "8000:8000"
    volumes:
      - ./logs:/app/logs
      - ./runs:/app/runs
    environment:
      - TZ=Asia/Almaty
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  ui:
    build: ./ui
    platform: linux/amd64
    image: rb-ocr-ui:latest
    container_name: rb-ocr-ui
    restart: always
    ports:
      - "8501:8501"
    environment:
      - TZ=Asia/Almaty
      - FASTAPI_SERVICE_URL=http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/api
    depends_on:
      backend:
        condition: service_healthy
```

**Key Configuration Explained**:

1. **`platform: linux/amd64`** (CRITICAL!):
   - Forces build for server architecture
   - Required on Apple Silicon Macs (arm64)
   - Without this: builds arm64 images that won't run on server

2. **`restart: always`**:
   - Auto-restart on crash
   - Auto-start on server reboot
   - Production-grade reliability

3. **`volumes`**:
   - `./logs:/app/logs` - Persist logs outside container
   - `./runs:/app/runs` - Persist processing artifacts

4. **`healthcheck`**:
   - Backend: Checks `/health` endpoint every 30s
   - Marks container "unhealthy" if check fails
   - Docker can restart unhealthy containers

5. **`depends_on` with `condition: service_healthy`**:
   - UI waits until backend is healthy
   - Prevents UI from starting before API is ready

---

## PHASE 3: Building AMD64 Images

### Objective
Build Docker images on Mac for Linux AMD64 architecture

**Date**: 2025-11-28 17:48-18:00

---

### Step 3.1: First Build Attempt (FAILED)

```bash
# On MacBook
cd ~/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps
docker compose build
```

**Error**:
```
E: Package 'libgl1-mesa-glx' has no installation candidate
```

**Root Cause**: Debian Bookworm (base image) deprecated `libgl1-mesa-glx`  
**Fix**: Changed to `libgl1` in Dockerfile

---

### Step 3.2: Second Build Attempt (Wrong Architecture)

After fixing library name:

```bash
docker compose build
```

**Success**: Images built!

**Verification**:
```bash
docker inspect rb-ocr-backend:latest --format '{{.Architecture}}'
```

**Output**: `arm64` ❌

**Problem**: Built for Mac's native ARM64 architecture, won't work on AMD64 server!

---

### Step 3.3: Adding Platform Specification

**Fix**: Added `platform: linux/amd64` to `docker-compose.yml`

```yaml
services:
  backend:
    platform: linux/amd64  # <-- Added this
```

**Rebuild**:
```bash
docker compose build
```

**Verification**:
```bash
docker inspect rb-ocr-backend:latest --format '{{.Architecture}}'
```

**Output**: `amd64` ✅

**Success**: Images now built for correct architecture!

---

### Step 3.4: Export Images to Tarballs

```bash
# Save images
docker save -o rb-ocr-backend.tar rb-ocr-backend:latest
docker save -o rb-ocr-ui.tar rb-ocr-ui:latest

# Compress
gzip -f rb-ocr-backend.tar
gzip -f rb-ocr-ui.tar

# Verify
ls -lh *.tar.gz
```

**Output**:
```
-rw-------  192M rb-ocr-backend.tar.gz
-rw-------  269M rb-ocr-ui.tar.gz
```

**Total**: 461 MB (manageable for offline transfer)

---

## PHASE 4: Fixing Healthchecks

### Objective
Fix initial deployment failure due to missing `curl` in containers

**Date**: 2025-12-01 12:00

---

### Step 4.1: First Deployment Attempt (Server)

**Commands**:
```bash
# On server
cd ~/rb-loan-deferment-idp/docker-deploy
gunzip -c rb-ocr-backend.tar.gz | sudo docker load
gunzip -c rb-ocr-ui.tar.gz | sudo docker load

cd ~/rb-loan-deferment-idp
sudo docker compose up -d
```

**Result**:
```
✘ Container rb-ocr-backend  Error
dependency failed to start: container rb-ocr-backend is unhealthy
```

---

### Step 4.2: Investigating the Failure

```bash
sudo docker compose logs backend
```

**Logs showed**:
```
[2025-12-01 11:59:02] [INFO] Starting gunicorn 21.2.0
[2025-12-01 11:59:02] [INFO] Listening at: http://0.0.0.0:8000
[2025-12-01 11:59:03] [INFO] Application startup complete.
```

**Analysis**:
- ✅ Application started successfully
- ❌ Container marked as "unhealthy"

**Root Cause**: Healthcheck command `curl -f http://localhost:8000/health` fails because `curl` is NOT installed in `python:3.11-slim` base image!

---

### Step 4.3: Fix - Install curl in Dockerfiles

**Backend Dockerfile** (line 10):
```dockerfile
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    curl \              # <-- Added
    && rm -rf /var/lib/apt/lists/*
```

**UI Dockerfile** (line 8):
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \              # <-- Added
    && rm -rf /var/lib/apt/lists/*
```

---

### Step 4.4: Rebuild with curl

```bash
# On MacBook
docker compose build
docker save -o rb-ocr-backend.tar rb-ocr-backend:latest
docker save -o rb-ocr-ui.tar rb-ocr-ui:latest
gzip -f rb-ocr-backend.tar
gzip -f rb-ocr-ui.tar
```

---

### Step 4.5: Second Deployment Attempt (Server)

**Cleanup**:
```bash
sudo docker compose down
sudo docker rmi rb-ocr-backend:latest
sudo docker rmi rb-ocr-ui:latest
```

**Load & Deploy**:
```bash
cd ~/rb-loan-deferment-idp/docker-deploy
gunzip -c rb-ocr-backend.tar.gz | sudo docker load
gunzip -c rb-ocr-ui.tar.gz | sudo docker load

cd ~/rb-loan-deferment-idp
sudo docker compose up -d
```

**Result**:
```
✔ Container rb-ocr-backend  Healthy
✔ Container rb-ocr-ui       Started
```

**Success**: ✅ Healthchecks now passing!

---

## PHASE 5: Fixing Swagger UI URLs

### Objective
Fix Swagger UI generating incorrect API request URLs

**Date**: 2025-12-01 13:59

---

### Step 5.1: Testing Swagger UI

**URL**: `http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/docs`

**Problem**: When clicking "Try it out" on `POST /v1/verify`, Swagger generated:
```
http://rb-ocr-dev-app-uv01.fortebank.com/v1/verify
```

**Expected**:
```
http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/api/v1/verify
```

**Result**: 404 Not Found from Nginx (missing `/rb-ocr/api` prefix)

---

### Step 5.2: Root Cause Analysis

Swagger UI reads the API's base path from FastAPI's configuration. When FastAPI is behind a reverse proxy at `/rb-ocr/api/`, it needs to know this via `root_path` parameter.

**What we had**:
```python
app = FastAPI(
    title="[DEV] RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

**Missing**: `root_path` configuration!

---

### Step 5.3: Fix - Add root_path

**File**: `fastapi-service/main.py`

```python
app = FastAPI(
    title="[DEV] RB-OCR Document Verification API",
    version="1.0.0",
    description="Validates loan deferment documents",
    docs_url="/docs",
    redoc_url="/redoc",
    root_path="/rb-ocr/api",  # <-- Added this!
)
```

**What `root_path` does**:
1. Tells FastAPI it's mounted at `/rb-ocr/api`
2. Swagger UI uses this to generate correct URLs
3. OpenAPI schema reflects the full path

---

### Step 5.4: Rebuild Backend Only

```bash
# On MacBook
docker compose build backend
docker save -o rb-ocr-backend.tar rb-ocr-backend:latest
gzip -f rb-ocr-backend.tar
```

---

### Step 5.5: Deploy Updated Backend

```bash
# On server
sudo docker compose down
sudo docker rmi rb-ocr-backend:latest

cd ~/rb-loan-deferment-idp/docker-deploy
gunzip -c rb-ocr-backend.tar.gz | sudo docker load

cd ~/rb-loan-deferment-idp
sudo docker compose up -d backend
```

---

### Step 5.6: Verification

**Testing Swagger UI**:
1. Open: `http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/docs`
2. Click `POST /v1/verify` → "Try it out"
3. Upload test PDF, enter FIO
4. Click "Execute"

**Request URL now shows**:
```
http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/api/v1/verify
```

**Response**: 200 OK ✅

**Success**: Swagger UI now generates correct URLs!

---

## PHASE 6: Server Deployment

### Objective
Final production deployment with all fixes applied

**Date**: 2025-12-02 09:36-09:56

---

### Step 6.1: Comprehensive Rebuild

**All changes included**:
- ✅ Platform: `linux/amd64`
- ✅ Healthchecks: `curl` installed
- ✅ Swagger URLs: `root_path="/rb-ocr/api"`

```bash
# On MacBook
docker compose build
docker save -o rb-ocr-backend.tar rb-ocr-backend:latest
docker save -o rb-ocr-ui.tar rb-ocr-ui:latest
gzip -f rb-ocr-backend.tar
gzip -f rb-ocr-ui.tar

ls -lh *.tar.gz
```

**Output**:
```
-rw-------  192M Dec  2 09:36 rb-ocr-backend.tar.gz
-rw-------  269M Dec  2 09:36 rb-ocr-ui.tar.gz
```

---

### Step 6.2: Clean Server Deployment

**Full cleanup**:
```bash
# On server
cd ~/rb-loan-deferment-idp

# Stop all containers
sudo docker compose down

# Verify stopped
sudo docker ps -a | grep rb-ocr

# Remove old images
sudo docker rmi rb-ocr-backend:latest
sudo docker rmi rb-ocr-ui:latest

# Verify cleanup
sudo docker images | grep rb-ocr
```

---

### Step 6.3: Load New Images

```bash
cd ~/rb-loan-deferment-idp/docker-deploy

# Verify tarballs
ls -lh *.tar.gz

# Load backend
sudo gunzip -c rb-ocr-backend.tar.gz | sudo docker load

# Load UI
sudo gunzip -c rb-ocr-ui.tar.gz | sudo docker load

# Verify loaded
sudo docker images | grep rb-ocr
```

**Expected**: Both images show recent timestamp

---

### Step 6.4: Start Services

```bash
cd ~/rb-loan-deferment-idp

# Start in detached mode
sudo docker compose up -d

# Monitor status
sudo docker compose ps
```

**Expected Output**:
```
NAME             STATUS
rb-ocr-backend   Up 45s (healthy)
rb-ocr-ui        Up 14s (healthy)
```

**Success**: ✅ Both containers healthy!

---

## PHASE 7: Verification

### Objective
Comprehensive testing of deployed services

**Date**: 2025-12-01 13:54

---

### Step 7.1: Container Health Checks

```bash
sudo docker compose ps
```

**Output**:
```
NAME             STATUS                   PORTS
rb-ocr-backend   Up 3 minutes (healthy)   0.0.0.0:8000->8000/tcp
rb-ocr-ui        Up 2 minutes (healthy)   0.0.0.0:8501->8501/tcp
```

✅ **Both containers healthy**

---

### Step 7.2: API Health Check

```bash
# Local
curl http://localhost:8000/health

# Via Nginx
curl http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/api/health
```

**Expected Response**:
```json
{"status":"healthy","service":"rb-ocr-api","version":"1.0.0"}
```

✅ **API responding correctly**

---

### Step 7.3: Browser Testing

#### Test 1: Swagger UI
**URL**: `http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/docs`

**Steps**:
1. Open Swagger UI
2. Click `POST /v1/verify`
3. Click "Try it out"
4. Upload test PDF
5. Enter FIO
6. Click "Execute"

**Verification**:
- Request URL: `http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/api/v1/verify` ✅
- Response: 200 OK with JSON verdict ✅

---

#### Test 2: Streamlit UI
**URL**: `http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/ui/`

**Steps**:
1. Upload test document
2. Enter FIO
3. Click "Загрузить и распознать"
4. Wait for processing

**Result**: ✅ Document processed, verdict displayed

---

### Step 7.4: Log Verification

```bash
sudo docker compose logs backend | tail -30
sudo docker compose logs ui | tail -30
```

**Logs show**:
- Gunicorn started with 4 workers ✅
- Requests processed successfully ✅
- No errors ✅

**Final Verification**: ✅ All tests passing!

---

## Docker Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Nginx (Port 80)                      │
│         rb-ocr-dev-app-uv01.fortebank.com               │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
        ▼                       ▼
┌──────────────┐        ┌──────────────┐
│/rb-ocr/api/  │        │ /rb-ocr/ui/  │
└──────┬───────┘        └──────┬───────┘
       │                       │
       ▼                       ▼
┌──────────────────┐   ┌──────────────────┐
│  rb-ocr-backend  │   │   rb-ocr-ui      │
│  Container       │   │   Container      │
│                  │   │                  │
│  Gunicorn:8000   │◄──│  Streamlit:8501  │
│  4 workers       │   │                  │
│                  │   │  (HTTP client)   │
└──────────────────┘   └──────────────────┘
        │
        ▼
┌──────────────────┐
│  Pipeline Logic  │
│  OCR + LLM       │
└──────────────────┘
```

### Container Details

#### Backend Container (`rb-ocr-backend`)
- **Base Image**: `python:3.11-slim` (Debian Bookworm)
- **Port**: 8000
- **Process**: Gunicorn with 4 Uvicorn workers
- **Volumes**: 
  - `./logs:/app/logs` (logs persistence)
  - `./runs:/app/runs` (processing artifacts)
- **Health**: `curl http://localhost:8000/health` every 30s
- **Restart**: Always (even after server reboot)

#### UI Container (`rb-ocr-ui`)
- **Base Image**: `python:3.11-slim`
- **Port**: 8501
- **Process**: Streamlit server
- **Dependencies**: Only `streamlit`, `requests`, `python-dotenv`
- **Health**: `curl http://localhost:8501/_stcore/health`
- **Environment**: `FASTAPI_SERVICE_URL` points to FastAPI via Nginx

### Network Flow

1. **User Request** → Nginx → `/rb-ocr/ui/`
2. **UI loads** from `rb-ocr-ui` container
3. **User uploads file** → Streamlit sends HTTP POST to FastAPI URL
4. **Request goes through Nginx** → `/rb-ocr/api/v1/verify`
5. **Backend processes** → OCR → LLM → Validation
6. **Response** → Nginx → UI → User sees result

---

## Troubleshooting

### Issue 1: Container Marked as "Unhealthy"

**Symptom**:
```
sudo docker compose ps
NAME             STATUS
rb-ocr-backend   Up 2 hours (unhealthy)
```

**Diagnosis**:
```bash
sudo docker inspect rb-ocr-backend | grep -A 10 Health
```

**Common Causes**:
1. **Missing curl**: Healthcheck command fails
   - **Fix**: Add `curl` to Dockerfile
2. **Application not starting**: Check logs
   ```bash
   sudo docker compose logs backend
   ```
3. **Wrong health endpoint**: Verify endpoint exists
   ```bash
   docker exec rb-ocr-backend curl http://localhost:8000/health
   ```

---

### Issue 2: Wrong Architecture (arm64 vs amd64)

**Symptom**: Container fails to start on server with exec format error

**Diagnosis**:
```bash
docker inspect rb-ocr-backend:latest --format '{{.Architecture}}'
```

**If shows `arm64`**:
- **Cause**: Built on Apple Silicon without platform specification
- **Fix**: Add `platform: linux/amd64` to docker-compose.yml, rebuild

---

### Issue 3: Swagger UI Shows Wrong URLs

**Symptom**: API calls from Swagger fail with 404

**Diagnosis**: Check Request URL in Swagger UI network tab

**If missing `/rb-ocr/api` prefix**:
- **Cause**: FastAPI `root_path` not configured
- **Fix**: Add `root_path="/rb-ocr/api"` to FastAPI initialization

---

### Issue 4: Cannot Access UI/API from Browser

**Diagnosis**:
```bash
# Check containers running
sudo docker compose ps

# Check port binding
sudo netstat -tlnp | grep -E '8000|8501'

# Check Nginx
sudo systemctl status nginx

# Test locally
curl http://localhost:8000/health
curl http://localhost:8501/_stcore/health
```

**Common Fixes**:
- Restart containers: `sudo docker compose restart`
- Check Nginx config: `/etc/nginx/sites-available/rb-ocr-dev-app-uv01`
- Reload Nginx: `sudo systemctl reload nginx`

---

### Issue 5: File Uploads Failing

**Symptom**: UI shows error when uploading files

**Diagnosis**:
```bash
# Check backend logs
sudo docker compose logs backend -f

# Check permissions on runs directory
ls -la ~/rb-loan-deferment-idp/runs
```

**Fixes**:
- Ensure `/app/runs` has write permissions (chmod 777 in Dockerfile)
- Check volume mount in docker-compose.yml

---

## Docker Operations Cheat Sheet

### Daily Operations

```bash
# Check status
sudo docker compose ps

# View logs (real-time)
sudo docker compose logs -f

# View logs (specific service)
sudo docker compose logs backend
sudo docker compose logs ui

# Restart all services
sudo docker compose restart

# Restart specific service
sudo docker compose restart backend

# Stop all
sudo docker compose down

# Start all
sudo docker compose up -d
```

### Image Management

```bash
# List images
sudo docker images

# Remove image
sudo docker rmi rb-ocr-backend:latest

# Clean up unused images
sudo docker image prune
```

### Container Management

```bash
# Execute command in container
sudo docker exec rb-ocr-backend ls -la /app

# Get shell in container
sudo docker exec -it rb-ocr-backend /bin/bash

# View container details
sudo docker inspect rb-ocr-backend
```

---

## Key Learnings

### 1. Architecture Matters
Always specify `platform: linux/amd64` when building on Apple Silicon for Linux servers. Without it, Docker builds native arm64 images that won't run on AMD64.

### 2. Healthchecks Need Tools
Debian slim base images don't include `curl`. If using curl-based healthchecks, explicitly install it in Dockerfile.

### 3. Reverse Proxy Configuration
When FastAPI is behind a reverse proxy with path prefix, use `root_path` to ensure correct URL generation in Swagger UI and OpenAPI schema.

### 4. Docker Runs Independently
Once `docker compose up -d` runs on server, containers continue running even after:
- SSH disconnection
- Workstation shutdown
- Network issues

Containers only stop when:
- Explicitly stopped (`docker compose down`)
- The system is shut down (but they auto-restart on boot with `restart: always`)

### 5. Transfer vs Build
For offline servers:
- **Build locally** (with internet)
- **Export to tarball** (`docker save`)
- **Transfer** (USB, network share, etc.)
- **Load on server** (`docker load`)

This is more reliable than trying to build on the offline server.

---

## File Inventory

### Created/Modified Files

**Dockerfiles**:
- `fastapi-service/Dockerfile` (33 lines)
- `ui/Dockerfile` (21 lines)

**Configuration**:
- `docker-compose.yml` (32 lines)
- `ui/requirements.txt` (3 lines)

**Modified**:
- `fastapi-service/main.py` (added `root_path="/rb-ocr/api"`)

**Build Artifacts**:
- `rb-ocr-backend.tar.gz` (192 MB)
- `rb-ocr-ui.tar.gz` (269 MB)

---

## Summary

We successfully migrated the RB-OCR application from systemd/venv to Docker containers, overcoming several challenges:

1. ✅ Built AMD64 images on Apple Silicon Mac
2. ✅ Fixed healthcheck failures by installing curl
3. ✅ Fixed Swagger UI URL generation with root_path
4. ✅ Deployed to offline server via tarball transfer
5. ✅ Achieved production-ready deployment with auto-restart and health monitoring

**Final Result**: Both services running in Docker with professional-grade orchestration, health monitoring, and automatic recovery.

**Benefits Achieved**:
- Consistent environment (dev = prod)
- Easy updates (rebuild → transfer → deploy)
- Automatic restart on failure/reboot
- Better resource isolation
- Simplified dependency management

---

**Date Completed**: 2025-12-02  
**Status**: ✅ Production Ready  
**Containers**: Running, Healthy, Auto-restarting
