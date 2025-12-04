# Testing Guide for FastAPI Service on Offline Server

Complete guide for running tests on the offline Debian 12 server with Docker.

---

## Overview

This guide covers how to run the S3 connection tests (and future tests) on your offline server within the Docker container. The challenge is that we need test dependencies (`minio`, `urllib3`) that aren't included in the main application requirements.

---

## Architecture Decision: Where to Include Test Dependencies?

### ❌ Option 1: Add to `fastapi-service/requirements.txt` (NOT RECOMMENDED)
- **Con**: Bloats production image with test-only dependencies
- **Con**: Violates separation of concerns
- **Con**: Increases container size unnecessarily

### ✅ Option 2: Create Development Dockerfile (RECOMMENDED)
- **Pro**: Clean separation between production and test environments
- **Pro**: Can run tests in isolated container
- **Pro**: Doesn't bloat production image

### 🔧 Option 3: Install in Running Container (QUICK & DIRTY)
- **Pro**: Quick for one-off testing
- **Con**: Requires internet or manual wheel transfer
- **Con**: Changes lost when container restarts

---

## Recommended Approach: Development Testing Container

Since your server is **offline**, you'll need to:
1. **Prepare offline wheels** for test dependencies on your Mac
2. **Build a test-enabled Docker image** with test dependencies
3. **Deploy and run tests** on the server

---

## Part 1: Prepare Test Dependencies (On Mac)

### Step 1: Create Test Requirements File

The test requirements are already in `tests/s3-test/requirements.txt`:
```
minio>=7.2.0
urllib3>=2.0.0
```

### Step 2: Download Test Dependency Wheels

Since the server is **offline**, you need to download the wheels on your Mac:

```bash
# Navigate to project directory
cd ~/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps

# Create directory for test wheels
mkdir -p fastapi-service/wheels-test

# Download test dependencies as wheels (linux/amd64 compatible)
pip download \
    --platform=manylinux2014_x86_64 \
    --only-binary=:all: \
    --python-version=311 \
    --implementation=cp \
    --abi=cp311 \
    -r fastapi-service/tests/s3-test/requirements.txt \
    -d fastapi-service/wheels-test/

# Verify wheels downloaded
ls -lh fastapi-service/wheels-test/
```

Expected output:
```
minio-7.x.x-py3-none-any.whl
urllib3-2.x.x-py3-none-any.whl
... (and their dependencies)
```

> [!IMPORTANT]
> Download wheels for **linux/amd64** platform since your server is Debian 12.

---

## Part 2: Create Development Dockerfile (On Mac)

### Step 1: Create `Dockerfile.dev` for Testing

Create a new file `fastapi-service/Dockerfile.dev`:

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

# Copy and install production requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install test wheels (offline)
COPY wheels-test/ /tmp/wheels-test/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels-test/ \
    minio>=7.2.0 urllib3>=2.0.0 && \
    rm -rf /tmp/wheels-test

# Copy application code and tests
COPY . .

# Create runs directory
RUN mkdir -p /app/runs && chmod 777 /app/runs

EXPOSE 8000

# Default: Run application (can override for tests)
CMD ["gunicorn", "main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

### Step 2: Build Development Image

```bash
# Build test-enabled image
docker build --platform linux/amd64 \
    -f fastapi-service/Dockerfile.dev \
    -t rb-ocr-backend:test \
    fastapi-service/

# Verify image created
docker images | grep rb-ocr-backend
```

### Step 3: Save and Compress Image

```bash
# Save image to tarball
docker save -o rb-ocr-backend-test.tar rb-ocr-backend:test

# Compress for transfer
gzip -f rb-ocr-backend-test.tar

# Verify file created
ls -lh rb-ocr-backend-test.tar.gz
```

---

## Part 3: Deploy Test Image to Server

### Step 1: Transfer Test Image Tarball

Transfer `rb-ocr-backend-test.tar.gz` to server at:
```
~/rb-loan-deferment-idp/docker-deploy/rb-ocr-backend-test.tar.gz
```

### Step 2: Load Test Image on Server

```bash
# SSH to server and navigate to deploy directory
cd ~/rb-loan-deferment-idp/docker-deploy

# Load test image
sudo gunzip -c rb-ocr-backend-test.tar.gz | sudo docker load

# Verify image loaded
sudo docker images | grep rb-ocr-backend
```

Expected output:
```
rb-ocr-backend    test      <image-id>    <time>    <size>
rb-ocr-backend    latest    <image-id>    <time>    <size>
```

---

## Part 4: Run Tests on Server

### Method 1: Run Test Script Directly

```bash
# Run S3 connection test in a temporary container
sudo docker run --rm \
    rb-ocr-backend:test \
    python tests/s3-test/test_s3_connection.py
```

Expected output:
```
============================================================
S3 Connection Test
============================================================
Endpoint: s3-dev.fortebank.com:9443
Bucket: loan-statements-dev
Secure: True

[1/4] Creating HTTP client with SSL configuration...
✓ HTTP client created

[2/4] Initializing MinIO client...
✓ MinIO client initialized

[3/4] Testing connection (checking bucket existence)...
✓ Successfully connected! Bucket 'loan-statements-dev' exists.

[4/4] Listing objects in bucket...

Objects in 'loan-statements-dev':
------------------------------------------------------------
1. example-file.pdf
   Size: 1.23 MB
   Last Modified: 2024-12-01 10:30:00

✓ S3 CONNECTION TEST SUCCESSFUL
============================================================
```

### Method 2: Interactive Testing in Container

```bash
# Start container with shell
sudo docker run --rm -it \
    rb-ocr-backend:test \
    /bin/bash

# Inside container, run tests
python tests/s3-test/test_s3_connection.py

# Can also test other Python functionality
python -c "from minio import Minio; print('Minio installed successfully')"

# Exit container
exit
```

### Method 3: Run Tests in Production Container (If Already Running)

If you want to test the production container without rebuilding:

```bash
# Copy test script into running container
sudo docker cp tests/s3-test/test_s3_connection.py rb-ocr-backend:/app/test_s3.py

# Install test dependencies in running container (TEMPORARY)
sudo docker exec rb-ocr-backend pip install minio urllib3

# Run test
sudo docker exec rb-ocr-backend python /app/test_s3.py
```

> [!WARNING]
> This method installs packages in the running container. Changes will be lost on container restart.

---

## Part 5: Future Testing Strategy

### For Unit Tests (When You Add Them)

If you add unit tests (e.g., with `pytest`):

1. **Add to test requirements**:
   ```
   # tests/requirements-test.txt
   pytest>=7.4.0
   pytest-cov>=4.1.0
   pytest-asyncio>=0.21.0
   minio>=7.2.0
   urllib3>=2.0.0
   ```

2. **Download wheels**:
   ```bash
   pip download \
       --platform=manylinux2014_x86_64 \
       --only-binary=:all: \
       --python-version=311 \
       -r fastapi-service/tests/requirements-test.txt \
       -d fastapi-service/wheels-test/
   ```

3. **Update `Dockerfile.dev`**:
   ```dockerfile
   # Install all test dependencies from wheels
   RUN pip install --no-cache-dir --no-index \
       --find-links=/tmp/wheels-test/ \
       -r tests/requirements-test.txt
   ```

4. **Run tests**:
   ```bash
   sudo docker run --rm rb-ocr-backend:test pytest tests/ -v
   ```

---

## Quick Reference Commands

### On Mac: Build Test Image
```bash
cd ~/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps

# Download test wheels
mkdir -p fastapi-service/wheels-test
pip download --platform=manylinux2014_x86_64 --only-binary=:all: \
    --python-version=311 -r fastapi-service/tests/s3-test/requirements.txt \
    -d fastapi-service/wheels-test/

# Build and save test image
docker build --platform linux/amd64 \
    -f fastapi-service/Dockerfile.dev -t rb-ocr-backend:test fastapi-service/
docker save -o rb-ocr-backend-test.tar rb-ocr-backend:test
gzip -f rb-ocr-backend-test.tar
```

### On Server: Load and Run Tests
```bash
# Load test image
cd ~/rb-loan-deferment-idp/docker-deploy
sudo gunzip -c rb-ocr-backend-test.tar.gz | sudo docker load

# Run S3 test
sudo docker run --rm rb-ocr-backend:test \
    python tests/s3-test/test_s3_connection.py
```

---

## Answers to Your Questions

### Q: Can I just add test requirements to `fastapi-service/requirements.txt` and rebuild?

**A**: Technically yes, but **not recommended** because:
- ❌ Bloats production image with unnecessary dependencies
- ❌ Mixes production and test concerns
- ❌ Increases container size and attack surface

**Better approach**: Use separate `Dockerfile.dev` with test dependencies.

### Q: Do I need to prepare offline wheels first?

**A**: **YES**, because:
- ✅ Your server has **no internet access**
- ✅ Docker build will fail if it tries to `pip install` from PyPI
- ✅ Using `--no-index` and `--find-links` with pre-downloaded wheels is the **only way** to install packages offline

### Q: Will it work to rebuild images as before?

**A**: It will work **IF**:
1. ✅ You download the test dependency wheels on your Mac first
2. ✅ You copy wheels into the Docker build context
3. ✅ You modify Dockerfile to install from local wheels (not from PyPI)

Otherwise, the build will fail on the server when it tries to download from PyPI.

---

## Troubleshooting

### Test Import Error: `ModuleNotFoundError: No module named 'minio'`

**Cause**: Test dependencies not installed in container.

**Solution**: 
- Build image with `Dockerfile.dev` which includes test wheels
- OR manually install in running container (temporary)

### Build Fails: `Could not find a version that satisfies the requirement minio`

**Cause**: Building without internet and wheels not in build context.

**Solution**:
1. Download wheels on Mac: `pip download -r tests/s3-test/requirements.txt -d wheels-test/`
2. Ensure `COPY wheels-test/` in Dockerfile
3. Use `--no-index --find-links=/tmp/wheels-test/` when installing

### S3 Test Fails: Connection Timeout

**Cause**: Server cannot reach S3 endpoint `s3-dev.fortebank.com:9443`.

**Solution**:
- Verify network connectivity from server to S3
- Check firewall rules
- Verify endpoint URL is correct

---

## Summary

**Best Practice for Offline Testing**:

1. **Separate environments**: Production (`Dockerfile`) vs Development (`Dockerfile.dev`)
2. **Pre-download wheels**: Use `pip download` on Mac for linux/amd64 platform
3. **Offline installation**: Use `--no-index --find-links` in Dockerfile
4. **Run tests in container**: Use test-enabled image, not production image

This approach keeps your production image lean while enabling comprehensive testing on the offline server.
