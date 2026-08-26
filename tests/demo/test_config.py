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
