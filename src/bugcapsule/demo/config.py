"""Environment-backed configuration for the controlled order service."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class DemoSettings(BaseSettings):
    """Settings loaded from ``BUGCAPSULE_DEMO_*`` variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BUGCAPSULE_DEMO_",
        extra="ignore",
    )

    database_url: SecretStr
    host: str = "127.0.0.1"
    port: int = Field(default=8766, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    pool_size: int = Field(default=2, ge=1, le=10)
    max_overflow: int = Field(default=0, ge=0, le=10)
    pool_timeout_seconds: float = Field(default=1.0, gt=0, le=30)
