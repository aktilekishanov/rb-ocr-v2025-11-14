"""MinIO S3 client for downloading documents."""
import ssl
import urllib3
import logging
from pathlib import Path
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class S3Client:
    """Client for interacting with MinIO S3 storage."""
    
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool = True,
    ):
        """
        Initialize S3 client.
        
        Args:
            endpoint: S3 endpoint (e.g., "s3-dev.fortebank.com:9443")
            access_key: S3 access key
            secret_key: S3 secret key
            bucket: S3 bucket name
            secure: Use HTTPS (default: True)
        """
        self.bucket = bucket
        self.endpoint = endpoint
        
        # Create HTTP client with SSL configuration
        http_client = urllib3.PoolManager(
            cert_reqs=ssl.CERT_NONE,
            assert_hostname=False
        )
        
        # Initialize MinIO client
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region="random-region",
            http_client=http_client
        )
        
        logger.info(f"S3Client initialized: endpoint={endpoint}, bucket={bucket}")
    
    def download_file(self, object_key: str, destination_path: str) -> dict:
        """
        Download a file from S3.
        
        Args:
            object_key: S3 object key/path
            destination_path: Local file path to save the downloaded file
            
        Returns:
            dict with metadata: {
                "size": int,
                "content_type": str,
                "etag": str,
                "local_path": str
            }
            
        Raises:
            S3Error: If file not found or download fails
            Exception: For other errors
        """
        try:
            # Get object metadata
            stat = self.client.stat_object(self.bucket, object_key)
            logger.info(
                f"Found S3 object: key={object_key}, "
                f"size={stat.size} bytes, content_type={stat.content_type}"
            )
            
            # Download file
            response = self.client.get_object(self.bucket, object_key)
            file_data = response.read()
            response.close()
            response.release_conn()
            
            # Save to local file
            Path(destination_path).parent.mkdir(parents=True, exist_ok=True)
            with open(destination_path, 'wb') as f:
                f.write(file_data)
            
            logger.info(f"Downloaded S3 file to: {destination_path}")
            
            return {
                "size": len(file_data),
                "content_type": stat.content_type,
                "etag": stat.etag,
                "local_path": destination_path,
            }
            
        except S3Error as e:
            logger.error(f"S3 error downloading {object_key}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error downloading {object_key}: {e}")
            raise
