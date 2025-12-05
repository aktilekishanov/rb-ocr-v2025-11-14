#!/usr/bin/env python3
"""
S3 File Download Script
Downloads an existing file from ForteBank DEV MinIO server.
"""

import ssl
import urllib3
import hashlib
from minio import Minio
from minio.error import S3Error

# S3 Configuration
S3_ENDPOINT = "s3-dev.fortebank.com:9443"
S3_ACCESS_KEY = "fyz13d2czRW7l4sBW8gD"
S3_SECRET_KEY = "1ixYVVoZKSnG0rwfvTy0vnqQplupXOOn8DF9gS1A"
S3_BUCKET = "loan-statements-dev"
S3_SECURE = True  # Use HTTPS

# File to download (full object key)
FILE_TO_DOWNLOAD = "Приказ о выходе в декретный отпуск - Жармағанбет.pdf"

def download_file_from_s3():
    """Download a file from S3."""
    
    print("=" * 80)
    print("S3 FILE DOWNLOAD")
    print("=" * 80)
    print(f"Endpoint: {S3_ENDPOINT}")
    print(f"Bucket:   {S3_BUCKET}")
    print(f"File:     {FILE_TO_DOWNLOAD}")
    print()
    
    try:
        # Step 1: Create HTTP client with SSL configuration
        print("[1/5] Creating HTTP client...")
        http_client = urllib3.PoolManager(
            cert_reqs=ssl.CERT_NONE,
            assert_hostname=False
        )
        print("✓ HTTP client created")
        print()
        
        # Step 2: Initialize MinIO client
        print("[2/5] Initializing MinIO client...")
        client = Minio(
            S3_ENDPOINT,
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY,
            secure=S3_SECURE,
            region="random-region",
            http_client=http_client
        )
        print("✓ MinIO client initialized")
        print()
        
        # Step 3: Verify file exists and get metadata
        print(f"[3/5] Checking if file exists...")
        try:
            stat = client.stat_object(S3_BUCKET, FILE_TO_DOWNLOAD)
            print(f"✓ File found in S3")
            print(f"   Object Key:    {FILE_TO_DOWNLOAD}")
            print(f"   Size:          {stat.size:,} bytes ({stat.size / (1024*1024):.2f} MB)")
            print(f"   Content Type:  {stat.content_type or 'Not set'}")
            print(f"   ETag:          {stat.etag}")
            print(f"   Last Modified: {stat.last_modified}")
            print(f"   Version ID:    {stat.version_id or 'N/A'}")
            
            # Show user metadata if any
            if stat.metadata:
                user_metadata = {
                    k.replace('x-amz-meta-', ''): v 
                    for k, v in stat.metadata.items() 
                    if k.startswith('x-amz-meta-')
                }
                if user_metadata:
                    print(f"   Metadata:      {user_metadata}")
            print()
            
        except S3Error as e:
            if e.code == "NoSuchKey":
                print(f"✗ File '{FILE_TO_DOWNLOAD}' not found in bucket")
                return False
            else:
                raise
        
        # Step 4: Download from S3
        print(f"[4/5] Downloading file...")
        s3_path = f"s3://{S3_BUCKET}/{FILE_TO_DOWNLOAD}"
        
        response = client.get_object(S3_BUCKET, FILE_TO_DOWNLOAD)
        downloaded_data = response.read()
        downloaded_size = len(downloaded_data)
        downloaded_hash = hashlib.md5(downloaded_data).hexdigest()
        
        response.close()
        response.release_conn()
        
        print(f"✓ Download successful!")
        print(f"   S3 Path:    {s3_path}")
        print(f"   Downloaded: {downloaded_size:,} bytes ({downloaded_size / (1024*1024):.2f} MB)")
        print(f"   MD5 Hash:   {downloaded_hash}")
        print()
        
        # Step 5: Save to local file
        print(f"[5/5] Saving to local file...")
        local_path = f"tests/{FILE_TO_DOWNLOAD}"
        
        with open(local_path, 'wb') as f:
            f.write(downloaded_data)
        
        print(f"✓ File saved")
        print(f"   Local Path: {local_path}")
        print()
        
        # Display summary
        print("=" * 80)
        print("✓ DOWNLOAD SUCCESSFUL")
        print("=" * 80)
        print()
        print("SUMMARY:")
        print(f"  • File:         {FILE_TO_DOWNLOAD}")
        print(f"  • S3 Path:      {s3_path}")
        print(f"  • Local Path:   {local_path}")
        print(f"  • Size:         {downloaded_size:,} bytes ({downloaded_size / (1024*1024):.2f} MB)")
        print(f"  • Content Type: {stat.content_type or 'Not set'}")
        print(f"  • MD5 Hash:     {downloaded_hash}")
        print("=" * 80)
        
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
    success = download_file_from_s3()
    exit(0 if success else 1)