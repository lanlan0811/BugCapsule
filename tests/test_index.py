"""Tests for the rebuildable capsule metadata index."""

import sqlite3
from pathlib import Path

import pytest

from bugcapsule.index import CapsuleIndex, CapsuleIndexError, CapsuleIndexStaleError
from tests.capsule.factories import make_stage_three_capsule


def make_index(tmp_path: Path) -> CapsuleIndex:
    return CapsuleIndex(tmp_path / "data" / "index.sqlite3", tmp_path / "data" / "capsules")


def test_rebuild_indexes_valid_capsules_and_reports_invalid_archives(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    source, _ = make_stage_three_capsule(index.capsules_dir, service_name="percent%api")
    (index.capsules_dir / "broken.bugcapsule").write_bytes(b"not a capsule")

    result = index.rebuild()
    summaries = index.list_capsules(query="%")
    detail = index.get_detail("cap_stage3_0001")

    assert source.is_file()
    assert result.indexed_count == 1
    assert result.issues[0].archive_name == "broken.bugcapsule"
    assert [item.capsule_id for item in summaries] == ["cap_stage3_0001"]
    assert detail is not None
    assert detail.summary.evidence_count == 7
    assert detail.summary.candidate_source_count == 1
    assert detail.summary.redaction_finding_count == 0
    assert detail.summary.fault_type == "database_pool_exhausted"
    assert len(detail.summary.archive_sha256) == 64
    assert detail.manifest.trace.trace_id == detail.summary.trace_id
    assert detail.to_dict()["timeline"][0]["relation"] == "request_root"


def test_index_database_contains_metadata_not_evidence_content(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    make_stage_three_capsule(index.capsules_dir)
    index.rebuild()

    database_files = [index.database_path, Path(f"{index.database_path}-wal")]
    database_bytes = b"".join(path.read_bytes() for path in database_files if path.is_file())

    assert b"demo-order-api" in database_bytes
    assert b"database pool exhausted" not in database_bytes
    assert b"session.execute(statement)" not in database_bytes


def test_rebuild_removes_deleted_capsules_and_reports_duplicate_ids(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    first, _ = make_stage_three_capsule(index.capsules_dir, filename="a.bugcapsule")
    make_stage_three_capsule(index.capsules_dir, filename="b.bugcapsule")

    duplicate_result = index.rebuild()

    assert duplicate_result.indexed_count == 1
    assert "duplicate capsule ID" in duplicate_result.issues[0].reason
    first.unlink()
    (index.capsules_dir / "b.bugcapsule").unlink()
    empty_result = index.rebuild()
    assert empty_result.indexed_count == 0
    assert index.list_capsules() == ()


def test_detail_detects_changed_or_missing_archive(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    source, _ = make_stage_three_capsule(index.capsules_dir)
    index.rebuild()
    source.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises(CapsuleIndexStaleError, match="changed"):
        index.get_detail("cap_stage3_0001")

    index.rebuild()
    source.unlink()
    with pytest.raises(CapsuleIndexStaleError, match="no longer available"):
        index.get_detail("cap_stage3_0001")


def test_upsert_rejects_archive_outside_configured_directory(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    source, _ = make_stage_three_capsule(tmp_path / "outside")

    with pytest.raises(CapsuleIndexError, match="configured capsules directory"):
        index.upsert(source)


def test_index_rejects_unknown_database_schema(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    index.database_path.parent.mkdir(parents=True)
    with sqlite3.connect(index.database_path) as connection:
        connection.execute(
            "CREATE TABLE index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO index_metadata(key, value) VALUES ('schema_version', 'future')"
        )

    with pytest.raises(CapsuleIndexError, match="unsupported SQLite index schema"):
        index.list_capsules()


def test_index_migrates_rebuildable_v1_metadata_schema(tmp_path: Path) -> None:
    index = make_index(tmp_path)
    index.database_path.parent.mkdir(parents=True)
    with sqlite3.connect(index.database_path) as connection:
        connection.execute(
            "CREATE TABLE index_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO index_metadata(key, value) VALUES ('schema_version', '1')")
        connection.execute(
            "CREATE TABLE capsules (capsule_id TEXT PRIMARY KEY, created_at TEXT, trace_id TEXT)"
        )

    assert index.list_capsules() == ()
    with sqlite3.connect(index.database_path) as connection:
        version = connection.execute(
            "SELECT value FROM index_metadata WHERE key = 'schema_version'"
        ).fetchone()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(capsules)")}

    assert version == ("2",)
    assert {"fault_type", "fault_summary", "redaction_finding_count"} <= columns


def test_index_rejects_unknown_filters_and_sort(tmp_path: Path) -> None:
    index = make_index(tmp_path)

    with pytest.raises(CapsuleIndexError, match="unknown analysis status"):
        index.list_capsules(analysis_status="invalid")
    with pytest.raises(CapsuleIndexError, match="unknown verification status"):
        index.list_capsules(verification_status="invalid")
    with pytest.raises(CapsuleIndexError, match="sort_by"):
        index.list_capsules(sort_by="invalid")
