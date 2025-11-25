from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Try Pydantic v2 settings; fall back to a simple env reader if not available.
try:
    from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore
    from pydantic import Field  # type: ignore

    def _default_runs_dir() -> Path:
        # apps/idp-loan-deferment-service/runs
        return (Path(__file__).resolve().parents[2] / "runs").resolve()

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="IDP_")
        APP_NAME: str = Field(default="idp-loan-deferment-service")
        ENV: str = Field(default="dev")
        LOG_LEVEL: str = Field(default="INFO")
        RUNS_DIR: Path = Field(default_factory=_default_runs_dir)
        TRACING_ENABLED: bool = Field(default=False)

except Exception:  # pragma: no cover

    class Settings:  # minimal fallback, no pydantic dependency
        def __init__(self) -> None:
            self.APP_NAME: str = os.getenv("IDP_APP_NAME", "idp-loan-deferment-service")
            self.ENV: str = os.getenv("IDP_ENV", "dev")
            self.LOG_LEVEL: str = os.getenv("IDP_LOG_LEVEL", "INFO")
            self.RUNS_DIR: Path = (
                Path(os.getenv("IDP_RUNS_DIR", "")).resolve()
                if os.getenv("IDP_RUNS_DIR")
                else (Path(__file__).resolve().parents[2] / "runs").resolve()
            )
            self.TRACING_ENABLED: bool = os.getenv("IDP_TRACING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
