"""Tests for safe Docker and HTTP demo orchestration."""

import subprocess
from pathlib import Path

import httpx
import pytest

from bugcapsule.demo.config import DemoSettings
from bugcapsule.demo.controller import DemoControlError, DemoController


def make_settings(compose_file: Path) -> DemoSettings:
    return DemoSettings(
        database_url="sqlite+pysqlite:///:memory:",
        api_url="http://demo.test",
        compose_file=compose_file,
        pool_timeout_seconds=0.01,
    )


def test_run_requires_expected_fault_sequence(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/demo/reset":
            return httpx.Response(200, json={"state": "ready"})
        calls += 1
        status_code = 503 if calls == 3 else 500
        fault = "database_pool_exhausted" if calls == 3 else "injected_request_failure"
        return httpx.Response(status_code, json={"detail": {"fault": fault}})

    controller = DemoController(
        make_settings(tmp_path / "compose.yml"),
        http_transport=httpx.MockTransport(handler),
    )

    result = controller.run()

    assert (result.first_status, result.second_status, result.exhausted_status) == (500, 500, 503)
    assert result.fault == "database_pool_exhausted"


def test_compose_uses_argument_list_without_shell(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}", encoding="utf-8")
    captured: dict[str, object] = {}

    def runner(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr("bugcapsule.demo.controller.shutil.which", lambda _: "docker.exe")
    controller = DemoController(make_settings(compose_file), command_runner=runner)

    controller.up()
    controller.down()

    command = captured["command"]
    assert isinstance(command, tuple)
    assert command[:4] == ("docker.exe", "compose", "--file", str(compose_file.resolve()))
    kwargs = captured["kwargs"]
    assert isinstance(kwargs, dict)
    assert "shell" not in kwargs


def test_compose_reports_missing_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("bugcapsule.demo.controller.shutil.which", lambda _: None)
    controller = DemoController(make_settings(tmp_path / "compose.yml"))

    with pytest.raises(DemoControlError, match="Docker CLI"):
        controller.up()
