"""Tests for demo service configuration."""

import pytest
from pydantic import ValidationError

from bugcapsule.demo.config import DemoSettings


def test_demo_settings_require_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BUGCAPSULE_DEMO_DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        DemoSettings(_env_file=None)


def test_demo_pool_defaults_match_fault_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCAPSULE_DEMO_DATABASE_URL", "postgresql+psycopg://local/test")

    settings = DemoSettings(_env_file=None)

    assert settings.pool_size == 2
    assert settings.max_overflow == 0
    assert settings.pool_timeout_seconds == 1.0
    assert settings.container_telemetry_dir == "/var/lib/bugcapsule"
    assert settings.compose_order_service == "order-service"


@pytest.mark.parametrize(
    "value",
    ["relative/path", "/var/lib/../secret", ""],
)
def test_demo_container_telemetry_path_must_be_safe(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("BUGCAPSULE_DEMO_DATABASE_URL", "postgresql+psycopg://local/test")
    monkeypatch.setenv("BUGCAPSULE_DEMO_CONTAINER_TELEMETRY_DIR", value)

    with pytest.raises(ValidationError):
        DemoSettings(_env_file=None)
