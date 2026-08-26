"""Tests for the command-line entry point."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from bugcapsule import __version__
from bugcapsule.analysis.service import AnalysisError
from bugcapsule.capsule.capture import CaptureError
from bugcapsule.cli import app
from bugcapsule.config import get_settings
from bugcapsule.demo.controller import DemoControlError, DemoRunResult
from bugcapsule.index import CapsuleIndexError
from bugcapsule.patching.service import PatchGenerationError

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


def test_capture_command_prints_destination(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    destination = tmp_path / "cap_test.bugcapsule"

    class FakeCaptureService:
        def capture(self, trace_id: str) -> Path:
            assert trace_id == "1" * 32
            return destination

    class FakeIndex:
        def upsert(self, source: Path) -> None:
            assert source == destination

    monkeypatch.setattr("bugcapsule.cli.CaptureService", lambda _: FakeCaptureService())
    monkeypatch.setattr("bugcapsule.cli.CapsuleIndex.from_settings", lambda _: FakeIndex())

    result = runner.invoke(app, ["capture", "--trace-id", "1" * 32])

    assert result.exit_code == 0
    assert str(destination) in result.stdout


def test_capture_command_reports_capture_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingCaptureService:
        def capture(self, trace_id: str) -> Path:
            raise CaptureError(f"missing {trace_id}")

    monkeypatch.setattr("bugcapsule.cli.CaptureService", lambda _: FailingCaptureService())

    result = runner.invoke(app, ["capture", "--trace-id", "1" * 32])

    assert result.exit_code == 1


def test_analyze_command_emits_result_and_rejects_invalid_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResult:
        def to_dict(self) -> dict[str, object]:
            return {"status": "completed", "mode": "replay", "artifact": {}}

    class FakeAnalysisService:
        def analyze(self, capsule_id: str, *, mode: str | None = None) -> FakeResult:
            assert capsule_id == "cap_stage3_0001"
            assert mode == "replay"
            return FakeResult()

    monkeypatch.setattr("bugcapsule.cli.AnalysisService", lambda _: FakeAnalysisService())

    result = runner.invoke(app, ["analyze", "cap_stage3_0001", "--mode", "replay"])
    invalid = runner.invoke(app, ["analyze", "cap_stage3_0001", "--mode", "invalid"])

    assert result.exit_code == 0
    assert result.stdout.strip() == '{"artifact":{},"mode":"replay","status":"completed"}'
    assert invalid.exit_code == 1
    assert "未知模型模式" in invalid.stderr


def test_analyze_command_reports_safe_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingAnalysisService:
        def analyze(self, capsule_id: str, *, mode: str | None = None) -> None:
            raise AnalysisError(f"record unavailable for {capsule_id}")

    monkeypatch.setattr("bugcapsule.cli.AnalysisService", lambda _: FailingAnalysisService())
    result = runner.invoke(app, ["analyze", "cap_stage3_0001"])
    assert result.exit_code == 1
    assert "分析失败" in result.stderr


def test_patch_generate_command_emits_result_and_reports_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResult:
        def to_dict(self) -> dict[str, object]:
            return {"status": "completed", "mode": "replay", "artifact": {}}

    class FakePatchService:
        def generate(self, capsule_id: str, **kwargs: object) -> FakeResult:
            assert capsule_id == "cap_stage3_0001"
            assert kwargs == {"root_cause_id": "RC-AAAAAAAAAAAA", "mode": "replay"}
            return FakeResult()

    monkeypatch.setattr("bugcapsule.cli.PatchGenerationService", lambda _: FakePatchService())
    result = runner.invoke(
        app,
        [
            "patch",
            "generate",
            "cap_stage3_0001",
            "--root-cause-id",
            "RC-AAAAAAAAAAAA",
            "--mode",
            "replay",
        ],
    )
    invalid = runner.invoke(app, ["patch", "generate", "cap_stage3_0001", "--mode", "invalid"])
    assert result.exit_code == 0
    assert '"status":"completed"' in result.stdout
    assert invalid.exit_code == 1
    assert "未知模型模式" in invalid.stderr

    class FailingPatchService:
        def generate(self, capsule_id: str, **kwargs: object) -> None:
            raise PatchGenerationError(f"unsafe Patch for {capsule_id}")

    monkeypatch.setattr("bugcapsule.cli.PatchGenerationService", lambda _: FailingPatchService())
    failed = runner.invoke(app, ["patch", "generate", "cap_stage3_0001"])
    assert failed.exit_code == 1
    assert "Patch 生成失败" in failed.stderr


def test_index_and_capsule_query_commands_emit_deterministic_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class JsonResult:
        def __init__(self, value: dict[str, object]) -> None:
            self.value = value

        def to_dict(self) -> dict[str, object]:
            return self.value

    class FakeIndex:
        def rebuild(self) -> JsonResult:
            return JsonResult({"indexed_count": 1, "issues": []})

        def list_capsules(self, **kwargs: object) -> tuple[JsonResult, ...]:
            assert kwargs == {
                "query": "demo",
                "analysis_status": "not_run",
                "verification_status": None,
                "sort_by": "time",
                "limit": 5,
            }
            return (JsonResult({"capsule_id": "cap_stage3_0001"}),)

        def get_detail(self, capsule_id: str) -> JsonResult | None:
            if capsule_id == "cap_stage3_0001":
                return JsonResult({"summary": {"capsule_id": capsule_id}})
            return None

    monkeypatch.setattr("bugcapsule.cli.CapsuleIndex.from_settings", lambda _: FakeIndex())

    rebuilt = runner.invoke(app, ["index", "rebuild"])
    listed = runner.invoke(
        app,
        [
            "capsules",
            "list",
            "--query",
            "demo",
            "--analysis-status",
            "not_run",
            "--limit",
            "5",
        ],
    )
    shown = runner.invoke(app, ["capsules", "show", "cap_stage3_0001"])
    missing = runner.invoke(app, ["capsules", "show", "cap_missing"])

    assert rebuilt.exit_code == 0
    assert rebuilt.stdout.strip() == '{"indexed_count":1,"issues":[]}'
    assert listed.exit_code == 0
    assert listed.stdout.strip() == '[{"capsule_id":"cap_stage3_0001"}]'
    assert shown.exit_code == 0
    assert '"cap_stage3_0001"' in shown.stdout
    assert missing.exit_code == 1


def test_index_command_reports_index_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingIndex:
        def rebuild(self) -> None:
            raise CapsuleIndexError("database unavailable")

    monkeypatch.setattr("bugcapsule.cli.CapsuleIndex.from_settings", lambda _: FailingIndex())

    result = runner.invoke(app, ["index", "rebuild"])

    assert result.exit_code == 1
    assert "索引重建失败" in result.stderr
