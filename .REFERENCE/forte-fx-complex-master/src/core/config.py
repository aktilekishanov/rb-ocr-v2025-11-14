from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    POSTGRES_DB: str
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int

    # noinspection PyPep8Naming
    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class RedisSettings(BaseSettings):
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str

    # noinspection PyPep8Naming
    @computed_field
    @property
    def CELERY_BROKER_URL(self) -> str:
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    # noinspection PyPep8Naming
    @computed_field
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/1"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class S3Settings(BaseSettings):
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool
    MINIO_BUCKET: str
    MINIO_VERIFY_SSL: str | bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


class AppSettings(BaseSettings):
    CALLBACK_URL: str
    CALLBACK_PRIVATE_KEY: str
    FRONTEND_URL: str
    COMPLIANCE_CONTROL_URL: str
    DMZ_URL: str | None = None
    VERIFY_SSL: str | bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_db_settings() -> DatabaseSettings:
    return DatabaseSettings()   # type: ignore[call-arg]


@lru_cache
def get_redis_settings() -> RedisSettings:
    return RedisSettings()  # type: ignore[call-arg]


@lru_cache
def get_s3_settings() -> S3Settings:
    return S3Settings() # type: ignore[call-arg]


@lru_cache
def get_app_settings() -> AppSettings:
    return AppSettings()    # type: ignore[call-arg]


db_settings = get_db_settings()
redis_settings = get_redis_settings()
s3_settings = get_s3_settings()
app_settings = get_app_settings()