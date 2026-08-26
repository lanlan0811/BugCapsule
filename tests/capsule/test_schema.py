"""Positive and negative tests for capsule schema version 0.1.0."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from bugcapsule.capsule import (
    CapsuleFile,
    CapsuleManifest,
    EnvironmentInfo,
    EvidenceItem,
    EvidenceKind,
    EvidenceReferenceError,
    GitInfo,
    ServiceInfo,
    TraceInfo,
    VerificationRun,
    validate_evidence_references,
)

SHA256 = "a" * 64
TRACE_ID = "1" * 32
SPAN_ID = "2" * 16
NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def make_evidence() -> EvidenceItem:
    return EvidenceItem.create(
        kind=EvidenceKind.LOG,
        source="logs.jsonl:1",
        captured_at=NOW,
        content={"level": "ERROR", "message": "pool timeout"},
        trace_id=TRACE_ID,
        span_id=SPAN_ID,
        priority=10,
    )


def test_evidence_id_is_stable_across_capture_time() -> None:
    first = make_evidence()
    second = EvidenceItem.create(
        kind=first.kind,
        source=first.source,
        captured_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
        content=first.content,
        trace_id=first.trace_id,
        span_id=first.span_id,
        priority=first.priority,
    )

    assert first.evidence_id == second.evidence_id


def test_evidence_rejects_tampered_stable_id() -> None:
    evidence = make_evidence()
    payload = evidence.model_dump()
    payload["evidence_id"] = "EV-000000000000"

    with pytest.raises(ValidationError, match="canonical evidence content"):
        EvidenceItem.model_validate(payload)


def test_manifest_requires_sorted_safe_unique_inventory() -> None:
    base = {
        "capsule_id": "cap_20260826_abcd1234",
        "created_at": NOW,
        "service": ServiceInfo(name="demo-order-api", entrypoint="POST /demo/leak"),
        "trace": TraceInfo(trace_id=TRACE_ID, root_span_id=SPAN_ID),
        "git": GitInfo(commit_sha="b" * 40, branch="master", dirty=False),
        "environment": EnvironmentInfo(
            python_version="3.12.13",
            platform="Windows-10",
            dependency_lock_sha256=SHA256,
        ),
    }
    files = (
        CapsuleFile(
            path="evidence/logs.jsonl",
            sha256=SHA256,
            size=10,
            media_type="application/x-ndjson",
        ),
        CapsuleFile(
            path="redaction-report.json",
            sha256=SHA256,
            size=20,
            media_type="application/json",
        ),
    )

    manifest = CapsuleManifest(**base, files=files)

    assert manifest.schema_version == "0.1.0"
    with pytest.raises(ValidationError, match="sorted by path"):
        CapsuleManifest(**base, files=tuple(reversed(files)))
    with pytest.raises(ValidationError, match="must not hash itself"):
        CapsuleManifest(
            **base,
            files=(
                CapsuleFile(
                    path="manifest.json",
                    sha256=SHA256,
                    size=1,
                    media_type="application/json",
                ),
            ),
        )


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "/etc/passwd",
        "C:/secret",
        "evidence\\logs.jsonl",
        "evidence//logs.jsonl",
        "evidence/./logs.jsonl",
    ],
)
def test_capsule_file_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError, match="archive path"):
        CapsuleFile(path=path, sha256=SHA256, size=1, media_type="application/json")


def test_unknown_evidence_references_are_rejected_in_sorted_order() -> None:
    with pytest.raises(EvidenceReferenceError, match="EV-AAAAAAAAAAAA, EV-BBBBBBBBBBBB"):
        validate_evidence_references(
            ["EV-BBBBBBBBBBBB", "EV-AAAAAAAAAAAA"],
            {make_evidence().evidence_id},
        )


def test_verification_approval_hash_must_match_patch() -> None:
    with pytest.raises(ValidationError, match="approved_sha256"):
        VerificationRun(
            verification_id="VR-1234567890AB",
            patch_id="PATCH-1234567890AB",
            patch_sha256="a" * 64,
            approved_sha256="b" * 64,
            explicitly_approved=True,
            status="running",
        )


def test_verification_requires_explicit_approval() -> None:
    with pytest.raises(ValidationError, match="explicit approval"):
        VerificationRun(
            verification_id="VR-1234567890AB",
            patch_id="PATCH-1234567890AB",
            patch_sha256="a" * 64,
            approved_sha256="a" * 64,
            explicitly_approved=False,
            status="running",
        )
