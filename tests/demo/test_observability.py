"""Integration test for OpenTelemetry spans and trace-correlated logs."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from bugcapsule.demo.app import create_demo_app
from bugcapsule.demo.config import DemoSettings
from bugcapsule.demo.observability import TelemetryWriter


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_fault_log_trace_context_matches_exported_http_span(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    settings = DemoSettings(
        database_url=f"sqlite+pysqlite:///{(tmp_path / 'demo.db').as_posix()}",
        pool_timeout_seconds=0.01,
        telemetry_dir=telemetry_dir,
    )
    application = create_demo_app(settings)

    async def run_request() -> None:
        transport = httpx.ASGITransport(app=application)
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/demo/leak")
                assert response.status_code == 500

    asyncio.run(run_request())

    spans = read_jsonl(telemetry_dir / "traces.jsonl")
    logs = read_jsonl(telemetry_dir / "logs.jsonl")
    failure_log = next(item for item in logs if item["fault"] == "injected_request_failure")
    same_trace_spans = [item for item in spans if item["trace_id"] == failure_log["trace_id"]]

    assert failure_log["span_id"] is not None
    assert any("/demo/leak" in item["name"] for item in same_trace_spans)
    assert any(item["attributes"].get("db.system") == "sqlite" for item in same_trace_spans)
    assert all(len(item["trace_id"]) == 32 for item in same_trace_spans)


def test_telemetry_redaction_audit_is_bound_to_trace(tmp_path: Path) -> None:
    writer = TelemetryWriter(tmp_path)

    writer.write(
        "logs",
        {"trace_id": "1" * 32, "message": "contact dev@example.com"},
        captured_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    audit = read_jsonl(tmp_path / "redaction-findings.jsonl")[0]
    logs = read_jsonl(tmp_path / "logs.jsonl")
    assert audit["trace_id"] == "1" * 32
    assert audit["stream"] == "logs"
    assert audit["report"]["total_findings"] == 1
    assert "dev@example.com" not in json.dumps(logs)
