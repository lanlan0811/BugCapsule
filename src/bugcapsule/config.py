"""Environment-backed application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
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
    model_mode: Literal["live", "replay", "off"] = "off"
    model_api_style: Literal["responses", "chat_completions"] = "responses"
    model_base_url: AnyHttpUrl = AnyHttpUrl("https://api.openai.com/v1")
    model_api_key: SecretStr | None = None
    model_name: str = ""
    model_provider: str = "openai-compatible"
    model_timeout_seconds: float = Field(default=60.0, ge=1, le=300)
    model_max_output_tokens: int = Field(default=2000, ge=256, le=16384)
    model_max_input_bytes: int = Field(default=64 * 1024, ge=4096, le=1024 * 1024)
    replay_dir: Path = Path(".bugcapsule-data/replay")
    display_timezone: str = "Asia/Shanghai"
    max_import_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    data_dir: Path = Path(".bugcapsule-data")
    demo_telemetry_dir: Path = Path(".bugcapsule-data/demo")
    source_root: Path = Path()
    source_include_root: Path = Path("src")
    source_context_lines: int = Field(default=30, ge=1, le=100)

    @field_validator("model_name", "model_provider")
    @classmethod
    def strip_model_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("display_timezone")
    @classmethod
    def validate_display_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("display_timezone must be a valid IANA timezone") from exc
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
