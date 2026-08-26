"""Pydantic schema for BugCapsule format version 0.1.0."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from bugcapsule.capsule.identifiers import stable_identifier

Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
TraceId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
SpanId = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{16}$")]
EvidenceId = Annotated[str, StringConstraints(pattern=r"^EV-[A-F0-9]{12}$")]


class CapsuleModel(BaseModel):
    """Strict immutable base model shared by all exchange types."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceKind(str, Enum):
    """Evidence categories understood by the 0.1 correlator."""

    TRACE = "trace"
    SPAN = "span"
    LOG = "log"
    STACKTRACE = "stacktrace"
    SOURCE = "source"
    GIT = "git"
    ENVIRONMENT = "environment"
    TEST = "test"


class ServiceInfo(CapsuleModel):
    """Captured service identity."""

    name: str = Field(min_length=1, max_length=120)
    version: str | None = Field(default=None, max_length=80)
    entrypoint: str = Field(min_length=1, max_length=240)


class TraceInfo(CapsuleModel):
    """Root trace identity for the captured failure."""

    trace_id: TraceId
    root_span_id: SpanId


class GitInfo(CapsuleModel):
    """Source revision captured with the failure."""

    commit_sha: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{40}$")]
    branch: str = Field(min_length=1, max_length=240)
    dirty: bool
    diff_sha256: Sha256 | None = None


class EnvironmentInfo(CapsuleModel):
    """Minimal reproducibility metadata."""

    python_version: str = Field(min_length=1, max_length=40)
    platform: str = Field(min_length=1, max_length=240)
    dependency_lock_sha256: Sha256
    simulated_data: Literal[True] = True


def validate_archive_path(path: str) -> str:
    """Reject absolute, ambiguous, Windows, and traversal archive paths."""
    if not path or "\\" in path:
        raise ValueError("archive path must be a non-empty POSIX path")
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or any(part in {"", ".", ".."} for part in candidate.parts):
        raise ValueError("archive path must be relative and must not traverse directories")
    if path != candidate.as_posix():
        raise ValueError("archive path must already be normalized")
    if ":" in candidate.parts[0]:
        raise ValueError("archive path must not contain a drive prefix")
    return candidate.as_posix()


class CapsuleFile(CapsuleModel):
    """Integrity record for one payload file, excluding manifest.json itself."""

    path: str
    sha256: Sha256
    size: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=120)

    _validate_path = field_validator("path")(validate_archive_path)


class CapsuleManifest(CapsuleModel):
    """Authoritative metadata and integrity inventory for a capsule archive."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    capsule_id: Annotated[
        str,
        StringConstraints(pattern=r"^cap_[a-z0-9][a-z0-9_-]{7,63}$"),
    ]
    created_at: AwareDatetime
    service: ServiceInfo
    trace: TraceInfo
    git: GitInfo
    environment: EnvironmentInfo
    redaction_status: Literal["completed"] = "completed"
    analysis_status: Literal["not_run", "completed", "failed"] = "not_run"
    verification_status: Literal["not_run", "running", "passed", "failed"] = "not_run"
    files: tuple[CapsuleFile, ...]

    @field_validator("files")
    @classmethod
    def validate_file_inventory(cls, files: tuple[CapsuleFile, ...]) -> tuple[CapsuleFile, ...]:
        paths = [item.path for item in files]
        if paths != sorted(paths):
            raise ValueError("manifest files must be sorted by path")
        if len(paths) != len(set(paths)):
            raise ValueError("manifest files must not contain duplicate paths")
        if "manifest.json" in paths:
            raise ValueError("manifest.json must not hash itself")
        return files


class EvidenceItem(CapsuleModel):
    """One immutable evidence record with a content-derived stable ID."""

    evidence_id: EvidenceId
    kind: EvidenceKind
    source: str = Field(min_length=1, max_length=500)
    captured_at: AwareDatetime
    content: dict[str, JsonValue]
    trace_id: TraceId | None = None
    span_id: SpanId | None = None
    priority: int = Field(default=100, ge=0, le=1000)

    @classmethod
    def create(
        cls,
        *,
        kind: EvidenceKind,
        source: str,
        captured_at: datetime,
        content: dict[str, JsonValue],
        trace_id: str | None = None,
        span_id: str | None = None,
        priority: int = 100,
    ) -> EvidenceItem:
        identity = cls.identity_payload(kind, source, content, trace_id, span_id)
        return cls(
            evidence_id=stable_identifier("EV", identity),
            kind=kind,
            source=source,
            captured_at=captured_at,
            content=content,
            trace_id=trace_id,
            span_id=span_id,
            priority=priority,
        )

    @staticmethod
    def identity_payload(
        kind: EvidenceKind,
        source: str,
        content: dict[str, JsonValue],
        trace_id: str | None,
        span_id: str | None,
    ) -> dict[str, Any]:
        return {
            "kind": kind.value,
            "source": source,
            "content": content,
            "trace_id": trace_id,
            "span_id": span_id,
        }

    @model_validator(mode="after")
    def verify_evidence_id(self) -> EvidenceItem:
        identity = self.identity_payload(
            self.kind,
            self.source,
            self.content,
            self.trace_id,
            self.span_id,
        )
        if self.evidence_id != stable_identifier("EV", identity):
            raise ValueError("evidence_id does not match canonical evidence content")
        return self


class RootCauseCandidate(CapsuleModel):
    """Evidence-backed root-cause hypothesis."""

    root_cause_id: Annotated[str, StringConstraints(pattern=r"^RC-[A-F0-9]{12}$")]
    rank: int = Field(ge=1, le=10)
    hypothesis: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    evidence_refs: tuple[EvidenceId, ...] = Field(min_length=1)
    unknowns: tuple[str, ...] = ()

    @classmethod
    def create(
        cls,
        *,
        rank: int,
        hypothesis: str,
        confidence: float,
        evidence_refs: tuple[str, ...],
        unknowns: tuple[str, ...] = (),
    ) -> RootCauseCandidate:
        """Assign an immutable content-derived ID to a validated hypothesis."""
        return cls(
            root_cause_id=stable_identifier(
                "RC",
                {"hypothesis": hypothesis, "evidence_refs": list(evidence_refs)},
            ),
            rank=rank,
            hypothesis=hypothesis,
            confidence=confidence,
            evidence_refs=evidence_refs,
            unknowns=unknowns,
        )

    @model_validator(mode="after")
    def verify_root_cause(self) -> RootCauseCandidate:
        expected = stable_identifier(
            "RC",
            {"hypothesis": self.hypothesis, "evidence_refs": list(self.evidence_refs)},
        )
        if self.root_cause_id != expected:
            raise ValueError("root_cause_id does not match canonical hypothesis content")
        if self.hypothesis != self.hypothesis.strip():
            raise ValueError("hypothesis must not have surrounding whitespace")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must not contain duplicates")
        if any(not item.strip() or item != item.strip() for item in self.unknowns):
            raise ValueError("unknowns must contain non-empty trimmed strings")
        return self


class PatchCandidate(CapsuleModel):
    """Proposed patch metadata; the unified diff remains a separate payload file."""

    patch_id: Annotated[str, StringConstraints(pattern=r"^PATCH-[A-F0-9]{12}$")]
    root_cause_id: Annotated[str, StringConstraints(pattern=r"^RC-[A-F0-9]{12}$")]
    summary: str = Field(min_length=1, max_length=4000)
    diff_path: str = "patches/candidate.diff"
    sha256: Sha256
    modified_files: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[EvidenceId, ...] = Field(min_length=1)
    safety_checks: tuple[str, ...]

    _validate_diff_path = field_validator("diff_path")(validate_archive_path)

    @classmethod
    def create(
        cls,
        *,
        root_cause_id: str,
        summary: str,
        diff_path: str,
        sha256: str,
        modified_files: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        safety_checks: tuple[str, ...],
    ) -> PatchCandidate:
        """Assign a content-derived Patch ID after deterministic safety checks."""
        identity = cls.identity_payload(root_cause_id, sha256, modified_files)
        return cls(
            patch_id=stable_identifier("PATCH", identity),
            root_cause_id=root_cause_id,
            summary=summary,
            diff_path=diff_path,
            sha256=sha256,
            modified_files=modified_files,
            evidence_refs=evidence_refs,
            safety_checks=safety_checks,
        )

    @staticmethod
    def identity_payload(
        root_cause_id: str,
        sha256: str,
        modified_files: tuple[str, ...],
    ) -> dict[str, Any]:
        return {
            "root_cause_id": root_cause_id,
            "sha256": sha256,
            "modified_files": list(modified_files),
        }

    @field_validator("modified_files")
    @classmethod
    def validate_modified_files(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(validate_archive_path(value) for value in values)
        if normalized != tuple(sorted(normalized)):
            raise ValueError("modified_files must be sorted")
        if len(normalized) != len(set(normalized)):
            raise ValueError("modified_files must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def verify_patch_candidate(self) -> PatchCandidate:
        expected = stable_identifier(
            "PATCH",
            self.identity_payload(self.root_cause_id, self.sha256, self.modified_files),
        )
        if self.patch_id != expected:
            raise ValueError("patch_id does not match canonical Patch content")
        if self.summary != self.summary.strip():
            raise ValueError("Patch summary must not have surrounding whitespace")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("Patch evidence_refs must not contain duplicates")
        if len(self.safety_checks) != len(set(self.safety_checks)):
            raise ValueError("Patch safety_checks must not contain duplicates")
        return self


class TestResult(CapsuleModel):
    """Immutable result of one preconfigured regression test command."""

    command_id: str = Field(min_length=1, max_length=120)
    exit_code: int
    duration_ms: int = Field(ge=0)
    timed_out: bool = False
    output_sha256: Sha256


class VerificationRun(CapsuleModel):
    """Patch approval binding and before/after verification result."""

    verification_id: Annotated[str, StringConstraints(pattern=r"^VR-[A-F0-9]{12}$")]
    patch_id: Annotated[str, StringConstraints(pattern=r"^PATCH-[A-F0-9]{12}$")]
    patch_sha256: Sha256
    approved_sha256: Sha256
    explicitly_approved: bool
    status: Literal["running", "passed", "failed"]
    before: TestResult | None = None
    after: TestResult | None = None

    @classmethod
    def create(
        cls,
        *,
        patch_id: str,
        patch_sha256: str,
        approved_sha256: str,
        explicitly_approved: bool,
        status: Literal["running", "passed", "failed"],
        before: TestResult | None = None,
        after: TestResult | None = None,
    ) -> VerificationRun:
        """Bind verification identity to the exact approved Patch bytes."""
        identity = {
            "patch_id": patch_id,
            "patch_sha256": patch_sha256,
            "approved_sha256": approved_sha256,
        }
        return cls(
            verification_id=stable_identifier("VR", identity),
            patch_id=patch_id,
            patch_sha256=patch_sha256,
            approved_sha256=approved_sha256,
            explicitly_approved=explicitly_approved,
            status=status,
            before=before,
            after=after,
        )

    @model_validator(mode="after")
    def validate_approval_binding(self) -> VerificationRun:
        if not self.explicitly_approved:
            raise ValueError("verification requires explicit approval")
        if self.patch_sha256 != self.approved_sha256:
            raise ValueError("approved_sha256 must match patch_sha256")
        expected = stable_identifier(
            "VR",
            {
                "patch_id": self.patch_id,
                "patch_sha256": self.patch_sha256,
                "approved_sha256": self.approved_sha256,
            },
        )
        if self.verification_id != expected:
            raise ValueError("verification_id does not match approved Patch content")
        if self.status in {"passed", "failed"} and (self.before is None or self.after is None):
            raise ValueError("completed verification requires before and after results")
        if self.status == "passed" and (
            self.before is None
            or self.after is None
            or self.before.exit_code == 0
            or self.before.timed_out
            or self.after.exit_code != 0
            or self.after.timed_out
        ):
            raise ValueError("passed verification requires before failure and after success")
        return self


class RedactionFinding(CapsuleModel):
    """Auditable record of one redaction rule match."""

    finding_id: Annotated[str, StringConstraints(pattern=r"^RF-[A-F0-9]{12}$")]
    rule_id: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=500)
    replacement: str = Field(min_length=1, max_length=120)
    match_count: int = Field(ge=1)


class RedactionReport(CapsuleModel):
    """Versioned audit report produced before capsule persistence or model input."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    rule_version: Literal["0.1.0"] = "0.1.0"
    completed_at: AwareDatetime
    total_findings: int = Field(ge=0)
    findings: tuple[RedactionFinding, ...]

    @model_validator(mode="after")
    def validate_finding_count(self) -> RedactionReport:
        if self.total_findings != len(self.findings):
            raise ValueError("total_findings must match findings length")
        return self


class EvidenceReferenceError(ValueError):
    """Raised when a model conclusion cites evidence outside the capsule."""


def validate_evidence_references(
    references: tuple[str, ...] | list[str],
    available_ids: set[str],
) -> None:
    """Reject unknown evidence IDs with deterministic error ordering."""
    unknown = sorted(set(references) - available_ids)
    if unknown:
        raise EvidenceReferenceError(f"unknown evidence references: {', '.join(unknown)}")
