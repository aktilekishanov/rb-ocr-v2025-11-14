# Docker Images Build & Deploy Guide

Complete guide for building Docker images on Mac and deploying to the offline server with proper cleanup.

---

## Part 1: Build & Export (On Mac)

### Step 1: Navigate to Project Directory
```bash
cd ~/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps
```

### Step 2: Rebuild Docker Images
```bash
# Rebuild both images
docker compose build

# OR rebuild specific service only:
# docker compose build backend
# docker compose build ui
```

### Step 3: Save Images to Tarballs
```bash
# Save images to tar files
docker save -o rb-ocr-backend.tar rb-ocr-backend:latest
docker save -o rb-ocr-ui.tar rb-ocr-ui:latest
```

### Step 4: Compress Tarballs
```bash
# Compress for faster transfer
gzip -f rb-ocr-backend.tar
gzip -f rb-ocr-ui.tar
```

### Step 5: Verify Files Created
```bash
ls -lh *.tar.gz
```

Expected output:
```
-rw-r--r--  1 user  staff   XXX MB  rb-ocr-backend.tar.gz
-rw-r--r--  1 user  staff   XXX MB  rb-ocr-ui.tar.gz
```

---

## Part 2: Deploy (On Server)

### Step 1: Pre-Deployment Checks

#### Check Existing Containers
```bash
# List all running containers
sudo docker ps

# List all containers (including stopped)
sudo docker ps -a

# Filter for rb-ocr containers
sudo docker ps -a | grep rb-ocr
```

#### Check Existing Images
```bash
# List all images
sudo docker images

# Filter for rb-ocr images
sudo docker images | grep rb-ocr
```

#### Check Docker Compose Status
```bash
cd ~/rb-loan-deferment-idp
sudo docker compose ps
```

---

### Step 2: Complete Cleanup

#### Stop All Running Containers
```bash
cd ~/rb-loan-deferment-idp
sudo docker compose down
```

#### Remove Old Containers (if any remain)
```bash
# Remove specific containers by name
sudo docker rm -f rb-ocr-backend || true
sudo docker rm -f rb-ocr-ui || true

# OR remove all stopped containers
# sudo docker container prune -f
```

#### Remove Old Images
```bash
# Remove specific images
sudo docker rmi rb-ocr-backend:latest || true
sudo docker rmi rb-ocr-ui:latest || true

# Verify images are removed
sudo docker images | grep rb-ocr
```

#### Clean Up Dangling Images (Optional but Recommended)
```bash
# Remove dangling images to free up space
sudo docker image prune -f
```

#### Verify Clean State
```bash
# Should show no rb-ocr containers
sudo docker ps -a | grep rb-ocr

# Should show no rb-ocr images
sudo docker images | grep rb-ocr
```

---

### Step 3: Load New Images

#### Navigate to Docker Deploy Directory
```bash
cd ~/rb-loan-deferment-idp/docker-deploy
```

#### Verify Tarball Files Exist
```bash
ls -lh *.tar.gz
```

Expected files:
- `rb-ocr-backend.tar.gz`
- `rb-ocr-ui.tar.gz`

#### Load Images from Tarballs
```bash
# Load backend image
sudo gunzip -c rb-ocr-backend.tar.gz | sudo docker load

# Load UI image
sudo gunzip -c rb-ocr-ui.tar.gz | sudo docker load
```

#### Verify Images Loaded Successfully
```bash
sudo docker images | grep rb-ocr
```

Expected output:
```
rb-ocr-backend    latest    <image-id>    <time>    <size>
rb-ocr-ui         latest    <image-id>    <time>    <size>
```

---

### Step 4: Start Containers

#### Navigate to Docker Compose Directory
```bash
cd ~/rb-loan-deferment-idp
```

#### Start Services in Detached Mode
```bash
sudo docker compose up -d
```

#### Verify Containers Started
```bash
sudo docker compose ps
```

Expected output should show both containers running:
```
NAME                STATUS              PORTS
rb-ocr-backend      Up X seconds        0.0.0.0:8000->8000/tcp
rb-ocr-ui           Up X seconds        0.0.0.0:8501->8501/tcp
```

---

### Step 5: Post-Deployment Verification

#### Check Container Logs
```bash
# View backend logs
sudo docker compose logs backend

# View UI logs
sudo docker compose logs ui

# Follow logs in real-time
sudo docker compose logs -f
```

#### Test Health Endpoints
```bash
# Test backend health
curl http://localhost:8000/health

# Test UI (should return HTML)
curl http://localhost:8501
```

#### Check Container Resource Usage
```bash
sudo docker stats --no-stream
```

---

## Troubleshooting

### If Containers Fail to Start

1. **Check logs for errors**:
   ```bash
   sudo docker compose logs backend
   sudo docker compose logs ui
   ```

2. **Verify images loaded correctly**:
   ```bash
   sudo docker images | grep rb-ocr
   ```

3. **Check port conflicts**:
   ```bash
   sudo netstat -tulpn | grep -E '8000|8501'
   ```

4. **Restart services**:
   ```bash
   sudo docker compose restart
   ```

### If Images Won't Load

1. **Check tarball integrity**:
   ```bash
   gunzip -t rb-ocr-backend.tar.gz
   gunzip -t rb-ocr-ui.tar.gz
   ```

2. **Re-transfer files if corrupted**

3. **Check disk space**:
   ```bash
   df -h
   ```

### Complete Reset (Nuclear Option)

```bash
# Stop everything
cd ~/rb-loan-deferment-idp
sudo docker compose down

# Remove all rb-ocr containers
sudo docker ps -a | grep rb-ocr | awk '{print $1}' | xargs -r sudo docker rm -f

# Remove all rb-ocr images
sudo docker images | grep rb-ocr | awk '{print $3}' | xargs -r sudo docker rmi -f

# Clean up system
sudo docker system prune -f

# Start fresh with load and deploy
```

---

## Quick Reference Commands

### On Mac (Build)
```bash
cd ~/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps
docker compose build
docker save -o rb-ocr-backend.tar rb-ocr-backend:latest
docker save -o rb-ocr-ui.tar rb-ocr-ui:latest
gzip -f rb-ocr-backend.tar rb-ocr-ui.tar
ls -lh *.tar.gz
```

### On Server (Deploy with Cleanup)
```bash
# Pre-check
cd ~/rb-loan-deferment-idp
sudo docker compose ps
sudo docker images | grep rb-ocr

# Cleanup
sudo docker compose down
sudo docker rmi rb-ocr-backend:latest rb-ocr-ui:latest || true
sudo docker image prune -f

# Load
cd ~/rb-loan-deferment-idp/docker-deploy
sudo gunzip -c rb-ocr-backend.tar.gz | sudo docker load
sudo gunzip -c rb-ocr-ui.tar.gz | sudo docker load
sudo docker images | grep rb-ocr

# Deploy
cd ~/rb-loan-deferment-idp
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs -f
```
