"""Tests for environment-backed settings."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from bugcapsule.config import Settings, get_settings


def test_settings_accept_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCAPSULE_PORT", "9876")
    monkeypatch.setenv("BUGCAPSULE_DATA_DIR", "runtime-data")
    monkeypatch.setenv("BUGCAPSULE_MODEL_MODE", "replay")
    monkeypatch.setenv("BUGCAPSULE_DISPLAY_TIMEZONE", "UTC")

    settings = Settings()

    assert settings.port == 9876
    assert settings.data_dir == Path("runtime-data")
    assert settings.model_mode == "replay"
    assert settings.display_timezone == "UTC"
    assert settings.verification_command[-2:] == ("-o", "addopts=")


def test_settings_reject_public_bind_address(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCAPSULE_HOST", "0.0.0.0")

    with pytest.raises(ValidationError):
        Settings()


def test_settings_reject_invalid_display_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCAPSULE_DISPLAY_TIMEZONE", "Mars/Olympus")

    with pytest.raises(ValidationError, match="valid IANA timezone"):
        Settings()


def test_settings_load_and_validate_patch_path_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUGCAPSULE_PATCH_ALLOWED_ROOTS", '["src","packages"]')
    monkeypatch.setenv("BUGCAPSULE_PATCH_PROTECTED_PATHS", '["tests","uv.lock"]')
    settings = Settings()
    assert settings.patch_allowed_roots == ("src", "packages")
    assert settings.patch_protected_paths == ("tests", "uv.lock")

    monkeypatch.setenv("BUGCAPSULE_PATCH_ALLOWED_ROOTS", '["src","src"]')
    with pytest.raises(ValidationError, match="duplicates"):
        Settings()

    monkeypatch.setenv("BUGCAPSULE_PATCH_ALLOWED_ROOTS", '["../outside"]')
    with pytest.raises(ValidationError, match="traverse"):
        Settings()


def test_get_settings_caches_validated_instance() -> None:
    get_settings.cache_clear()

    settings = get_settings()

    assert get_settings() is settings
    get_settings.cache_clear()
