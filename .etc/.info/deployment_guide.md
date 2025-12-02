# RB-OCR Deployment Guide (Docker Migration)

**Date**: 2025-12-01
**Target Server**: `rb-ocr-dev-app-uv01` (Offline)
**Architecture**: `linux/amd64`

---

## 1. What Has Been Done ✅

We have successfully transformed the application from a local script to a production-ready, containerized microservices architecture.

### 🏗️ Architecture Changes
*   **Nginx Reverse Proxy**: Configured path-based routing (`/rb-ocr/api/`, `/rb-ocr/ui/`) to support multiple projects on one server.
*   **UI/Backend Separation**: Refactored Streamlit (`ui`) to be a pure client that calls the FastAPI (`backend`) via HTTP.
*   **Containerization**: Created Dockerfiles for both services and a `docker-compose.yml` orchestrator.
*   **Offline Build**: Built `linux/amd64` compatible Docker images locally to bypass the server's lack of internet access.

### 📦 Artifacts Prepared
You have the following files ready for transfer:
1.  `rb-ocr-backend.tar.gz` (Backend Image)
2.  `rb-ocr-ui.tar.gz` (Frontend Image)
3.  `docker-compose.yml` (Configuration)

---

## 2. What To Do Now (Deployment Steps) 🚀

Follow these steps on your server to deploy the new version.

### Step 1: Transfer Files
Copy the 3 artifacts listed above to your server, for example to `~/rb-loan-deferment-idp/docker-deploy/`.

### Step 2: Clean Up Old Services
Stop any manually running instances or systemd services to free up ports 8000 and 8501.
```bash
# If running manually:
# Press Ctrl+C in the terminals running uvicorn or streamlit

# If using systemd:
sudo systemctl stop rb-ocr-fastapi
# sudo systemctl disable rb-ocr-fastapi  # Optional: prevent auto-start
```

### Step 3: Load Docker Images
Import the offline images into the server's Docker registry.
```bash
cd ~/rb-loan-deferment-idp/docker-deploy

# Load Backend
gunzip -c rb-ocr-backend.tar.gz | docker load

# Load UI
gunzip -c rb-ocr-ui.tar.gz | docker load
```

### Step 4: Start Services
Launch the application stack.
```bash
docker compose up -d
```

---

## 3. How To Test (Verification) 🧪

### A. Check Containers
Verify both containers are running and healthy.
```bash
docker compose ps
```
*Expected Output*: `rb-ocr-backend` and `rb-ocr-ui` should have Status `Up`.

### B. Check Logs
Ensure there are no startup errors.
```bash
docker compose logs -f
```

### C. Functional Testing (Browser)

1.  **API Documentation (Swagger UI)**
    *   URL: `http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/docs`
    *   *Action*: Check if the page loads.

2.  **User Interface (Streamlit)**
    *   URL: `http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/ui/`
    *   *Action*:
        1.  Upload a test PDF document.
        2.  Click "Загрузить и распознать".
        3.  Verify that a result (Verdict/Run ID) appears.

### D. API Health Check
```bash
curl http://rb-ocr-dev-app-uv01.fortebank.com/rb-ocr/health
# Expected: {"status":"healthy", ...}
```
