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