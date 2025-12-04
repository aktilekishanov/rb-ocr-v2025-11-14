# S3 Connection Test - Offline Server Deployment

## Overview
This guide explains how to run the S3 connection test on an offline server.

---

## Quick Start (Local Machine)

### Step 1: Download Dependencies as Wheels

```bash
cd /Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/TEST-S3-CONN

# Create requirements file
cat > requirements.txt << EOF
minio>=7.2.0
urllib3>=2.0.0
EOF

# Download wheels for all dependencies (including transitive deps)
pip download -r requirements.txt -d ./wheels
```

This will download:
- `minio` and all its dependencies
- `urllib3` and all its dependencies
- All wheels will be saved in `./wheels/` directory

### Step 2: Transfer to Server

```bash
# Create tarball for easy transfer
tar -czf s3-test-package.tar.gz test_s3_connection.py requirements.txt wheels/

# Transfer to server (adjust server details)
scp s3-test-package.tar.gz rb_admin@10.0.94.227:/home/rb_admin/
```

---

## On Offline Server

### Step 3: Extract and Setup

```bash
# Extract package
cd /home/rb_admin
tar -xzf s3-test-package.tar.gz

# Create virtual environment (RECOMMENDED)
python3 -m venv s3-test-env
source s3-test-env/bin/activate
```

**Why use venv?**
- ✅ Isolates dependencies from system Python
- ✅ Prevents conflicts with other projects
- ✅ Easy to clean up (just delete the directory)
- ✅ No sudo/admin rights needed

### Step 4: Install Dependencies from Wheels

```bash
# Install from local wheels (no internet needed)
pip install --no-index --find-links=./wheels -r requirements.txt
```

**Flags explained:**
- `--no-index`: Don't use PyPI (internet)
- `--find-links=./wheels`: Use local wheel directory
- `-r requirements.txt`: Install packages from requirements file

### Step 5: Run Test Script

```bash
python test_s3_connection.py
```

### Step 6: Cleanup (Optional)

```bash
# Deactivate virtual environment
deactivate

# Remove everything
cd ~
rm -rf s3-test-env s3-test-package.tar.gz test_s3_connection.py requirements.txt wheels/
```

---

## Alternative: Without Virtual Environment

If you prefer not to use venv (not recommended):

```bash
# Install directly to user site-packages
pip install --user --no-index --find-links=./wheels -r requirements.txt

# Run script
python test_s3_connection.py
```

**Drawbacks:**
- ❌ May conflict with existing packages
- ❌ Harder to clean up
- ❌ Affects all Python scripts for that user

---

## Troubleshooting

### Issue: `pip: command not found`

**Solution:**
```bash
# Use python3 -m pip instead
python3 -m pip install --no-index --find-links=./wheels -r requirements.txt
```

### Issue: Missing wheel for specific Python version

**Solution on local machine:**
```bash
# Download for specific Python version (e.g., 3.11)
pip download -r requirements.txt -d ./wheels --python-version 3.11 --only-binary=:all:
```

### Issue: Platform mismatch (macOS wheels won't work on Linux)

**Solution on local machine:**
```bash
# Download for Linux platform
pip download -r requirements.txt -d ./wheels --platform manylinux2014_x86_64 --only-binary=:all:
```

---

## Complete One-Liner Commands

### On Local Machine:
```bash
cd TEST-S3-CONN && \
echo -e "minio>=7.2.0\nurllib3>=2.0.0" > requirements.txt && \
pip download -r requirements.txt -d ./wheels && \
tar -czf s3-test-package.tar.gz test_s3_connection.py requirements.txt wheels/ && \
scp s3-test-package.tar.gz rb_admin@10.0.94.227:/home/rb_admin/
```

### On Offline Server:
```bash
tar -xzf s3-test-package.tar.gz && \
python3 -m venv s3-test-env && \
source s3-test-env/bin/activate && \
pip install --no-index --find-links=./wheels -r requirements.txt && \
python test_s3_connection.py
```

---

## Expected Output

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
...
============================================================
✓ S3 CONNECTION TEST SUCCESSFUL
============================================================
```
