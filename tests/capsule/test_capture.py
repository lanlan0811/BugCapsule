"""End-to-end test for assembling local evidence into a valid capsule."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bugcapsule.capsule import CapsuleArchive, EvidenceItem
from bugcapsule.capsule.capture import CaptureError, CaptureService, GitCollector, GitSnapshot
from bugcapsule.capsule.redaction import Redactor
from bugcapsule.config import Settings

TRACE_ID = "1" * 32
SPAN_ID = "2" * 16


class FakeGitCollector:
    def snapshot(self, source_root: Path) -> GitSnapshot:
        assert source_root.is_dir()
        return GitSnapshot(commit_sha="b" * 40, branch="master", dirty=False, diff="")


def write_jsonl(path: Path, values: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(value) + "\n" for value in values), encoding="utf-8")


def test_capture_builds_importable_redacted_capsule(tmp_path: Path) -> None:
    source_file = tmp_path / "src" / "app.py"
    source_file.parent.mkdir(parents=True)
    source_file.write_text(
        "def leak():\n    token = 'sk-exampleabcdefghijklmnop'\n    raise RuntimeError()\n",
        encoding="utf-8",
    )
    (tmp_path / "uv.lock").write_text("version = 1\n", encoding="utf-8")
    telemetry = tmp_path / "telemetry"
    write_jsonl(
        telemetry / "traces.jsonl",
        [
            {
                "trace_id": TRACE_ID,
                "span_id": SPAN_ID,
                "parent_span_id": None,
                "name": "POST /demo/leak",
                "end_time_unix_nano": 1787700000000000000,
                "attributes": {"http.method": "POST", "http.route": "/demo/leak"},
                "resource": {"service.name": "demo-order-api"},
            }
        ],
    )
    write_jsonl(
        telemetry / "logs.jsonl",
        [
            {
                "trace_id": TRACE_ID,
                "span_id": SPAN_ID,
                "timestamp_unix_nano": 1787700000000000000,
                "level": "ERROR",
                "message": "failed for dev@example.com",
                "exception": f'Traceback\n  File "{source_file}", line 3\nRuntimeError',
            }
        ],
    )
    audit_time = datetime(2026, 8, 26, tzinfo=timezone.utc)
    target_report = (
        Redactor()
        .redact(
            {"message": "target@example.com"},
            completed_at=audit_time,
        )
        .report
    )
    other_report = (
        Redactor()
        .redact(
            {"message": "13800138000"},
            completed_at=audit_time,
        )
        .report
    )
    write_jsonl(
        telemetry / "redaction-findings.jsonl",
        [
            {
                "stream": "logs",
                "trace_id": TRACE_ID,
                "report": target_report.model_dump(mode="json"),
            },
            {
                "stream": "logs",
                "trace_id": "9" * 32,
                "report": other_report.model_dump(mode="json"),
            },
        ],
    )
    settings = Settings(
        data_dir=tmp_path / "data",
        demo_telemetry_dir=telemetry,
        source_root=tmp_path,
        source_include_root=Path("src"),
        source_context_lines=2,
    )
    service = CaptureService(settings, git_collector=FakeGitCollector())

    destination = service.capture(TRACE_ID)
    imported = CapsuleArchive().import_capsule(destination)
    all_bytes = b"".join(imported.payloads.values())
    supporting = json.loads(imported.read("evidence/source-snippets.json"))
    redaction_report = json.loads(imported.read("redaction-report.json"))

    assert imported.manifest.trace.trace_id == TRACE_ID
    assert imported.manifest.service.entrypoint == "POST /demo/leak"
    assert b"dev@example.com" not in all_bytes
    assert b"sk-exampleabcdefghijklmnop" not in all_bytes
    source_items = [
        EvidenceItem.model_validate(item) for item in supporting if item["kind"] == "source"
    ]
    assert source_items
    assert source_items[0].trace_id == TRACE_ID
    assert source_items[0].span_id == SPAN_ID
    finding_ids = {item["finding_id"] for item in redaction_report["findings"]}
    assert target_report.findings[0].finding_id in finding_ids
    assert other_report.findings[0].finding_id not in finding_ids


def test_capture_rejects_invalid_or_missing_trace(tmp_path: Path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        demo_telemetry_dir=tmp_path / "telemetry",
        source_root=tmp_path,
    )
    service = CaptureService(settings, git_collector=FakeGitCollector())

    with pytest.raises(CaptureError, match="32 lowercase"):
        service.capture("invalid")
    with pytest.raises(CaptureError, match="not found"):
        service.capture(TRACE_ID)


def test_git_collector_uses_fixed_non_shell_commands(tmp_path: Path) -> None:
    outputs = {
        ("rev-parse", "HEAD"): "b" * 40,
        ("branch", "--show-current"): "master",
        ("status", "--porcelain=v1"): " M file.py",
        ("diff", "--no-ext-diff", "--unified=3"): "diff --git a/file.py b/file.py",
    }
    calls: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, outputs[command[1:]], "")

    snapshot = GitCollector(runner).snapshot(tmp_path)

    assert snapshot.dirty is True
    assert snapshot.branch == "master"
    assert all(command[0] == "git" for command in calls)


def test_git_collector_reports_command_failure(tmp_path: Path) -> None:
    def runner(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "failure")

    with pytest.raises(CaptureError, match="Git evidence command failed"):
        GitCollector(runner).snapshot(tmp_path)
