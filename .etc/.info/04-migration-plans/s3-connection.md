# S3 Connection Implementation Plan

## Overview

**Objective:** Connect to the ForteBank DEV MinIO S3 server, establish connection, and list bucket contents.

**Target S3 Server:**
- **Domain:** s3-dev.fortebank.com:9443
- **IP:** 10.0.99.212
- **Bucket:** loan-statements-dev
- **Access Key:** fyz13d2czRW7l4sBW8gD
- **Secret Key:** 1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A
- **API:** s3v4
- **Protocol:** HTTPS (port 9443)

---

## Reference Implementation Analysis

Based on the colleague's `forte-fx-complex` project, the S3 integration uses:

1. **MinIO Python Client** (version 7.2.16) - S3-compatible object storage client
2. **Custom SSL Handling** - Supports both custom CA certificates and SSL verification bypass
3. **Connection Pooling** - Uses urllib3 for efficient connection management
4. **Key Normalization** - Defensive handling of S3 object keys

**Key Implementation Pattern:**
```python
from minio import Minio
import ssl
import urllib3

# Create MinIO client with SSL handling
http_client = urllib3.PoolManager(
    cert_reqs=ssl.CERT_NONE,
    assert_hostname=False
)

client = Minio(
    endpoint="s3-dev.fortebank.com:9443",
    access_key="fyz13d2czRW7l4sBW8gD",
    secret_key="1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A",
    secure=True,  # Use HTTPS
    http_client=http_client
)
```

---

## Step-by-Step Implementation Plan

### Phase 1: Environment Setup

#### Step 1.1: Install Required Dependencies

**Action:** Install the MinIO Python client library.

**Commands:**
```bash
pip install minio urllib3
```

**Expected Versions:**
- `minio>=7.2.0` (reference project uses 7.2.16)
- `urllib3>=2.0.0`

**Verification:**
```bash
pip list | grep minio
pip list | grep urllib3
```

---

### Phase 2: Create S3 Connection Script

#### Step 2.1: Create Test Script File

**Action:** Create a standalone Python script to test S3 connection.

**File Location:** `/Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/test_s3_connection.py`

**Script Structure:**
```python
#!/usr/bin/env python3
"""
S3 Connection Test Script
Tests connection to ForteBank DEV MinIO server and lists bucket contents.
"""

import ssl
import urllib3
from minio import Minio
from minio.error import S3Error

# S3 Configuration
S3_ENDPOINT = "s3-dev.fortebank.com:9443"
S3_ACCESS_KEY = "fyz13d2czRW7l4sBW8gD"
S3_SECRET_KEY = "1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A"
S3_BUCKET = "loan-statements-dev"
S3_SECURE = True  # Use HTTPS

def test_s3_connection():
    """Test S3 connection and list bucket contents."""
    
    print("=" * 60)
    print("S3 Connection Test")
    print("=" * 60)
    print(f"Endpoint: {S3_ENDPOINT}")
    print(f"Bucket: {S3_BUCKET}")
    print(f"Secure: {S3_SECURE}")
    print()
    
    try:
        # Step 1: Create HTTP client with SSL verification disabled
        # (for internal servers with self-signed certificates)
        print("[1/4] Creating HTTP client with SSL configuration...")
        http_client = urllib3.PoolManager(
            cert_reqs=ssl.CERT_NONE,
            assert_hostname=False
        )
        print("✓ HTTP client created")
        print()
        
        # Step 2: Initialize MinIO client
        print("[2/4] Initializing MinIO client...")
        client = Minio(
            S3_ENDPOINT,
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY,
            secure=S3_SECURE,
            http_client=http_client
        )
        print("✓ MinIO client initialized")
        print()
        
        # Step 3: Test connection by checking if bucket exists
        print("[3/4] Testing connection (checking bucket existence)...")
        bucket_exists = client.bucket_exists(S3_BUCKET)
        
        if bucket_exists:
            print(f"✓ Successfully connected! Bucket '{S3_BUCKET}' exists.")
        else:
            print(f"✗ Connection successful, but bucket '{S3_BUCKET}' does not exist.")
            print("Available buckets:")
            buckets = client.list_buckets()
            for bucket in buckets:
                print(f"  - {bucket.name}")
            return False
        print()
        
        # Step 4: List objects in bucket
        print("[4/4] Listing objects in bucket...")
        objects = client.list_objects(S3_BUCKET, recursive=True)
        
        object_count = 0
        print(f"\nObjects in '{S3_BUCKET}':")
        print("-" * 60)
        
        for obj in objects:
            object_count += 1
            size_mb = obj.size / (1024 * 1024)
            print(f"{object_count}. {obj.object_name}")
            print(f"   Size: {size_mb:.2f} MB")
            print(f"   Last Modified: {obj.last_modified}")
            print()
            
            # Limit output to first 10 objects
            if object_count >= 10:
                print("... (showing first 10 objects only)")
                break
        
        if object_count == 0:
            print("(Bucket is empty)")
        else:
            print(f"\nTotal objects shown: {object_count}")
        
        print()
        print("=" * 60)
        print("✓ S3 CONNECTION TEST SUCCESSFUL")
        print("=" * 60)
        return True
        
    except S3Error as e:
        print(f"\n✗ S3 Error: {e}")
        print(f"   Error Code: {e.code}")
        print(f"   Message: {e.message}")
        return False
        
    except Exception as e:
        print(f"\n✗ Unexpected Error: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_s3_connection()
    exit(0 if success else 1)
```

---

### Phase 3: Connection Testing

#### Step 3.1: Run Initial Connection Test

**Action:** Execute the test script to verify S3 connection.

**Command:**
```bash
cd /Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps
python test_s3_connection.py
```

**Expected Output (Success):**
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
1. path/to/file1.pdf
   Size: 1.23 MB
   Last Modified: 2025-12-04 10:30:00+00:00

...

============================================================
✓ S3 CONNECTION TEST SUCCESSFUL
============================================================
```

**Possible Issues & Solutions:**

| Issue | Symptom | Solution |
|-------|---------|----------|
| **Network Connectivity** | `Connection refused` or timeout | 1. Check if server is reachable: `ping 10.0.99.212`<br>2. Check if port is open: `telnet 10.0.99.212 9443`<br>3. Verify VPN/network access |
| **Invalid Credentials** | `Access Denied` or `InvalidAccessKeyId` | 1. Verify access key and secret key<br>2. Check if credentials are still valid<br>3. Contact admin to regenerate keys |
| **SSL Certificate Error** | `SSL: CERTIFICATE_VERIFY_FAILED` | Already handled by `cert_reqs=ssl.CERT_NONE`<br>If still occurs, ensure `secure=True` and `http_client` is set |
| **Bucket Not Found** | `NoSuchBucket` | 1. Verify bucket name is correct<br>2. List all buckets to find correct name<br>3. Check if you have access to the bucket |
| **DNS Resolution** | `Name or service not known` | 1. Try using IP directly: `10.0.99.212:9443`<br>2. Check `/etc/hosts` or DNS settings |

---

### Phase 4: Enhanced Testing (Optional)

#### Step 4.1: Test File Download

**Action:** If bucket contains files, test downloading a file.

**Additional Test Function:**
```python
def test_download_file(client, bucket, object_key):
    """Test downloading a specific file from S3."""
    try:
        print(f"Downloading: {object_key}")
        response = client.get_object(bucket, object_key)
        data = response.read()
        print(f"✓ Downloaded {len(data)} bytes")
        response.close()
        response.release_conn()
        return True
    except Exception as e:
        print(f"✗ Download failed: {e}")
        return False
```

#### Step 4.2: Test File Upload (if needed)

**Action:** Test uploading a small test file.

**Additional Test Function:**
```python
def test_upload_file(client, bucket):
    """Test uploading a small test file."""
    import io
    
    try:
        test_data = b"Test file content"
        test_key = "test/connection_test.txt"
        
        print(f"Uploading test file: {test_key}")
        client.put_object(
            bucket,
            test_key,
            io.BytesIO(test_data),
            length=len(test_data),
            content_type="text/plain"
        )
        print(f"✓ Upload successful")
        
        # Clean up
        client.remove_object(bucket, test_key)
        print(f"✓ Test file removed")
        return True
    except Exception as e:
        print(f"✗ Upload failed: {e}")
        return False
```

---

### Phase 5: Integration Planning

#### Step 5.1: Create Reusable S3 Client Module

**Action:** Once connection is verified, create a reusable S3 client module for the project.

**File Location:** `/Users/aktilekishanov/Documents/career/forte/ds/rb_ocr/2025-11-14-apps-from-server-RBOCR/apps/utils/s3_client.py`

**Module Structure:**
```python
"""
S3 Client Module
Provides S3 connection and file operations for the RB-OCR project.
"""

import ssl
import urllib3
from minio import Minio
from minio.error import S3Error
from typing import Optional
import os

class S3Client:
    """MinIO S3 client wrapper for document storage."""
    
    def __init__(
        self,
        endpoint: str = None,
        access_key: str = None,
        secret_key: str = None,
        bucket: str = None,
        secure: bool = True,
        verify_ssl: bool = False
    ):
        """
        Initialize S3 client.
        
        Args:
            endpoint: S3 endpoint (e.g., "s3-dev.fortebank.com:9443")
            access_key: S3 access key
            secret_key: S3 secret key
            bucket: Default bucket name
            secure: Use HTTPS
            verify_ssl: Verify SSL certificates
        """
        # Load from environment if not provided
        self.endpoint = endpoint or os.getenv("S3_ENDPOINT")
        self.access_key = access_key or os.getenv("S3_ACCESS_KEY")
        self.secret_key = secret_key or os.getenv("S3_SECRET_KEY")
        self.bucket = bucket or os.getenv("S3_BUCKET")
        self.secure = secure
        
        # Configure SSL
        http_client = None
        if not verify_ssl:
            http_client = urllib3.PoolManager(
                cert_reqs=ssl.CERT_NONE,
                assert_hostname=False
            )
        
        # Initialize MinIO client
        self.client = Minio(
            self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            http_client=http_client
        )
    
    def download_file(self, object_key: str, bucket: str = None) -> bytes:
        """Download file from S3 and return bytes."""
        bucket = bucket or self.bucket
        response = self.client.get_object(bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    
    def list_objects(self, prefix: str = "", bucket: str = None):
        """List objects in bucket with optional prefix filter."""
        bucket = bucket or self.bucket
        return self.client.list_objects(bucket, prefix=prefix, recursive=True)
    
    def bucket_exists(self, bucket: str = None) -> bool:
        """Check if bucket exists."""
        bucket = bucket or self.bucket
        return self.client.bucket_exists(bucket)
```

#### Step 5.2: Environment Configuration

**Action:** Add S3 configuration to environment variables.

**File:** `.env` or environment configuration

**Variables:**
```env
# S3/MinIO Configuration
S3_ENDPOINT=s3-dev.fortebank.com:9443
S3_ACCESS_KEY=fyz13d2czRW7l4sBW8gD
S3_SECRET_KEY=1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A
S3_BUCKET=loan-statements-dev
S3_SECURE=true
S3_VERIFY_SSL=false
```

---

## Verification Plan

### Manual Verification Steps

1. **Install Dependencies**
   ```bash
   pip install minio urllib3
   ```

2. **Run Connection Test**
   ```bash
   python test_s3_connection.py
   ```
   
   **Success Criteria:**
   - Script completes without errors
   - Prints "✓ S3 CONNECTION TEST SUCCESSFUL"
   - Lists objects in bucket (or shows "Bucket is empty")
   - Exit code is 0

3. **Verify Network Connectivity** (if connection fails)
   ```bash
   # Test server reachability
   ping -c 3 10.0.99.212
   
   # Test port connectivity
   nc -zv 10.0.99.212 9443
   # or
   telnet 10.0.99.212 9443
   ```

4. **Test with Alternative Endpoint** (if DNS fails)
   - Modify script to use IP directly: `10.0.99.212:9443`
   - Re-run test

---

## Troubleshooting Guide

### Common Issues

#### 1. SSL Certificate Verification Failed

**Error:**
```
ssl.SSLCertVerificationError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**Solution:**
- Ensure `http_client` with `cert_reqs=ssl.CERT_NONE` is passed to Minio()
- Verify `secure=True` is set
- Check that urllib3 is properly installed

#### 2. Connection Timeout

**Error:**
```
urllib3.exceptions.MaxRetryError: Max retries exceeded
```

**Solution:**
- Check network connectivity to 10.0.99.212
- Verify port 9443 is accessible
- Check firewall rules
- Ensure VPN is connected (if required)

#### 3. Access Denied

**Error:**
```
S3Error: Access Denied
```

**Solution:**
- Verify access key and secret key are correct
- Check if credentials have expired
- Confirm bucket name is correct
- Verify IAM permissions for the access key

#### 4. Bucket Not Found

**Error:**
```
S3Error: NoSuchBucket
```

**Solution:**
- List all available buckets using `client.list_buckets()`
- Verify bucket name spelling
- Check if you have access to the bucket

---

## Security Considerations

### Current Approach
- **SSL Verification Disabled:** Using `cert_reqs=ssl.CERT_NONE` for internal servers with self-signed certificates
- **Credentials in Code:** Test script has hardcoded credentials

### Production Recommendations

1. **Use Environment Variables**
   - Store credentials in `.env` file (add to `.gitignore`)
   - Use `python-dotenv` to load environment variables
   - Never commit credentials to version control

2. **Enable SSL Verification (if possible)**
   - Obtain the CA certificate for s3-dev.fortebank.com
   - Use `ssl.create_default_context(cafile="/path/to/ca.crt")`
   - Pass custom SSL context to urllib3

3. **Credential Rotation**
   - Regularly rotate access keys
   - Use IAM roles if available
   - Implement credential expiration policies

4. **Access Control**
   - Use least-privilege principle for S3 access
   - Restrict bucket access to specific IP ranges
   - Enable audit logging

---

## Next Steps After Verification

Once S3 connection is successfully established:

1. **Integrate with Kafka Consumer**
   - Modify Kafka consumer to download files from S3 using `s3_path`
   - Pass downloaded file bytes to FastAPI `/v1/verify` endpoint

2. **Update Database Schema**
   - Add `source_s3_path` column to store original S3 location
   - Enable file recovery if local copy is deleted

3. **Implement File Lifecycle**
   - Download from S3 when Kafka event received
   - Process file through pipeline
   - Delete local copy after 30 days (keep S3 path in DB)

4. **Error Handling**
   - Handle S3 connection failures gracefully
   - Implement retry logic for transient errors
   - Log S3 operations for debugging

---

## Summary

This implementation plan provides:

✅ **Clear Dependencies:** MinIO Python client + urllib3  
✅ **Reference Implementation:** Based on proven colleague's code  
✅ **Step-by-Step Script:** Complete test script with error handling  
✅ **Verification Steps:** Manual testing procedures  
✅ **Troubleshooting Guide:** Common issues and solutions  
✅ **Security Best Practices:** Environment variables, SSL handling  
✅ **Integration Path:** Next steps for Kafka integration  

**Estimated Time:** 30-60 minutes (including troubleshooting)

**Risk Level:** Low - Read-only operations, no code changes to existing system

**Dependencies:** Network access to 10.0.99.212:9443, valid S3 credentials
