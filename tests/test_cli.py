"""Tests for the command-line entry point."""

import pytest
from typer.testing import CliRunner

from bugcapsule import __version__
from bugcapsule.cli import app
from bugcapsule.config import get_settings
from bugcapsule.demo.controller import DemoControlError, DemoRunResult

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


class FakeDemoController:
    """Record CLI delegation without requiring Docker."""

    def __init__(self) -> None:
        self.actions: list[str] = []

    def up(self) -> None:
        self.actions.append("up")

    def run(self) -> DemoRunResult:
        self.actions.append("run")
        return DemoRunResult(500, 500, 503, "database_pool_exhausted")

    def reset(self) -> dict[str, object]:
        self.actions.append("reset")
        return {"state": "ready"}

    def down(self) -> None:
        self.actions.append("down")


def test_demo_commands_delegate_to_controller(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = FakeDemoController()
    monkeypatch.setattr("bugcapsule.cli.get_demo_controller", lambda: controller)

    results = [runner.invoke(app, ["demo", command]) for command in ("up", "run", "reset", "down")]

    assert [result.exit_code for result in results] == [0, 0, 0, 0]
    assert controller.actions == ["up", "run", "reset", "down"]
    assert "HTTP 500" in results[1].stdout


def test_demo_command_reports_control_error(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = FakeDemoController()

    def fail() -> None:
        raise DemoControlError("Docker unavailable")

    controller.up = fail  # type: ignore[method-assign]
    monkeypatch.setattr("bugcapsule.cli.get_demo_controller", lambda: controller)

    result = runner.invoke(app, ["demo", "up"])

    assert result.exit_code == 1
