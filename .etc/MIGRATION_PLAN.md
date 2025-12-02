# Migration Plan: RB-OCR FastAPI Service

**Objective**: Migrate the FastAPI service and its dependencies to a new offline Linux server.
**Prerequisites**: 
- SSH access to the new server.
- `sudo` privileges on the server.
- Python 3.11+ installed on the server.

---

## Phase 1: Transfer Files

**Goal**: Move the application code and offline dependencies to the server.

### 1.1 Prepare Local Files
Ensure you have the following directories on your local machine:
- `apps/fastapi-service/` (The application code)
- `apps/.rb-ocr-dependencies/` (The offline wheels)

### 1.2 Transfer to Server
Use `scp` or drag-and-drop via VS Code to upload these folders to the server.
Recommended path on server: `~/apps/`

**Target Structure on Server**:
```
/home/<username>/
├── .rb-ocr-dependencies/   # Directory with .whl files
└── apps/
    └── fastapi-service/    # Application code
```

### 1.1 Prepare Build Context
**Action**: Run in `apps/` directory.
```bash
# 1. Update requirements
cp UNIFIED_REQUIREMENTS.txt fastapi-service/requirements.txt

# 2. Copy wheels to build context
cp -r unified-wheels fastapi-service/packages
```

### 1.2 Update Dockerfile
**Action**: Modify `apps/fastapi-service/Dockerfile` to use local wheels.
Change the install section to:
```dockerfile
COPY requirements.txt .
COPY packages /tmp/packages
# Flatten wheels for pip
RUN mkdir /packages && find /tmp/packages -name "*.whl" -exec cp {} /packages/ \;
RUN pip install --no-cache-dir --no-index --find-links /packages -r requirements.txt
```

### 1.3 Build Image
**Action**: Run in `apps/fastapi-service/` directory.
```bash
cd fastapi-service/
docker build --platform linux/amd64 -t rb-ocr-service:v1 .
```
### 1.3 Verify Transfer
**Action**: Run on server terminal.
```bash
ls -l ~/apps/fastapi-service
ls -l ~/.rb-ocr-dependencies
```
**Verification**: Ensure all files are present and file sizes look correct.

---

## Phase 2: Environment Setup

**Goal**: Create a Python virtual environment and install dependencies without internet.

### 2.1 Check Python Version
**Action**:
```bash
python3 --version
```
**Verification**: Should be Python 3.11 or higher.

### 2.2 Create Virtual Environment
**Action**:
```bash
cd ~/apps/fastapi-service
python3 -m venv .venv
```

### 2.3 Install Dependencies (Offline)
**Action**:
```bash
source .venv/bin/activate

# Install using local wheels
pip install --no-index --find-links ~/.rb-ocr-dependencies/ -r requirements.txt
```
**Verification**:
```bash
pip list
# Should show fastapi, uvicorn, gunicorn, rapidfuzz, etc.
```

### 2.4 Test Imports
**Action**:
```bash
python3 -c "from pipeline.orchestrator import run_pipeline; from api.schemas import VerifyResponse; print('✅ Imports OK')"
```
**Verification**: Output should be `✅ Imports OK`.

---

## Phase 3: Service Configuration

**Goal**: Configure systemd to run the service automatically.

### 3.1 Update Service File (If Needed)
**Action**: Check `system/rb-ocr-fastapi.service`.
The file currently assumes:
- User: `rb_admin2`
- Path: `/home/rb_admin2/apps/fastapi-service`

**If your username is different**:
Edit `system/rb-ocr-fastapi.service` and replace `rb_admin2` with your actual username (run `whoami` to check).
Also update the paths if you placed the files somewhere else.

### 3.2 Run Deployment Script
**Action**:
```bash
chmod +x deploy.sh
./deploy.sh
```
**What this does**:
- Verifies dependencies.
- Creates log directory `/var/log/rb-ocr-api`.
- Copies service file to `/etc/systemd/system/`.
- Enables and starts the service.

**Verification**:
The script should end with `✅ Deployment complete!`.

---

## Phase 4: Verification

**Goal**: Ensure the service is running and responding to requests.

### 4.1 Check Service Status
**Action**:
```bash
sudo systemctl status rb-ocr-fastapi
```
**Verification**: Status should be `active (running)`.

### 4.2 Check Logs
**Action**:
```bash
sudo tail -f /var/log/rb-ocr-api/error.log
```
**Verification**: Should show Gunicorn/Uvicorn starting up without errors.

### 4.3 Test API Endpoint
**Action**:
```bash
curl -X GET http://localhost:8001/health
```
**Verification**:
Response should be:
```json
{"status":"healthy","service":"rb-ocr-api","version":"1.0.0"}
```

---

## Rollback Plan

If deployment fails:
1. Stop service: `sudo systemctl stop rb-ocr-fastapi`
2. Check logs: `cat /var/log/rb-ocr-api/error.log`
3. Fix issues (e.g., missing dependencies, wrong paths).
4. Re-run `./deploy.sh`.
