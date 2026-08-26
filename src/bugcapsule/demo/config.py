"""Environment-backed configuration for the controlled order service."""

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    api_url: str = "http://127.0.0.1:8766"
    compose_file: Path = Path("compose.yml")
    command_timeout_seconds: float = Field(default=180, gt=0, le=600)
    telemetry_enabled: bool = True
    telemetry_dir: Path = Path(".bugcapsule-data/demo")
    container_telemetry_dir: str = "/var/lib/bugcapsule"
    compose_order_service: str = "order-service"
    telemetry_sync_max_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024)
    service_name: str = Field(default="demo-order-api", min_length=1, max_length=120)

    @field_validator("container_telemetry_dir")
    @classmethod
    def validate_container_telemetry_dir(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        path = PurePosixPath(normalized)
        if not normalized or not path.is_absolute() or ".." in path.parts or "\x00" in normalized:
            raise ValueError("container telemetry directory must be a safe absolute POSIX path")
        return normalized

    @field_validator("compose_order_service")
    @classmethod
    def validate_compose_order_service(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(character.isspace() for character in normalized):
            raise ValueError("Compose order service must be a non-empty identifier")
        return normalized
