"""
Centralized application settings using Pydantic.

All environment variables are read once at startup and validated.
Use this instead of scattered os.getenv() calls throughout the codebase.
"""

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class DatabaseSettings(BaseSettings):
    """Database connection and pool configuration."""

    DB_HOST: str
    DB_PORT: int = 5432
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: SecretStr
    DB_POOL_MIN_SIZE: int = 5
    DB_POOL_MAX_SIZE: int = 30
    DB_POOL_TIMEOUT: float = 10.0
    DB_COMMAND_TIMEOUT: float = 10.0

    model_config = {"case_sensitive": True, "env_file": ".env", "extra": "ignore"}


class S3Settings(BaseSettings):
    """S3/MinIO storage configuration."""

    S3_ENDPOINT: str
    S3_ACCESS_KEY: str
    S3_SECRET_KEY: SecretStr
    S3_BUCKET: str
    S3_SECURE: bool = True

    model_config = {"case_sensitive": True, "env_file": ".env", "extra": "ignore"}


class OCRSettings(BaseSettings):
    """OCR service configuration."""

    OCR_BASE_URL: str

    model_config = {"case_sensitive": True, "env_file": ".env", "extra": "ignore"}


class LLMSettings(BaseSettings):
    """LLM service configuration."""

    LLM_ENDPOINT_URL: str

    model_config = {"case_sensitive": True, "env_file": ".env", "extra": "ignore"}


class WebhookSettings(BaseSettings):
    """Webhook client configuration."""

    WEBHOOK_URL: str
    WEBHOOK_USERNAME: str
    WEBHOOK_PASSWORD: SecretStr

    model_config = {"case_sensitive": True, "env_file": ".env", "extra": "ignore"}


class AppSettings(BaseSettings):
    """General application settings."""

    LOG_LEVEL: str = "INFO"
    TZ: str = "Asia/Almaty"
    RB_IDP_RUNS_DIR: str = "./runs"

    model_config = {"case_sensitive": True, "env_file": ".env", "extra": "ignore"}

    @property
    def runs_dir(self):
        """Resolve runs directory path from environment variable."""
        from pathlib import Path

        env_runs_dir = self.RB_IDP_RUNS_DIR.strip()
        if env_runs_dir:
            return Path(env_runs_dir).resolve()
        return Path(__file__).resolve().parents[1] / "runs"


# Singleton instances - loaded once at module import
db_settings = DatabaseSettings()
s3_settings = S3Settings()
ocr_settings = OCRSettings()
llm_settings = LLMSettings()
webhook_settings = WebhookSettings()
app_settings = AppSettings()
