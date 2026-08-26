"""Tests for the command-line entry point."""

import pytest
from typer.testing import CliRunner

from bugcapsule import __version__
from bugcapsule.cli import app
from bugcapsule.config import get_settings

runner = CliRunner()


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"BugCapsule {__version__}"


def test_no_arguments_shows_help() -> None:
    result = runner.invoke(app)

    assert result.exit_code == 2
    assert "Usage: bugcapsule" in result.stdout


def test_serve_uses_validated_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(application: str, *, host: str, port: int, log_level: str) -> None:
        captured.update(
            application=application,
            host=host,
            port=port,
            log_level=log_level,
        )

    monkeypatch.setenv("BUGCAPSULE_PORT", "9876")
    monkeypatch.setattr("bugcapsule.cli.uvicorn.run", fake_run)
    get_settings.cache_clear()

    result = runner.invoke(app, ["serve"])

    get_settings.cache_clear()
    assert result.exit_code == 0
    assert captured == {
        "application": "bugcapsule.app:app",
        "host": "127.0.0.1",
        "port": 9876,
        "log_level": "info",
    }
