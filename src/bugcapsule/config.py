"""Environment-backed application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from ``BUGCAPSULE_*`` environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BUGCAPSULE_",
        extra="ignore",
    )

    host: Literal["127.0.0.1", "localhost"] = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    data_dir: Path = Path(".bugcapsule-data")
    demo_telemetry_dir: Path = Path(".bugcapsule-data/demo")
    source_root: Path = Path()
    source_include_root: Path = Path("src")
    source_context_lines: int = Field(default=30, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
