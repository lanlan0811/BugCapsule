"""Deterministic capsule fixtures shared by stage-three tests."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from bugcapsule.capsule import (
    CapsuleArchive,
    EnvironmentInfo,
    EvidenceItem,
    EvidenceKind,
    GitInfo,
    ServiceInfo,
    TraceInfo,
    canonical_json,
    create_manifest,
)

TRACE_ID = "1" * 32
ROOT_SPAN_ID = "2" * 16
CHILD_SPAN_ID = "3" * 16
NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def make_stage_three_capsule(
    directory: Path,
    *,
    filename: str = "cap_stage3_0001.bugcapsule",
    capsule_id: str = "cap_stage3_0001",
    service_name: str = "demo-order-api",
    reverse_runtime: bool = False,
) -> tuple[Path, tuple[EvidenceItem, ...]]:
    root = EvidenceItem.create(
        kind=EvidenceKind.TRACE,
        source="traces.jsonl:1",
        captured_at=NOW + timedelta(microseconds=500),
        content={
            "trace_id": TRACE_ID,
            "span_id": ROOT_SPAN_ID,
            "parent_span_id": None,
            "name": "POST /demo/leak",
            "start_time_unix_nano": 100,
            "end_time_unix_nano": 500,
            "status": "ERROR",
        },
        trace_id=TRACE_ID,
        span_id=ROOT_SPAN_ID,
        priority=0,
    )
    child = EvidenceItem.create(
        kind=EvidenceKind.SPAN,
        source="traces.jsonl:2",
        captured_at=NOW + timedelta(microseconds=250),
        content={
            "trace_id": TRACE_ID,
            "span_id": CHILD_SPAN_ID,
            "parent_span_id": ROOT_SPAN_ID,
            "name": "SELECT orders",
            "start_time_unix_nano": 200,
            "end_time_unix_nano": 250,
            "status": "ERROR",
        },
        trace_id=TRACE_ID,
        span_id=CHILD_SPAN_ID,
        priority=20,
    )
    error_log = EvidenceItem.create(
        kind=EvidenceKind.LOG,
        source="logs.jsonl:1",
        captured_at=NOW + timedelta(microseconds=300),
        content={
            "timestamp_unix_nano": 300,
            "level": "ERROR",
            "message": "database pool exhausted",
            "fault": "database_pool_exhausted",
        },
        trace_id=TRACE_ID,
        span_id=ROOT_SPAN_ID,
        priority=10,
    )
    stack = EvidenceItem.create(
        kind=EvidenceKind.STACKTRACE,
        source="logs.exception:1",
        captured_at=NOW + timedelta(microseconds=300),
        content={"stacktrace": "PoolTimeout at src/bugcapsule/demo/database.py:45"},
        trace_id=TRACE_ID,
        span_id=ROOT_SPAN_ID,
        priority=5,
    )
    source = EvidenceItem.create(
        kind=EvidenceKind.SOURCE,
        source="src/bugcapsule/demo/database.py:45",
        captured_at=NOW + timedelta(microseconds=300),
        content={
            "path": "src/bugcapsule/demo/database.py",
            "line": 45,
            "start_line": 43,
            "end_line": 47,
            "text": "session = session_factory()\nsession.execute(statement)",
        },
        trace_id=TRACE_ID,
        span_id=ROOT_SPAN_ID,
        priority=15,
    )
    git = EvidenceItem.create(
        kind=EvidenceKind.GIT,
        source="git:working-tree",
        captured_at=NOW + timedelta(microseconds=500),
        content={"commit_sha": "b" * 40, "branch": "master", "dirty": False, "diff": ""},
        priority=60,
    )
    environment = EvidenceItem.create(
        kind=EvidenceKind.ENVIRONMENT,
        source="runtime:environment",
        captured_at=NOW + timedelta(microseconds=500),
        content={"python_version": "3.12.13", "platform": "Windows-10"},
        priority=80,
    )
    runtime = [root, child, error_log]
    if reverse_runtime:
        runtime.reverse()
    supporting = (stack, source, git, environment)
    payloads = {
        "evidence/traces.jsonl": b"".join(
            canonical_json(item.model_dump(mode="json")) + b"\n"
            for item in runtime
            if item.kind in {EvidenceKind.TRACE, EvidenceKind.SPAN}
        ),
        "evidence/logs.jsonl": b"".join(
            canonical_json(item.model_dump(mode="json")) + b"\n"
            for item in runtime
            if item.kind is EvidenceKind.LOG
        ),
        "evidence/source-snippets.json": canonical_json(
            [item.model_dump(mode="json") for item in supporting]
        )
        + b"\n",
        "redaction-report.json": (
            b'{"completed_at":"2026-08-26T00:00:00Z","findings":[],'
            b'"rule_version":"0.1.0","schema_version":"0.1.0","total_findings":0}\n'
        ),
    }
    media_types = {
        "evidence/traces.jsonl": "application/x-ndjson",
        "evidence/logs.jsonl": "application/x-ndjson",
        "evidence/source-snippets.json": "application/json",
        "redaction-report.json": "application/json",
    }
    manifest = create_manifest(
        capsule_id=capsule_id,
        created_at=NOW,
        service=ServiceInfo(name=service_name, entrypoint="POST /demo/leak"),
        trace=TraceInfo(trace_id=TRACE_ID, root_span_id=ROOT_SPAN_ID),
        git=GitInfo(commit_sha="b" * 40, branch="master", dirty=False),
        environment=EnvironmentInfo(
            python_version="3.12.13",
            platform="Windows-10",
            dependency_lock_sha256="a" * 64,
        ),
        payloads=payloads,
        media_types=media_types,
    )
    destination = directory / filename
    CapsuleArchive().export(destination, manifest, payloads)
    return destination, tuple(runtime) + supporting
