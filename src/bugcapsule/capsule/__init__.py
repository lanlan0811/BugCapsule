"""Public types and validation helpers for the open capsule format."""

from bugcapsule.capsule.identifiers import canonical_json, stable_identifier
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
    "RootCauseCandidate",
    "ServiceInfo",
    "TestResult",
    "TraceInfo",
    "VerificationRun",
    "canonical_json",
    "stable_identifier",
    "validate_evidence_references",
]
