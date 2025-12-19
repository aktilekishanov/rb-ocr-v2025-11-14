import sys
from minio import Minio
from minio.error import S3Error
import urllib3
import ssl
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION - PLEASE FILL THESE IN
# =============================================================================
S3_ENDPOINT = "s3-dev.fortebank.com:9443"  # Example, change if needed
S3_ACCESS_KEY = "YOUR_ACCESS_KEY"
S3_SECRET_KEY = "YOUR_SECRET_KEY"
S3_BUCKET = "loan-statements-dev"          # Found in your logs
S3_SECURE = True                           # Set to False if using HTTP

def test_s3_connection():
    """
    Test S3 connection using the fixed SSL context configuration.
    """
    logger.info("Initializing S3 Client with custom SSL context...")

    try:
        # ---------------------------------------------------------------------
        # THE FIX: Custom SSL Context for urllib3 v2.0+
        # ---------------------------------------------------------------------
        if S3_SECURE:
             # Create a custom SSL context to disable verification (replacement for assert_hostname=False)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            http_client = urllib3.PoolManager(
                ssl_context=ssl_context
            )
        else:
             http_client = urllib3.PoolManager()

        # Initialize Minio Client
        client = Minio(
            S3_ENDPOINT,
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY,
            secure=S3_SECURE,
            region="random-region",
            http_client=http_client,
        )
        logger.info(f"Client initialized for endpoint: {S3_ENDPOINT}")

        # Test 1: List Buckets (Basic connectivity check)
        logger.info("Test 1: Listing buckets...")
        buckets = client.list_buckets()
        logger.info(f"Success! Found {len(buckets)} buckets.")
        for msg_bucket in buckets:
            logger.info(f" - {msg_bucket.name}")

        # Test 2: List Objects in specific bucket
        if S3_BUCKET:
            logger.info(f"\nTest 2: Listing objects in bucket '{S3_BUCKET}'...")
            objects = client.list_objects(S3_BUCKET, recursive=True)
            count = 0
            for obj in objects:
                count += 1
                if count <= 10:
                    logger.info(f" - {obj.object_name} ({obj.size} bytes)")
            
            if count > 10:
                logger.info(f"... and {count - 10} more objects.")
            elif count == 0:
                logger.info("Bucket is empty or no objects found.")
        
        print("\n✅ CONNECTION SUCCESSFUL")

    except S3Error as e:
        logger.error(f"❌ S3 Error: {e}")
        if e.code == 'BadRequest':
            logger.error("NOTE: 'BadRequest' usually implies the SSL/Hostname issue we just fixed.")
    except Exception as e:
        logger.error(f"❌ Unexpected Error: {e}")

if __name__ == "__main__":
    test_s3_connection()
