"""Tests for deterministic evidence ranking and correlation."""

from pathlib import Path

import pytest

from bugcapsule.capsule import (
    CapsuleArchive,
    EvidenceCorrelator,
    EvidenceItem,
    EvidenceKind,
    EvidenceLoadError,
    canonical_json,
    create_manifest,
)
from tests.capsule.factories import make_stage_three_capsule


def replace_payload(source: Path, path: str, value: bytes) -> None:
    archive = CapsuleArchive()
    imported = archive.import_capsule(source)
    payloads = dict(imported.payloads)
    payloads[path] = value
    media_types = {item.path: item.media_type for item in imported.manifest.files}
    manifest = create_manifest(
        capsule_id=imported.manifest.capsule_id,
        created_at=imported.manifest.created_at,
        service=imported.manifest.service,
        trace=imported.manifest.trace,
        git=imported.manifest.git,
        environment=imported.manifest.environment,
        payloads=payloads,
        media_types=media_types,
    )
    archive.export(source, manifest, payloads)


def test_correlator_builds_ranked_evidence_and_causal_timeline(tmp_path: Path) -> None:
    source, _ = make_stage_three_capsule(tmp_path)

    chain = EvidenceCorrelator().build(CapsuleArchive().import_capsule(source))

    assert [item.kind for item in chain.ranked] == [
        EvidenceKind.TRACE,
        EvidenceKind.STACKTRACE,
        EvidenceKind.LOG,
        EvidenceKind.SOURCE,
        EvidenceKind.SPAN,
        EvidenceKind.GIT,
        EvidenceKind.ENVIRONMENT,
    ]
    assert [entry.evidence.kind for entry in chain.timeline] == [
        EvidenceKind.TRACE,
        EvidenceKind.SPAN,
        EvidenceKind.LOG,
        EvidenceKind.STACKTRACE,
        EvidenceKind.SOURCE,
        EvidenceKind.GIT,
        EvidenceKind.ENVIRONMENT,
    ]
    assert [entry.relation for entry in chain.timeline] == [
        "request_root",
        "child_of",
        "observed_on",
        "exception_from",
        "points_to",
        "version_context",
        "runtime_context",
    ]
    assert chain.candidate_sources[0].source.endswith("database.py:45")
    assert len(chain.evidence_ids) == 7


def test_timeline_is_independent_of_archive_record_order(tmp_path: Path) -> None:
    first, _ = make_stage_three_capsule(tmp_path / "first")
    second, _ = make_stage_three_capsule(
        tmp_path / "second",
        reverse_runtime=True,
    )
    correlator = EvidenceCorrelator()

    first_ids = [
        entry.evidence.evidence_id
        for entry in correlator.build(CapsuleArchive().import_capsule(first)).timeline
    ]
    second_ids = [
        entry.evidence.evidence_id
        for entry in correlator.build(CapsuleArchive().import_capsule(second)).timeline
    ]

    assert first_ids == second_ids


def test_correlator_rejects_invalid_duplicate_and_missing_root_evidence(tmp_path: Path) -> None:
    invalid, _ = make_stage_three_capsule(tmp_path / "invalid")
    replace_payload(invalid, "evidence/logs.jsonl", b"not-json\n")
    with pytest.raises(EvidenceLoadError, match="invalid evidence record"):
        EvidenceCorrelator().build(CapsuleArchive().import_capsule(invalid))

    duplicate, _ = make_stage_three_capsule(tmp_path / "duplicate")
    imported = CapsuleArchive().import_capsule(duplicate)
    traces = imported.read("evidence/traces.jsonl")
    first_line = traces.splitlines(keepends=True)[0]
    replace_payload(duplicate, "evidence/traces.jsonl", first_line + traces)
    with pytest.raises(EvidenceLoadError, match="duplicate evidence IDs"):
        EvidenceCorrelator().build(CapsuleArchive().import_capsule(duplicate))

    missing, _ = make_stage_three_capsule(tmp_path / "missing")
    imported = CapsuleArchive().import_capsule(missing)
    child_line = imported.read("evidence/traces.jsonl").splitlines(keepends=True)[1]
    replace_payload(missing, "evidence/traces.jsonl", child_line)
    with pytest.raises(EvidenceLoadError, match="manifest root span"):
        EvidenceCorrelator().build(CapsuleArchive().import_capsule(missing))


def test_correlator_rejects_cross_trace_and_unknown_span_links(tmp_path: Path) -> None:
    wrong_trace, _ = make_stage_three_capsule(tmp_path / "wrong-trace")
    imported = CapsuleArchive().import_capsule(wrong_trace)
    root_line, child_line = imported.read("evidence/traces.jsonl").splitlines()
    root = EvidenceItem.model_validate_json(root_line)
    replaced_root = EvidenceItem.create(
        kind=root.kind,
        source=root.source,
        captured_at=root.captured_at,
        content=root.content,
        trace_id="9" * 32,
        span_id=root.span_id,
        priority=root.priority,
    )
    replace_payload(
        wrong_trace,
        "evidence/traces.jsonl",
        canonical_json(replaced_root.model_dump(mode="json")) + b"\n" + child_line + b"\n",
    )
    with pytest.raises(EvidenceLoadError, match="different trace"):
        EvidenceCorrelator().build(CapsuleArchive().import_capsule(wrong_trace))

    unknown_span, _ = make_stage_three_capsule(tmp_path / "unknown-span")
    imported = CapsuleArchive().import_capsule(unknown_span)
    log = EvidenceItem.model_validate_json(imported.read("evidence/logs.jsonl"))
    replaced_log = EvidenceItem.create(
        kind=log.kind,
        source=log.source,
        captured_at=log.captured_at,
        content=log.content,
        trace_id=log.trace_id,
        span_id="4" * 16,
        priority=log.priority,
    )
    replace_payload(
        unknown_span,
        "evidence/logs.jsonl",
        canonical_json(replaced_log.model_dump(mode="json")) + b"\n",
    )
    with pytest.raises(EvidenceLoadError, match="unknown span"):
        EvidenceCorrelator().build(CapsuleArchive().import_capsule(unknown_span))
