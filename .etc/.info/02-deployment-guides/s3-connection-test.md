# S3 Connection Testing Guide

## Table of Contents
- [Overview](#overview)
- [Why We Did This](#why-we-did-this)
- [What We Did](#what-we-did)
- [How We Did It](#how-we-did-it)
- [Results](#results)
- [How to Reproduce (A to Z)](#how-to-reproduce-a-to-z)
- [Troubleshooting](#troubleshooting)

---

## Overview

This document describes the process of testing S3 (MinIO) connectivity from within the Dockerized FastAPI service to verify that the application can successfully connect to ForteBank's DEV MinIO server and access the `loan-statements-dev` bucket.

**Date**: 2024-12-04  
**Environment**: rb-ocr-dev-app-uv01 (offline server)  
**Result**: ✅ Successful

---

## Why We Did This

### Business Context
The RB-OCR system needs to integrate with ForteBank's S3 storage to:
- Retrieve loan statement documents from the `loan-statements-dev` bucket
- Process uploaded files from external systems
- Store or access document artifacts

### Technical Context
Before implementing full S3 integration in the FastAPI service, we needed to:
1. **Verify network connectivity** from the Docker container to the S3 endpoint
2. **Validate credentials** (access key and secret key)
3. **Confirm bucket access permissions**
4. **Test SSL/TLS configuration** (self-signed certificates)
5. **Document the working configuration** for future implementation

### Initial Problem
The first test attempt resulted in an **AccessDenied** error, indicating authentication or configuration issues that needed to be resolved.

---

## What We Did

### Step-by-Step Summary

1. **Created S3 test script** (`test_s3_connection.py`)
   - Configured connection to `s3-dev.fortebank.com:9443`
   - Used MinIO Python client library
   - Implemented SSL verification bypass for self-signed certificates

2. **Built test Docker image**
   - Added test dependencies to requirements
   - Included test script in Docker image
   - Tagged as `rb-ocr-backend:test`

3. **Ran initial test**
   - Encountered `AccessDenied` error
   - Identified missing `region` parameter in MinIO client initialization

4. **Fixed the issue**
   - Added `region="random-region"` parameter
   - Region value can be any string (MinIO requirement for S3 signature calculation)

5. **Verified success**
   - Successfully connected to S3
   - Listed bucket contents
   - Confirmed read access to objects

---

## How We Did It

### Prerequisites
- Docker installed and running on the server
- Network access to `s3-dev.fortebank.com:9443`
- S3 credentials (access key and secret key)
- MinIO Python library in requirements

### Technical Implementation

#### 1. Test Script Structure

The test script performs 4 main steps:

```python
# Step 1: Create HTTP client with SSL configuration
http_client = urllib3.PoolManager(
    cert_reqs=ssl.CERT_NONE,      # Disable SSL verification
    assert_hostname=False           # Don't verify hostname
)

# Step 2: Initialize MinIO client
client = Minio(
    S3_ENDPOINT,
    access_key=S3_ACCESS_KEY,
    secret_key=S3_SECRET_KEY,
    secure=S3_SECURE,
    region="random-region",          # ⭐ CRITICAL: Required for auth
    http_client=http_client
)

# Step 3: Test connection (bucket_exists)
bucket_exists = client.bucket_exists(S3_BUCKET)

# Step 4: List objects in bucket
objects = client.list_objects(S3_BUCKET, recursive=True)
```

#### 2. Key Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| Endpoint | `s3-dev.fortebank.com:9443` | Internal MinIO server |
| Access Key | `fyz13d2czRW7l4sBW8gD` | DEV environment credentials |
| Secret Key | `1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A` | DEV environment credentials |
| Bucket | `loan-statements-dev` | Target bucket name |
| Secure | `True` | Use HTTPS |
| **Region** | `"random-region"` | ⭐ **Required** - any string works |
| SSL Verify | `False` | Self-signed certificate |

#### 3. Critical Fix: Region Parameter

**Problem**: Without the `region` parameter, the MinIO client could not generate a valid S3 v4 signature, resulting in `AccessDenied`.

**Solution**: Add `region="random-region"` (or any string value) to the `Minio()` constructor.

```python
# ❌ BEFORE (fails with AccessDenied)
client = Minio(
    S3_ENDPOINT,
    access_key=S3_ACCESS_KEY,
    secret_key=S3_SECRET_KEY,
    secure=S3_SECURE,
    http_client=http_client
)

# ✅ AFTER (works)
client = Minio(
    S3_ENDPOINT,
    access_key=S3_ACCESS_KEY,
    secret_key=S3_SECRET_KEY,
    secure=S3_SECURE,
    region="random-region",  # Added this line
    http_client=http_client
)
```

---

## Results

### Test Output

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
1. 0000e449-7f10-4d5f-8abe-8ae73ab37b66
   Size: 0.05 MB
   Last Modified: 2024-06-05 08:44:56.210000+00:00

[... 9 more objects ...]

Total objects shown: 10
 
============================================================
✓ S3 CONNECTION TEST SUCCESSFUL
============================================================
```

### What We Verified

✅ **Network connectivity** - Docker container can reach `s3-dev.fortebank.com:9443`  
✅ **Authentication** - Access key and secret key are valid  
✅ **Bucket access** - Can check bucket existence and permissions  
✅ **Read operations** - Can list objects and read metadata  
✅ **SSL/TLS** - Self-signed certificate handled correctly  

---

## How to Reproduce (A to Z)

### On Your Local Machine

#### Step 1: Create Test Script

Create the file `fastapi-service/tests/s3-test/test_s3_connection.py`:

```bash
mkdir -p fastapi-service/tests/s3-test
```

Add the following content (see full script in the repository):

```python
#!/usr/bin/env python3
import ssl
import urllib3
from minio import Minio
from minio.error import S3Error

S3_ENDPOINT = "s3-dev.fortebank.com:9443"
S3_ACCESS_KEY = "fyz13d2czRW7l4sBW8gD"
S3_SECRET_KEY = "1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A"
S3_BUCKET = "loan-statements-dev"
S3_SECURE = True

def test_s3_connection():
    http_client = urllib3.PoolManager(
        cert_reqs=ssl.CERT_NONE,
        assert_hostname=False
    )
    
    client = Minio(
        S3_ENDPOINT,
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
        secure=S3_SECURE,
        region="random-region",  # ⭐ CRITICAL
        http_client=http_client
    )
    
    bucket_exists = client.bucket_exists(S3_BUCKET)
    if bucket_exists:
        print(f"✓ Successfully connected! Bucket '{S3_BUCKET}' exists.")
        objects = client.list_objects(S3_BUCKET, recursive=True)
        # ... list objects ...
    
if __name__ == "__main__":
    success = test_s3_connection()
    exit(0 if success else 1)
```

#### Step 2: Update Requirements

Ensure `fastapi-service/requirements.txt` includes:

```txt
minio>=7.0.0
urllib3>=1.26.0
```

#### Step 3: Build Docker Image

```bash
cd /path/to/rb-ocr/apps

# Build with test tag
docker build \
  --platform linux/amd64 \
  -t rb-ocr-backend:test \
  -f fastapi-service/Dockerfile \
  ./fastapi-service
```

#### Step 4: Export to Tarball

```bash
# Save image
docker save rb-ocr-backend:test | gzip > rb-ocr-backend-test.tar.gz

# Verify size
ls -lh rb-ocr-backend-test.tar.gz
```

#### Step 5: Transfer to Server

```bash
# Transfer via SCP or USB drive
scp rb-ocr-backend-test.tar.gz rb_admin@rb-ocr-dev-app-uv01:~/rb-loan-deferment-idp/docker-deploy/
```

### On the Offline Server

#### Step 6: Load Docker Image

```bash
cd ~/rb-loan-deferment-idp/docker-deploy

# Extract and load
gunzip -c rb-ocr-backend-test.tar.gz | sudo docker load

# Verify
sudo docker images | grep rb-ocr-backend
```

#### Step 7: Run the Test

```bash
# Run the S3 connection test
sudo docker run --rm \
  rb-ocr-backend:test \
  python tests/s3-test/test_s3_connection.py
```

#### Step 8: Verify Success

Look for:
- ✅ `✓ Successfully connected! Bucket 'loan-statements-dev' exists.`
- ✅ List of objects in the bucket
- ✅ `✓ S3 CONNECTION TEST SUCCESSFUL`

---

## Troubleshooting

### Issue 1: AccessDenied Error

**Symptom**:
```
✗ S3 Error: S3 operation failed; code: AccessDenied, message: Access Denied.
```

**Cause**: Missing `region` parameter in MinIO client initialization

**Solution**: Add `region="random-region"` to the `Minio()` constructor

---

### Issue 2: Network Connectivity

**Symptom**:
```
✗ Unexpected Error: MaxRetryError
Connection refused / Timeout
```

**Checks**:
```bash
# Test DNS resolution
nslookup s3-dev.fortebank.com

# Test port connectivity
telnet s3-dev.fortebank.com 9443

# Test from container
sudo docker run --rm rb-ocr-backend:test \
  curl -k https://s3-dev.fortebank.com:9443
```

**Solution**: Verify network routing and firewall rules

---

### Issue 3: SSL Certificate Warnings

**Symptom**:
```
InsecureRequestWarning: Unverified HTTPS request is being made to host 's3-dev.fortebank.com'
```

**Note**: This is **expected** for internal servers with self-signed certificates

**Options**:
1. **Ignore** (current approach) - acceptable for internal DEV environment
2. **Add certificate** to trust store for production
3. **Configure** `MINIO_VERIFY_SSL` with path to CA certificate

---

### Issue 4: Bucket Not Found

**Symptom**:
```
✗ Connection successful, but bucket 'loan-statements-dev' does not exist.
```

**Solution**:
```python
# List all available buckets
buckets = client.list_buckets()
for bucket in buckets:
    print(f"  - {bucket.name}")
```

---

## Next Steps

### 1. Implement S3 Integration in FastAPI Service

Refer to the reference project for implementation pattern:
- [.REFERENCE/forte-fx-complex-master/src/core/s3.py](file:///.REFERENCE/forte-fx-complex-master/src/core/s3.py)
- [.REFERENCE/forte-fx-complex-master/src/core/config.py](file:///.REFERENCE/forte-fx-complex-master/src/core/config.py)

### 2. Environment Configuration

Add S3 configuration to `docker-compose.yml`:

```yaml
services:
  backend:
    environment:
      - MINIO_ENDPOINT=s3-dev.fortebank.com:9443
      - MINIO_ACCESS_KEY=fyz13d2czRW7l4sBW8gD
      - MINIO_SECRET_KEY=1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A
      - MINIO_BUCKET=loan-statements-dev
      - MINIO_SECURE=true
      - MINIO_VERIFY_SSL=false
```

### 3. Update Documentation

- [ ] Add S3 configuration to main README
- [ ] Document S3 integration in API documentation
- [ ] Create S3 usage examples

---

## References

- MinIO Python Client: https://min.io/docs/minio/linux/developers/python/minio-py.html
- Reference Project: `.REFERENCE/forte-fx-complex-master/`
- Integration Details: `.etc/.info/01-project-management/integration-details.md`

---

## Appendix: Full Test Script

See [fastapi-service/tests/s3-test/test_s3_connection.py](file:///fastapi-service/tests/s3-test/test_s3_connection.py) for the complete, working test script.
