"""Load annotations and materialize deterministic benchmark capsules."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from bugcapsule.benchmarking.schema import BenchmarkCase, BenchmarkDataset
from bugcapsule.capsule import (
    CapsuleArchive,
    CapsuleManifest,
    EnvironmentInfo,
    EvidenceItem,
    EvidenceKind,
    GitInfo,
    ServiceInfo,
    TraceInfo,
    canonical_json,
    create_manifest,
)
from bugcapsule.capsule.identifiers import sha256_hex

DATASET_PATH = Path(__file__).resolve().parent / "dataset.json"
BASE_TIME = datetime(2026, 8, 26, tzinfo=timezone.utc)


class BenchmarkDatasetError(RuntimeError):
    """Raised when benchmark input or output is unsafe or invalid."""


@dataclass(frozen=True)
class BenchmarkBuildResult:
    """Deterministic summary of one materialized dataset."""

    output_dir: Path
    annotation_sha256: str
    case_count: int
    fault_counts: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "output_dir": str(self.output_dir),
            "annotation_sha256": self.annotation_sha256,
            "case_count": self.case_count,
            "fault_counts": dict(sorted(self.fault_counts.items())),
        }


def load_benchmark_dataset(source: Path = DATASET_PATH) -> BenchmarkDataset:
    """Load and fully validate the packaged human annotation file."""
    try:
        return BenchmarkDataset.model_validate_json(source.read_bytes())
    except FileNotFoundError as exc:
        raise BenchmarkDatasetError(f"benchmark dataset not found: {source}") from exc
    except (OSError, ValidationError) as exc:
        raise BenchmarkDatasetError("benchmark dataset is unreadable or invalid") from exc


class BenchmarkDatasetBuilder:
    """Create portable capsules without relying on live services or wall-clock time."""

    def __init__(
        self,
        dataset: BenchmarkDataset | None = None,
        *,
        archive: CapsuleArchive | None = None,
    ) -> None:
        self.dataset = dataset or load_benchmark_dataset()
        self.archive = archive or CapsuleArchive()

    def build(self, output_dir: Path, *, overwrite: bool = False) -> BenchmarkBuildResult:
        destination = output_dir.resolve()
        capsules_dir = destination / "capsules"
        annotation_path = destination / "annotations.json"
        targets = [
            annotation_path,
            *(capsules_dir / f"{case.capsule_id}.bugcapsule" for case in self.dataset.cases),
        ]
        if not overwrite and any(target.exists() for target in targets):
            raise BenchmarkDatasetError("benchmark output already exists; use explicit overwrite")
        capsules_dir.mkdir(parents=True, exist_ok=True)

        annotation_bytes = canonical_json(self.dataset.model_dump(mode="json")) + b"\n"
        for sequence, case in enumerate(self.dataset.cases):
            manifest, payloads, _media_types = self._capsule(case, sequence)
            self.archive.export(
                capsules_dir / f"{case.capsule_id}.bugcapsule",
                manifest,
                payloads,
            )
        annotation_path.write_bytes(annotation_bytes)
        counts: Counter[str] = Counter(case.fault_type for case in self.dataset.cases)
        return BenchmarkBuildResult(
            output_dir=destination,
            annotation_sha256=sha256_hex(annotation_bytes),
            case_count=len(self.dataset.cases),
            fault_counts=dict(counts),
        )

    @staticmethod
    def _capsule(
        case: BenchmarkCase,
        sequence: int,
    ) -> tuple[CapsuleManifest, dict[str, bytes], dict[str, str]]:
        captured_at = BASE_TIME + timedelta(minutes=sequence)
        digest = sha256_hex(case.case_id.encode("utf-8"))
        trace_id = digest[:32]
        root_span_id = digest[32:48]
        child_span_id = digest[48:64]
        root = EvidenceItem.create(
            kind=EvidenceKind.TRACE,
            source="benchmark/traces.jsonl:1",
            captured_at=captured_at,
            content={
                "name": case.entrypoint,
                "status": "ERROR",
                "trace_id": trace_id,
                "span_id": root_span_id,
                "parent_span_id": None,
            },
            trace_id=trace_id,
            span_id=root_span_id,
            priority=0,
        )
        span = EvidenceItem.create(
            kind=EvidenceKind.SPAN,
            source="benchmark/traces.jsonl:2",
            captured_at=captured_at + timedelta(milliseconds=10),
            content={
                "name": case.span_name,
                "status": "ERROR",
                "trace_id": trace_id,
                "span_id": child_span_id,
                "parent_span_id": root_span_id,
            },
            trace_id=trace_id,
            span_id=child_span_id,
            priority=20,
        )
        log = EvidenceItem.create(
            kind=EvidenceKind.LOG,
            source="benchmark/logs.jsonl:1",
            captured_at=captured_at + timedelta(milliseconds=20),
            content={"level": "ERROR", "message": case.log_message, "fault": case.fault_type},
            trace_id=trace_id,
            span_id=root_span_id,
            priority=10,
        )
        stack = EvidenceItem.create(
            kind=EvidenceKind.STACKTRACE,
            source="benchmark/logs.exception:1",
            captured_at=captured_at + timedelta(milliseconds=20),
            content={"stacktrace": case.stacktrace},
            trace_id=trace_id,
            span_id=root_span_id,
            priority=5,
        )
        source = EvidenceItem.create(
            kind=EvidenceKind.SOURCE,
            source=f"{case.source_path}:{case.source_line}",
            captured_at=captured_at + timedelta(milliseconds=20),
            content={
                "path": case.source_path,
                "line": case.source_line,
                "start_line": max(1, case.source_line - 1),
                "end_line": case.source_line + len(case.source_text.splitlines()),
                "text": case.source_text,
            },
            trace_id=trace_id,
            span_id=root_span_id,
            priority=15,
        )
        git = EvidenceItem.create(
            kind=EvidenceKind.GIT,
            source="benchmark/git",
            captured_at=captured_at,
            content={"commit_sha": digest[:40], "branch": "benchmark", "dirty": False},
            priority=60,
        )
        environment = EvidenceItem.create(
            kind=EvidenceKind.ENVIRONMENT,
            source="benchmark/environment",
            captured_at=captured_at,
            content={"python_version": "3.12", "platform": "simulated"},
            priority=80,
        )
        evidence = (root, span, log, stack, source, git, environment)
        payloads = {
            "evidence/traces.jsonl": b"".join(
                canonical_json(item.model_dump(mode="json")) + b"\n"
                for item in evidence
                if item.kind in {EvidenceKind.TRACE, EvidenceKind.SPAN}
            ),
            "evidence/logs.jsonl": canonical_json(log.model_dump(mode="json")) + b"\n",
            "evidence/source-snippets.json": canonical_json(
                [item.model_dump(mode="json") for item in (stack, source, git, environment)]
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
            capsule_id=case.capsule_id,
            created_at=captured_at,
            service=ServiceInfo(name=case.service_name, entrypoint=case.entrypoint),
            trace=TraceInfo(trace_id=trace_id, root_span_id=root_span_id),
            git=GitInfo(commit_sha=digest[:40], branch="benchmark", dirty=False),
            environment=EnvironmentInfo(
                python_version="3.12",
                platform="simulated",
                dependency_lock_sha256=sha256_hex(b"benchmark-lock-v1"),
            ),
            payloads=payloads,
            media_types=media_types,
        )
        return manifest, payloads, media_types
