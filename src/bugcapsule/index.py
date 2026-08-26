"""Rebuildable SQLite metadata index backed by authoritative capsule archives."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from bugcapsule.capsule.archive import CapsuleArchive, CapsuleArchiveError, ImportedCapsule
from bugcapsule.capsule.evidence import EvidenceChain, EvidenceCorrelator, EvidenceLoadError
from bugcapsule.capsule.identifiers import sha256_hex
from bugcapsule.capsule.schema import (
    CapsuleManifest,
    EvidenceKind,
    RedactionReport,
)
from bugcapsule.config import Settings

INDEX_SCHEMA_VERSION = "2"


class CapsuleIndexError(RuntimeError):
    """Raised when the local index cannot safely satisfy an operation."""


class CapsuleIndexStaleError(CapsuleIndexError):
    """Raised when an indexed archive changed after indexing."""


@dataclass(frozen=True)
class CapsuleSummary:
    """Stable metadata row shared by CLI and Web presentation layers."""

    capsule_id: str
    created_at: datetime
    service_name: str
    service_version: str | None
    entrypoint: str
    trace_id: str
    root_span_id: str
    git_commit_sha: str
    git_branch: str
    git_dirty: bool
    redaction_status: str
    analysis_status: str
    verification_status: str
    fault_type: str
    fault_summary: str
    evidence_count: int
    candidate_source_count: int
    redaction_finding_count: int
    archive_sha256: str
    archive_size: int

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["created_at"] = self.created_at.isoformat()
        return value


@dataclass(frozen=True)
class CapsuleDetail:
    """Authoritative archive data plus its deterministic evidence chain."""

    summary: CapsuleSummary
    manifest: CapsuleManifest
    evidence: EvidenceChain
    redaction_report: RedactionReport
    archive_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.to_dict(),
            "manifest": self.manifest.model_dump(mode="json"),
            "redaction_report": self.redaction_report.model_dump(mode="json"),
            "ranked_evidence": [item.model_dump(mode="json") for item in self.evidence.ranked],
            "timeline": [
                {
                    "sequence": entry.sequence,
                    "evidence_id": entry.evidence.evidence_id,
                    "kind": entry.evidence.kind.value,
                    "relation": entry.relation,
                    "related_evidence_id": entry.related_evidence_id,
                    "captured_at": entry.evidence.captured_at.isoformat(),
                }
                for entry in self.evidence.timeline
            ],
        }


@dataclass(frozen=True)
class IndexRebuildIssue:
    """One archive excluded from a rebuild with a safe diagnostic."""

    archive_name: str
    reason: str


@dataclass(frozen=True)
class IndexRebuildResult:
    """Deterministic rebuild outcome."""

    indexed_count: int
    issues: tuple[IndexRebuildIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexed_count": self.indexed_count,
            "issues": [asdict(issue) for issue in self.issues],
        }


class CapsuleIndex:
    """Store only rebuildable metadata; archives remain the source of truth."""

    def __init__(
        self,
        database_path: Path,
        capsules_dir: Path,
        *,
        archive: CapsuleArchive | None = None,
        correlator: EvidenceCorrelator | None = None,
    ) -> None:
        self.database_path = database_path.resolve()
        self.capsules_dir = capsules_dir.resolve()
        self.archive = archive or CapsuleArchive()
        self.correlator = correlator or EvidenceCorrelator()

    @classmethod
    def from_settings(cls, settings: Settings) -> CapsuleIndex:
        data_dir = settings.data_dir.resolve()
        return cls(data_dir / "index.sqlite3", data_dir / "capsules")

    def rebuild(self) -> IndexRebuildResult:
        self.capsules_dir.mkdir(parents=True, exist_ok=True)
        records: list[dict[str, Any]] = []
        issues: list[IndexRebuildIssue] = []
        seen_ids: dict[str, str] = {}
        for source in sorted(self.capsules_dir.glob("*.bugcapsule"), key=lambda path: path.name):
            try:
                record = self._record_for(source)
            except (CapsuleArchiveError, EvidenceLoadError, OSError) as exc:
                issues.append(IndexRebuildIssue(source.name, str(exc)))
                continue
            capsule_id = str(record["capsule_id"])
            previous = seen_ids.get(capsule_id)
            if previous is not None:
                issues.append(
                    IndexRebuildIssue(
                        source.name,
                        f"duplicate capsule ID already indexed from {previous}",
                    )
                )
                continue
            seen_ids[capsule_id] = source.name
            records.append(record)

        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM capsules")
            connection.executemany(self._insert_sql(), records)
            connection.commit()
        return IndexRebuildResult(len(records), tuple(issues))

    def upsert(self, source: Path) -> CapsuleSummary:
        safe_source = self._resolve_archive_path(source)
        try:
            record = self._record_for(safe_source)
        except (CapsuleArchiveError, EvidenceLoadError, OSError) as exc:
            raise CapsuleIndexError(str(exc)) from exc
        with closing(self._connect()) as connection:
            connection.execute(
                self._insert_sql()
                + " ON CONFLICT(capsule_id) DO UPDATE SET "
                + ", ".join(
                    f"{column}=excluded.{column}" for column in record if column != "capsule_id"
                ),
                record,
            )
            connection.commit()
        return self._summary_from_record(record)

    def inspect(self, source: Path) -> CapsuleSummary:
        """Validate one in-directory archive without changing the SQLite index."""
        try:
            return self._summary_from_record(self._record_for(source))
        except (CapsuleArchiveError, EvidenceLoadError, OSError) as exc:
            raise CapsuleIndexError(str(exc)) from exc

    def list_capsules(
        self,
        *,
        query: str | None = None,
        analysis_status: str | None = None,
        verification_status: str | None = None,
        sort_by: str = "time",
        limit: int = 100,
    ) -> tuple[CapsuleSummary, ...]:
        if not 1 <= limit <= 500:
            raise CapsuleIndexError("limit must be between 1 and 500")
        if analysis_status not in {None, "not_run", "completed", "failed"}:
            raise CapsuleIndexError("unknown analysis status")
        if verification_status not in {None, "not_run", "running", "passed", "failed"}:
            raise CapsuleIndexError("unknown verification status")
        if sort_by not in {"time", "status"}:
            raise CapsuleIndexError("sort_by must be time or status")
        clauses: list[str] = []
        parameters: list[object] = []
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            clauses.append(
                "(capsule_id LIKE ? ESCAPE '\\' OR service_name LIKE ? ESCAPE '\\' "
                "OR entrypoint LIKE ? ESCAPE '\\' OR trace_id LIKE ? ESCAPE '\\')"
            )
            parameters.extend([pattern] * 4)
        if analysis_status:
            clauses.append("analysis_status = ?")
            parameters.append(analysis_status)
        if verification_status:
            clauses.append("verification_status = ?")
            parameters.append(verification_status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "created_at DESC, capsule_id ASC"
        if sort_by == "status":
            order = (
                "CASE verification_status WHEN 'failed' THEN 0 WHEN 'running' THEN 1 "
                "WHEN 'passed' THEN 2 ELSE 3 END, "
                "CASE analysis_status WHEN 'failed' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, "
                "created_at DESC, capsule_id ASC"
            )
        query_sql = "SELECT * FROM capsules" + where + f" ORDER BY {order} LIMIT ?"
        parameters.append(limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(query_sql, parameters).fetchall()
        return tuple(self._summary_from_record(dict(row)) for row in rows)

    def get_detail(self, capsule_id: str) -> CapsuleDetail | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM capsules WHERE capsule_id = ?",
                (capsule_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        source = self._resolve_archive_path(Path(str(record["archive_path"])))
        try:
            archive_bytes = source.read_bytes()
        except OSError as exc:
            raise CapsuleIndexStaleError("indexed capsule archive is no longer available") from exc
        if sha256_hex(archive_bytes) != record["archive_sha256"]:
            raise CapsuleIndexStaleError("indexed capsule archive changed; rebuild the index")
        try:
            imported = self.archive.import_capsule(source)
            evidence = self.correlator.build(imported)
            redaction_report = self._redaction_report(imported)
        except (CapsuleArchiveError, EvidenceLoadError) as exc:
            raise CapsuleIndexStaleError(f"indexed capsule is no longer valid: {exc}") from exc
        return CapsuleDetail(
            summary=self._summary_from_record(record),
            manifest=imported.manifest,
            evidence=evidence,
            redaction_report=redaction_report,
            archive_path=source,
        )

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        version = connection.execute(
            "SELECT value FROM index_metadata WHERE key = 'schema_version'"
        ).fetchone()
        if version is not None and version["value"] == "1":
            self._migrate_v1(connection)
            version = connection.execute(
                "SELECT value FROM index_metadata WHERE key = 'schema_version'"
            ).fetchone()
        if version is not None and version["value"] != INDEX_SCHEMA_VERSION:
            connection.close()
            raise CapsuleIndexError("unsupported SQLite index schema; remove or rebuild it")
        connection.execute(
            "INSERT OR IGNORE INTO index_metadata(key, value) VALUES ('schema_version', ?)",
            (INDEX_SCHEMA_VERSION,),
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS capsules ("
            "capsule_id TEXT PRIMARY KEY, archive_path TEXT NOT NULL, "
            "archive_sha256 TEXT NOT NULL, "
            "archive_size INTEGER NOT NULL CHECK(archive_size >= 0), created_at TEXT NOT NULL, "
            "service_name TEXT NOT NULL, service_version TEXT, entrypoint TEXT NOT NULL, "
            "trace_id TEXT NOT NULL, root_span_id TEXT NOT NULL, git_commit_sha TEXT NOT NULL, "
            "git_branch TEXT NOT NULL, git_dirty INTEGER NOT NULL CHECK(git_dirty IN (0, 1)), "
            "redaction_status TEXT NOT NULL, analysis_status TEXT NOT NULL, "
            "verification_status TEXT NOT NULL, "
            "fault_type TEXT NOT NULL, fault_summary TEXT NOT NULL, "
            "evidence_count INTEGER NOT NULL CHECK(evidence_count >= 0), "
            "candidate_source_count INTEGER NOT NULL CHECK(candidate_source_count >= 0), "
            "redaction_finding_count INTEGER NOT NULL CHECK(redaction_finding_count >= 0))"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS capsules_created_at_idx ON capsules(created_at DESC)"
        )
        connection.execute("CREATE INDEX IF NOT EXISTS capsules_trace_id_idx ON capsules(trace_id)")
        connection.commit()
        return connection

    def _record_for(self, source: Path) -> dict[str, Any]:
        safe_source = self._resolve_archive_path(source)
        archive_bytes = safe_source.read_bytes()
        imported = self.archive.import_capsule(safe_source)
        evidence = self.correlator.build(imported)
        redaction_report = self._redaction_report(imported)
        fault_type, fault_summary = self._fault_details(evidence)
        manifest = imported.manifest
        return {
            "capsule_id": manifest.capsule_id,
            "archive_path": str(safe_source),
            "archive_sha256": sha256_hex(archive_bytes),
            "archive_size": len(archive_bytes),
            "created_at": manifest.created_at.isoformat(),
            "service_name": manifest.service.name,
            "service_version": manifest.service.version,
            "entrypoint": manifest.service.entrypoint,
            "trace_id": manifest.trace.trace_id,
            "root_span_id": manifest.trace.root_span_id,
            "git_commit_sha": manifest.git.commit_sha,
            "git_branch": manifest.git.branch,
            "git_dirty": int(manifest.git.dirty),
            "redaction_status": manifest.redaction_status,
            "analysis_status": manifest.analysis_status,
            "verification_status": manifest.verification_status,
            "fault_type": fault_type,
            "fault_summary": fault_summary,
            "evidence_count": len(evidence.items),
            "candidate_source_count": len(evidence.candidate_sources),
            "redaction_finding_count": redaction_report.total_findings,
        }

    @staticmethod
    def _redaction_report(imported: ImportedCapsule) -> RedactionReport:
        try:
            payload = imported.read("redaction-report.json")
            return RedactionReport.model_validate_json(payload)
        except (CapsuleArchiveError, ValidationError) as exc:
            raise EvidenceLoadError("capsule contains an invalid redaction report") from exc

    @staticmethod
    def _fault_details(evidence: EvidenceChain) -> tuple[str, str]:
        error_logs = [
            item
            for item in evidence.ranked
            if item.kind is EvidenceKind.LOG and item.content.get("level") in {"ERROR", "CRITICAL"}
        ]
        if not error_logs:
            return "unknown", "未捕获错误日志"
        error_log = error_logs[0]
        fault = error_log.content.get("fault")
        fault_type = fault if isinstance(fault, str) and fault else "runtime_error"
        return fault_type, "关联错误日志可在证据链中核验"

    @staticmethod
    def _migrate_v1(connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"]) for row in connection.execute("PRAGMA table_info(capsules)").fetchall()
        }
        additions = {
            "fault_type": "TEXT NOT NULL DEFAULT 'unknown'",
            "fault_summary": "TEXT NOT NULL DEFAULT ''",
            "redaction_finding_count": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, declaration in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE capsules ADD COLUMN {name} {declaration}")
        connection.execute(
            "UPDATE index_metadata SET value = ? WHERE key = 'schema_version'",
            (INDEX_SCHEMA_VERSION,),
        )

    def _resolve_archive_path(self, source: Path) -> Path:
        resolved = source.resolve()
        if resolved.suffix != ".bugcapsule" or not resolved.is_relative_to(self.capsules_dir):
            raise CapsuleIndexError(
                "capsule archive must be inside the configured capsules directory"
            )
        return resolved

    @staticmethod
    def _insert_sql() -> str:
        columns = (
            "capsule_id",
            "archive_path",
            "archive_sha256",
            "archive_size",
            "created_at",
            "service_name",
            "service_version",
            "entrypoint",
            "trace_id",
            "root_span_id",
            "git_commit_sha",
            "git_branch",
            "git_dirty",
            "redaction_status",
            "analysis_status",
            "verification_status",
            "fault_type",
            "fault_summary",
            "evidence_count",
            "candidate_source_count",
            "redaction_finding_count",
        )
        names = ", ".join(columns)
        values = ", ".join(f":{column}" for column in columns)
        return f"INSERT INTO capsules ({names}) VALUES ({values})"

    @staticmethod
    def _summary_from_record(record: dict[str, Any]) -> CapsuleSummary:
        return CapsuleSummary(
            capsule_id=str(record["capsule_id"]),
            created_at=datetime.fromisoformat(str(record["created_at"])),
            service_name=str(record["service_name"]),
            service_version=(
                str(record["service_version"]) if record["service_version"] is not None else None
            ),
            entrypoint=str(record["entrypoint"]),
            trace_id=str(record["trace_id"]),
            root_span_id=str(record["root_span_id"]),
            git_commit_sha=str(record["git_commit_sha"]),
            git_branch=str(record["git_branch"]),
            git_dirty=bool(record["git_dirty"]),
            redaction_status=str(record["redaction_status"]),
            analysis_status=str(record["analysis_status"]),
            verification_status=str(record["verification_status"]),
            fault_type=str(record["fault_type"]),
            fault_summary=str(record["fault_summary"]),
            evidence_count=int(record["evidence_count"]),
            candidate_source_count=int(record["candidate_source_count"]),
            redaction_finding_count=int(record["redaction_finding_count"]),
            archive_sha256=str(record["archive_sha256"]),
            archive_size=int(record["archive_size"]),
        )
