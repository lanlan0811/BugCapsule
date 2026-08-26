"""Tests for environment-backed settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from bugcapsule.config import Settings, get_settings


def test_settings_accept_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCAPSULE_PORT", "9876")
    monkeypatch.setenv("BUGCAPSULE_DATA_DIR", "runtime-data")

    settings = Settings()

    assert settings.port == 9876
    assert settings.data_dir == Path("runtime-data")


def test_settings_reject_public_bind_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCAPSULE_HOST", "0.0.0.0")

    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_caches_validated_instance() -> None:
    get_settings.cache_clear()

    settings = get_settings()

    assert get_settings() is settings
    get_settings.cache_clear()
