"""Tests for safe Docker and HTTP demo orchestration."""

import json
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


def test_sync_telemetry_uses_compose_cp_and_returns_latest_exhaustion_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}", encoding="utf-8")
    telemetry_dir = tmp_path / "telemetry"
    settings = make_settings(compose_file).model_copy(update={"telemetry_dir": telemetry_dir})
    commands: list[object] = []

    def runner(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        rows = [
            {"fault": "database_pool_exhausted", "trace_id": "1" * 32},
            {"fault": "injected_request_failure", "trace_id": "2" * 32},
            {"fault": "database_pool_exhausted", "trace_id": "3" * 32},
        ]
        (telemetry_dir / "logs.jsonl").write_text(
            "".join(f"{json.dumps(row)}\n" for row in rows),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr("bugcapsule.demo.controller.shutil.which", lambda _: "docker.exe")
    result = DemoController(settings, command_runner=runner).sync_telemetry()

    assert result.trace_id == "3" * 32
    assert result.telemetry_dir == telemetry_dir.resolve()
    assert commands == [
        (
            "docker.exe",
            "compose",
            "--file",
            str(compose_file.resolve()),
            "cp",
            "order-service:/var/lib/bugcapsule/.",
            str(telemetry_dir.resolve()),
        )
    ]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("not-json\n", "有效 JSONL"),
        (json.dumps({"fault": "database_pool_exhausted", "trace_id": "invalid"}), "Trace ID"),
        (json.dumps({"fault": "injected_request_failure", "trace_id": "1" * 32}), "没有"),
    ],
)
def test_sync_telemetry_rejects_unusable_fault_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    message: str,
) -> None:
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}", encoding="utf-8")
    telemetry_dir = tmp_path / "telemetry"
    settings = make_settings(compose_file).model_copy(update={"telemetry_dir": telemetry_dir})

    def runner(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        (telemetry_dir / "logs.jsonl").write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr("bugcapsule.demo.controller.shutil.which", lambda _: "docker.exe")

    with pytest.raises(DemoControlError, match=message):
        DemoController(settings, command_runner=runner).sync_telemetry()


@pytest.mark.parametrize(
    ("content", "settings_update", "message"),
    [
        ("[]\n", {}, "不是 JSON 对象"),
        (" " * 1025, {"telemetry_sync_max_bytes": 1024}, "超过"),
    ],
)
def test_sync_telemetry_rejects_non_object_and_oversized_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content: str,
    settings_update: dict[str, object],
    message: str,
) -> None:
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}", encoding="utf-8")
    telemetry_dir = tmp_path / "telemetry"
    settings = make_settings(compose_file).model_copy(
        update={"telemetry_dir": telemetry_dir, **settings_update}
    )

    def runner(command: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        telemetry_dir.mkdir(parents=True, exist_ok=True)
        (telemetry_dir / "logs.jsonl").write_text(content, encoding="utf-8")
        return subprocess.CompletedProcess([], 0, "", "")

    monkeypatch.setattr("bugcapsule.demo.controller.shutil.which", lambda _: "docker.exe")

    with pytest.raises(DemoControlError, match=message):
        DemoController(settings, command_runner=runner).sync_telemetry()


def test_sync_telemetry_requires_copied_log_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}", encoding="utf-8")
    settings = make_settings(compose_file).model_copy(
        update={"telemetry_dir": tmp_path / "telemetry"}
    )
    monkeypatch.setattr("bugcapsule.demo.controller.shutil.which", lambda _: "docker.exe")
    controller = DemoController(
        settings,
        command_runner=lambda *args, **kwargs: subprocess.CompletedProcess([], 0, "", ""),
    )

    with pytest.raises(DemoControlError, match="缺少"):
        controller.sync_telemetry()
