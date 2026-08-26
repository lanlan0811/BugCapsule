"""OpenTelemetry tracing and trace-correlated redacted JSONL logging."""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from sqlalchemy import Engine

from bugcapsule import __version__
from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.capsule.redaction import Redactor
from bugcapsule.demo.config import DemoSettings


def json_compatible(value: Any) -> Any:
    """Normalize OpenTelemetry attribute types into JSON-compatible values."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {str(key): json_compatible(child) for key, child in value.items()}
    if isinstance(value, Sequence):
        return [json_compatible(child) for child in value]
    return str(value)


class TelemetryWriter:
    """Serialize redacted Trace, Log, and redaction audit records under one lock."""

    def __init__(self, directory: Path, redactor: Redactor | None = None) -> None:
        self.directory = directory
        self.redactor = redactor or Redactor()
        self._lock = threading.Lock()
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, stream: str, payload: object, *, captured_at: datetime) -> None:
        result = self.redactor.redact(payload, completed_at=captured_at)
        with self._lock:
            self._append(self.directory / f"{stream}.jsonl", result.value)
            if result.report.findings:
                self._append(
                    self.directory / "redaction-findings.jsonl",
                    result.report.model_dump(mode="json"),
                )

    @staticmethod
    def _append(path: Path, value: object) -> None:
        with path.open("ab") as handle:
            handle.write(canonical_json(value))
            handle.write(b"\n")


class JsonlSpanExporter(SpanExporter):
    """Export completed spans directly to a local redacted JSONL stream."""

    def __init__(self, writer: TelemetryWriter) -> None:
        self.writer = writer

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        for span in spans:
            context = span.context
            parent = span.parent
            payload = {
                "trace_id": f"{context.trace_id:032x}" if context else None,
                "span_id": f"{context.span_id:016x}" if context else None,
                "parent_span_id": f"{parent.span_id:016x}" if parent else None,
                "name": span.name,
                "kind": span.kind.name,
                "start_time_unix_nano": span.start_time,
                "end_time_unix_nano": span.end_time,
                "status": span.status.status_code.name,
                "status_description": span.status.description,
                "attributes": json_compatible(span.attributes or {}),
                "events": [
                    {
                        "name": event.name,
                        "timestamp_unix_nano": event.timestamp,
                        "attributes": json_compatible(event.attributes or {}),
                    }
                    for event in span.events
                ],
            }
            captured_at = datetime.now(timezone.utc)
            if span.end_time is not None:
                captured_at = datetime.fromtimestamp(span.end_time / 1_000_000_000, timezone.utc)
            self.writer.write("traces", payload, captured_at=captured_at)
        return SpanExportResult.SUCCESS


class JsonlLogHandler(logging.Handler):
    """Write standard LogRecords with the active OpenTelemetry context."""

    def __init__(self, writer: TelemetryWriter) -> None:
        super().__init__()
        self.writer = writer
        self._exception_formatter = logging.Formatter()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            span_context = trace.get_current_span().get_span_context()
            payload = {
                "timestamp_unix_nano": int(record.created * 1_000_000_000),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "trace_id": f"{span_context.trace_id:032x}" if span_context.is_valid else None,
                "span_id": f"{span_context.span_id:016x}" if span_context.is_valid else None,
                "fault": getattr(record, "fault", None),
                "leaked_sessions": getattr(record, "leaked_sessions", None),
                "order_id": getattr(record, "order_id", None),
                "exception": (
                    self._exception_formatter.formatException(record.exc_info)
                    if record.exc_info
                    else None
                ),
            }
            captured_at = datetime.fromtimestamp(record.created, timezone.utc)
            self.writer.write("logs", payload, captured_at=captured_at)
        except Exception:
            self.handleError(record)


class ObservabilityRuntime:
    """Own instrumentation and ensure it is removed during app shutdown."""

    def __init__(
        self,
        *,
        application: FastAPI,
        provider: TracerProvider,
        sqlalchemy_instrumentor: SQLAlchemyInstrumentor,
        logger: logging.Logger,
        log_handler: JsonlLogHandler,
    ) -> None:
        self.application = application
        self.provider = provider
        self.sqlalchemy_instrumentor = sqlalchemy_instrumentor
        self.logger = logger
        self.log_handler = log_handler

    def shutdown(self) -> None:
        self.logger.removeHandler(self.log_handler)
        self.log_handler.close()
        self.sqlalchemy_instrumentor.uninstrument()
        FastAPIInstrumentor.uninstrument_app(self.application)
        self.provider.shutdown()


def configure_observability(
    application: FastAPI,
    engine: Engine,
    settings: DemoSettings,
) -> ObservabilityRuntime:
    """Instrument one demo application without replacing the global provider."""
    writer = TelemetryWriter(settings.telemetry_dir)
    resource = Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": __version__,
            "deployment.environment.name": "simulated-demo",
        }
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(SimpleSpanProcessor(JsonlSpanExporter(writer)))
    FastAPIInstrumentor.instrument_app(
        application,
        tracer_provider=provider,
        excluded_urls="healthz",
    )
    sqlalchemy_instrumentor = SQLAlchemyInstrumentor()
    sqlalchemy_instrumentor.instrument(engine=engine, tracer_provider=provider)

    logger = logging.getLogger("bugcapsule.demo")
    logger.setLevel(settings.log_level)
    logger.propagate = False
    log_handler = JsonlLogHandler(writer)
    logger.addHandler(log_handler)
    return ObservabilityRuntime(
        application=application,
        provider=provider,
        sqlalchemy_instrumentor=sqlalchemy_instrumentor,
        logger=logger,
        log_handler=log_handler,
    )
