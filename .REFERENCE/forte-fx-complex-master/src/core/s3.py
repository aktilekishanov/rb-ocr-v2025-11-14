import ssl
import urllib3
from minio import Minio

from src.core.config import s3_settings


class S3Client:
    def __init__(self):
        http_client = None

        if isinstance(s3_settings.MINIO_VERIFY_SSL, str):
            ctx = ssl.create_default_context(cafile=s3_settings.MINIO_VERIFY_SSL)
            http_client = urllib3.PoolManager(ssl_context=ctx)
        elif not s3_settings.MINIO_VERIFY_SSL:
            http_client = urllib3.PoolManager(
                cert_reqs=ssl.CERT_NONE,
                assert_hostname=False
            )

        self.client = Minio(
            s3_settings.MINIO_ENDPOINT,
            access_key=s3_settings.MINIO_ACCESS_KEY,
            secret_key=s3_settings.MINIO_SECRET_KEY,
            secure=s3_settings.MINIO_SECURE,
            region="random-place-in-ekibastuz",
            http_client=http_client
        )
        self.bucket = s3_settings.MINIO_BUCKET

    def _normalize_key(self, key: str) -> str:
        """
        Expect a pure object key (no scheme, no bucket). Be defensive:
        - strip leading slashes
        - if someone accidentally sends 'bucket/key' and bucket matches, strip it
        """
        k = key.strip().lstrip("/")
        prefix = f"{self.bucket}/"
        if k.startswith(prefix):
            k = k[len(prefix):]
        return k

    def download_bytes(self, key: str) -> bytes | None:
        k = self._normalize_key(key)
        resp = self.client.get_object(self.bucket, k)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()
