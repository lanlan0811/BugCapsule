"""Public types and validation helpers for the open capsule format."""

from bugcapsule.capsule.identifiers import canonical_json, stable_identifier
from bugcapsule.capsule.redaction import RedactionResult, RedactionRule, Redactor
from bugcapsule.capsule.schema import (
    CapsuleFile,
    CapsuleManifest,
    EnvironmentInfo,
    EvidenceItem,
    EvidenceKind,
    EvidenceReferenceError,
    GitInfo,
    PatchCandidate,
    RedactionFinding,
    RedactionReport,
    RootCauseCandidate,
    ServiceInfo,
    TestResult,
    TraceInfo,
    VerificationRun,
    validate_evidence_references,
)

__all__ = [
    "CapsuleFile",
    "CapsuleManifest",
    "EnvironmentInfo",
    "EvidenceItem",
    "EvidenceKind",
    "EvidenceReferenceError",
    "GitInfo",
    "PatchCandidate",
    "RedactionFinding",
    "RedactionReport",
    "RedactionResult",
    "RedactionRule",
    "Redactor",
    "RootCauseCandidate",
    "ServiceInfo",
    "TestResult",
    "TraceInfo",
    "VerificationRun",
    "canonical_json",
    "stable_identifier",
    "validate_evidence_references",
]
