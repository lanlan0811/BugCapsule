"""Build a validated capsule from local telemetry, source, Git, and environment evidence."""

from __future__ import annotations

import platform
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from pydantic import JsonValue, TypeAdapter, ValidationError

from bugcapsule.capsule.archive import CapsuleArchive, create_manifest
from bugcapsule.capsule.identifiers import canonical_json, sha256_hex
from bugcapsule.capsule.redaction import Redactor
from bugcapsule.capsule.schema import (
    EnvironmentInfo,
    EvidenceItem,
    EvidenceKind,
    GitInfo,
    RedactionFinding,
    RedactionReport,
    ServiceInfo,
    TraceInfo,
)
from bugcapsule.config import Settings

JsonObject = dict[str, JsonValue]
JSON_OBJECT_ADAPTER: TypeAdapter[JsonObject] = TypeAdapter(JsonObject)
STACK_FRAME_PATTERN = re.compile(r'^\s*File "(?P<path>[^"]+)", line (?P<line>\d+)', re.MULTILINE)
GitRunner = Callable[..., subprocess.CompletedProcess[str]]


class CaptureError(ValueError):
    """Raised when requested evidence is missing, malformed, or outside policy."""


@dataclass(frozen=True)
class GitSnapshot:
    """Captured Git revision and uncommitted textual diff."""

    commit_sha: str
    branch: str
    dirty: bool
    diff: str


class GitSnapshotProvider(Protocol):
    """Structural interface for Git evidence collection."""

    def snapshot(self, source_root: Path) -> GitSnapshot: ...


class GitCollector:
    """Collect Git facts through fixed argument lists without a shell."""

    def __init__(self, runner: GitRunner = subprocess.run) -> None:
        self._runner = runner

    def snapshot(self, source_root: Path) -> GitSnapshot:
        commit_sha = self._run(source_root, "rev-parse", "HEAD")
        branch = self._run(source_root, "branch", "--show-current")
        status = self._run(source_root, "status", "--porcelain=v1")
        diff = self._run(source_root, "diff", "--no-ext-diff", "--unified=3")
        return GitSnapshot(
            commit_sha=commit_sha,
            branch=branch or "detached",
            dirty=bool(status),
            diff=diff,
        )

    def _run(self, source_root: Path, *arguments: str) -> str:
        result = self._runner(
            ("git", *arguments),
            cwd=source_root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        if result.returncode != 0:
            raise CaptureError(f"Git evidence command failed: {' '.join(arguments)}")
        return result.stdout.strip()


class CaptureService:
    """Assemble one trace into a deterministic, integrity-protected capsule."""

    def __init__(
        self,
        settings: Settings,
        *,
        git_collector: GitSnapshotProvider | None = None,
        redactor: Redactor | None = None,
        archive: CapsuleArchive | None = None,
    ) -> None:
        self.settings = settings
        self.git_collector = git_collector or GitCollector()
        self.redactor = redactor or Redactor()
        self.archive = archive or CapsuleArchive()

    def capture(self, trace_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", trace_id):
            raise CaptureError("trace_id must be 32 lowercase hexadecimal characters")
        telemetry_dir = self.settings.demo_telemetry_dir.resolve()
        spans = self._matching_records(telemetry_dir / "traces.jsonl", trace_id)
        logs = self._matching_records(telemetry_dir / "logs.jsonl", trace_id)
        if not spans:
            raise CaptureError(f"trace evidence not found: {trace_id}")

        root_span = self._root_span(spans)
        captured_at = self._record_time(root_span)
        git = self.git_collector.snapshot(self.settings.source_root.resolve())
        findings = self._existing_findings(
            telemetry_dir / "redaction-findings.jsonl",
            trace_id,
        )

        trace_evidence = tuple(
            self._evidence_from_record(record, line_number, captured_at, findings)
            for line_number, record in spans
        )
        log_evidence = tuple(
            self._log_evidence(record, line_number, captured_at, findings)
            for line_number, record in logs
        )
        supporting_evidence = self._supporting_evidence(logs, git, captured_at, findings)
        report = self._redaction_report(captured_at, findings)

        payloads = {
            "evidence/traces.jsonl": self._jsonl(trace_evidence),
            "evidence/logs.jsonl": self._jsonl(log_evidence),
            "evidence/source-snippets.json": canonical_json(
                [item.model_dump(mode="json") for item in supporting_evidence]
            )
            + b"\n",
            "redaction-report.json": canonical_json(report.model_dump(mode="json")) + b"\n",
        }
        media_types = {
            "evidence/traces.jsonl": "application/x-ndjson",
            "evidence/logs.jsonl": "application/x-ndjson",
            "evidence/source-snippets.json": "application/json",
            "redaction-report.json": "application/json",
        }
        lock_path = self.settings.source_root.resolve() / "uv.lock"
        if not lock_path.is_file():
            raise CaptureError(f"dependency lock file does not exist: {lock_path}")
        diff_sha = sha256_hex(git.diff.encode("utf-8")) if git.diff else None
        capsule_identity = {"trace_id": trace_id, "git": git.commit_sha}
        capsule_id = f"cap_{sha256_hex(canonical_json(capsule_identity))[:16]}"
        attributes = root_span[1].get("attributes", {})
        if not isinstance(attributes, dict):
            attributes = {}
        method = str(
            attributes.get("http.request.method") or attributes.get("http.method") or "HTTP"
        )
        route = str(attributes.get("http.route") or attributes.get("url.path") or "unknown")
        service_name = self._service_name(root_span[1])
        manifest = create_manifest(
            capsule_id=capsule_id,
            created_at=captured_at,
            service=ServiceInfo(name=service_name, entrypoint=f"{method} {route}"),
            trace=TraceInfo(trace_id=trace_id, root_span_id=str(root_span[1]["span_id"])),
            git=GitInfo(
                commit_sha=git.commit_sha,
                branch=git.branch,
                dirty=git.dirty,
                diff_sha256=diff_sha,
            ),
            environment=EnvironmentInfo(
                python_version=platform.python_version(),
                platform=platform.platform(),
                dependency_lock_sha256=sha256_hex(lock_path.read_bytes()),
            ),
            payloads=payloads,
            media_types=media_types,
        )
        destination = self.settings.data_dir.resolve() / "capsules" / f"{capsule_id}.bugcapsule"
        return self.archive.export(destination, manifest, payloads)

    @staticmethod
    def _matching_records(path: Path, trace_id: str) -> list[tuple[int, JsonObject]]:
        if not path.is_file():
            return []
        matches: list[tuple[int, JsonObject]] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = JSON_OBJECT_ADAPTER.validate_json(line)
            except ValidationError as exc:
                raise CaptureError(f"invalid JSONL record: {path}:{line_number}") from exc
            if record.get("trace_id") == trace_id:
                matches.append((line_number, record))
        return matches

    @staticmethod
    def _root_span(spans: list[tuple[int, JsonObject]]) -> tuple[int, JsonObject]:
        roots = [item for item in spans if item[1].get("parent_span_id") is None]
        candidates = roots or spans

        def end_time(item: tuple[int, JsonObject]) -> int:
            value = item[1].get("end_time_unix_nano")
            return value if isinstance(value, int) and not isinstance(value, bool) else 0

        return max(candidates, key=end_time)

    @staticmethod
    def _record_time(item: tuple[int, JsonObject]) -> datetime:
        nanoseconds = item[1].get("end_time_unix_nano")
        if not isinstance(nanoseconds, int):
            raise CaptureError("root span is missing end_time_unix_nano")
        return datetime.fromtimestamp(nanoseconds / 1_000_000_000, timezone.utc)

    def _evidence_from_record(
        self,
        record: JsonObject,
        line_number: int,
        fallback_time: datetime,
        findings: list[RedactionFinding],
    ) -> EvidenceItem:
        captured_at = fallback_time
        end_time = record.get("end_time_unix_nano")
        if isinstance(end_time, int):
            captured_at = datetime.fromtimestamp(end_time / 1_000_000_000, timezone.utc)
        content = self._redact_object(record, captured_at, f"$/traces/{line_number}", findings)
        kind = EvidenceKind.TRACE if record.get("parent_span_id") is None else EvidenceKind.SPAN
        return EvidenceItem.create(
            kind=kind,
            source=f"traces.jsonl:{line_number}",
            captured_at=captured_at,
            content=content,
            trace_id=str(record["trace_id"]),
            span_id=str(record["span_id"]),
            priority=0 if kind is EvidenceKind.TRACE else 20,
        )

    def _log_evidence(
        self,
        record: JsonObject,
        line_number: int,
        fallback_time: datetime,
        findings: list[RedactionFinding],
    ) -> EvidenceItem:
        captured_at = fallback_time
        timestamp = record.get("timestamp_unix_nano")
        if isinstance(timestamp, int):
            captured_at = datetime.fromtimestamp(timestamp / 1_000_000_000, timezone.utc)
        content = self._redact_object(record, captured_at, f"$/logs/{line_number}", findings)
        return EvidenceItem.create(
            kind=EvidenceKind.LOG,
            source=f"logs.jsonl:{line_number}",
            captured_at=captured_at,
            content=content,
            trace_id=str(record["trace_id"]),
            span_id=str(record["span_id"]) if record.get("span_id") else None,
            priority=10 if record.get("level") in {"ERROR", "CRITICAL"} else 40,
        )

    def _supporting_evidence(
        self,
        logs: list[tuple[int, JsonObject]],
        git: GitSnapshot,
        captured_at: datetime,
        findings: list[RedactionFinding],
    ) -> tuple[EvidenceItem, ...]:
        items: list[EvidenceItem] = []
        exceptions = [record for _, record in logs if record.get("exception")]
        for index, record in enumerate(exceptions, start=1):
            exception = record.get("exception")
            if not isinstance(exception, str):
                continue
            exception_time = self._log_record_time(record, captured_at)
            trace_id = str(record["trace_id"]) if record.get("trace_id") else None
            span_id = str(record["span_id"]) if record.get("span_id") else None
            content = self._redact_object(
                {"stacktrace": exception},
                exception_time,
                f"$/stacktraces/{index}",
                findings,
            )
            items.append(
                EvidenceItem.create(
                    kind=EvidenceKind.STACKTRACE,
                    source=f"logs.exception:{index}",
                    captured_at=exception_time,
                    content=content,
                    trace_id=trace_id,
                    span_id=span_id,
                    priority=5,
                )
            )
            items.extend(
                self._source_evidence(
                    exception,
                    exception_time,
                    findings,
                    trace_id=trace_id,
                    span_id=span_id,
                )
            )

        git_content = self._redact_object(
            {
                "commit_sha": git.commit_sha,
                "branch": git.branch,
                "dirty": git.dirty,
                "diff": git.diff,
            },
            captured_at,
            "$/git",
            findings,
        )
        items.append(
            EvidenceItem.create(
                kind=EvidenceKind.GIT,
                source="git:working-tree",
                captured_at=captured_at,
                content=git_content,
                priority=60,
            )
        )
        environment_content = self._redact_object(
            {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
            captured_at,
            "$/environment",
            findings,
        )
        items.append(
            EvidenceItem.create(
                kind=EvidenceKind.ENVIRONMENT,
                source="runtime:environment",
                captured_at=captured_at,
                content=environment_content,
                priority=80,
            )
        )
        return tuple(sorted(items, key=lambda item: (item.priority, item.evidence_id)))

    @staticmethod
    def _log_record_time(record: JsonObject, fallback: datetime) -> datetime:
        timestamp = record.get("timestamp_unix_nano")
        if isinstance(timestamp, int) and not isinstance(timestamp, bool):
            return datetime.fromtimestamp(timestamp / 1_000_000_000, timezone.utc)
        return fallback

    def _source_evidence(
        self,
        stacktrace: str,
        captured_at: datetime,
        findings: list[RedactionFinding],
        *,
        trace_id: str | None,
        span_id: str | None,
    ) -> list[EvidenceItem]:
        source_root = self.settings.source_root.resolve()
        include_root = (source_root / self.settings.source_include_root).resolve()
        items: list[EvidenceItem] = []
        seen: set[tuple[Path, int]] = set()
        for match in STACK_FRAME_PATTERN.finditer(stacktrace):
            raw_path = Path(match.group("path"))
            candidate = (raw_path if raw_path.is_absolute() else source_root / raw_path).resolve()
            line_number = int(match.group("line"))
            identity = (candidate, line_number)
            if (
                identity in seen
                or not candidate.is_file()
                or not candidate.is_relative_to(include_root)
            ):
                continue
            seen.add(identity)
            lines = candidate.read_text(encoding="utf-8").splitlines()
            start = max(1, line_number - self.settings.source_context_lines)
            end = min(len(lines), line_number + self.settings.source_context_lines)
            relative = candidate.relative_to(source_root).as_posix()
            content = self._redact_object(
                {
                    "path": relative,
                    "line": line_number,
                    "start_line": start,
                    "end_line": end,
                    "text": "\n".join(lines[start - 1 : end]),
                },
                captured_at,
                f"$/source/{relative.replace('/', '~1')}/{line_number}",
                findings,
            )
            items.append(
                EvidenceItem.create(
                    kind=EvidenceKind.SOURCE,
                    source=f"{relative}:{line_number}",
                    captured_at=captured_at,
                    content=content,
                    trace_id=trace_id,
                    span_id=span_id,
                    priority=15,
                )
            )
        return items

    def _redact_object(
        self,
        value: object,
        captured_at: datetime,
        root_location: str,
        findings: list[RedactionFinding],
    ) -> JsonObject:
        result = self.redactor.redact(
            value,
            completed_at=captured_at,
            root_location=root_location,
        )
        findings.extend(result.report.findings)
        return JSON_OBJECT_ADAPTER.validate_python(result.value)

    @staticmethod
    def _existing_findings(path: Path, trace_id: str) -> list[RedactionFinding]:
        if not path.is_file():
            return []
        findings: list[RedactionFinding] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            try:
                record = JSON_OBJECT_ADAPTER.validate_json(line)
                if "report" in record:
                    if record.get("trace_id") != trace_id:
                        continue
                    report = RedactionReport.model_validate(record["report"])
                else:
                    report = RedactionReport.model_validate(record)
            except ValidationError as exc:
                raise CaptureError(f"invalid redaction report: {path}:{line_number}") from exc
            findings.extend(report.findings)
        return findings

    @staticmethod
    def _redaction_report(
        captured_at: datetime,
        findings: list[RedactionFinding],
    ) -> RedactionReport:
        unique = {finding.finding_id: finding for finding in findings}
        ordered = tuple(unique[key] for key in sorted(unique))
        return RedactionReport(
            completed_at=captured_at,
            total_findings=len(ordered),
            findings=ordered,
        )

    @staticmethod
    def _jsonl(items: tuple[EvidenceItem, ...]) -> bytes:
        return b"".join(canonical_json(item.model_dump(mode="json")) + b"\n" for item in items)

    @staticmethod
    def _service_name(root_span: JsonObject) -> str:
        resource = root_span.get("resource")
        if isinstance(resource, dict):
            name = resource.get("service.name")
            if isinstance(name, str) and name:
                return name
        return "demo-order-api"
