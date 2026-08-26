"""Tests for deterministic export, safe import, and file integrity checks."""

import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bugcapsule.capsule import (
    ArchiveLimits,
    CapsuleArchive,
    CapsuleArchiveError,
    CapsuleIntegrityError,
    CapsuleSecurityError,
    EnvironmentInfo,
    GitInfo,
    ServiceInfo,
    TraceInfo,
    create_manifest,
)

NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)
SHA256 = "a" * 64


def make_capsule(destination: Path) -> tuple[CapsuleArchive, Path, dict[str, bytes]]:
    payloads = {
        "evidence/logs.jsonl": b'{"level":"ERROR"}\n',
        "evidence/source-snippets.json": b"[]\n",
        "evidence/traces.jsonl": b'{"trace_id":"11111111111111111111111111111111"}\n',
        "redaction-report.json": b'{"total_findings":0}\n',
    }
    media_types = {
        "evidence/logs.jsonl": "application/x-ndjson",
        "evidence/source-snippets.json": "application/json",
        "evidence/traces.jsonl": "application/x-ndjson",
        "redaction-report.json": "application/json",
    }
    manifest = create_manifest(
        capsule_id="cap_20260826_abcd1234",
        created_at=NOW,
        service=ServiceInfo(name="demo-order-api", entrypoint="POST /demo/leak"),
        trace=TraceInfo(trace_id="1" * 32, root_span_id="2" * 16),
        git=GitInfo(commit_sha="b" * 40, branch="master", dirty=False),
        environment=EnvironmentInfo(
            python_version="3.12.13",
            platform="Windows-10",
            dependency_lock_sha256=SHA256,
        ),
        payloads=payloads,
        media_types=media_types,
    )
    archive = CapsuleArchive()
    return archive, archive.export(destination, manifest, payloads), payloads


def rewrite_member(source: Path, member: str, replacement: bytes) -> None:
    with zipfile.ZipFile(source, "r") as archive:
        entries = [(info, archive.read(info)) for info in archive.infolist()]
    with zipfile.ZipFile(source, "w") as archive:
        for info, value in entries:
            archive.writestr(info, replacement if info.filename == member else value)


def test_export_is_byte_deterministic_and_round_trips(tmp_path: Path) -> None:
    archive, first_path, payloads = make_capsule(tmp_path / "first.bugcapsule")
    imported = archive.import_capsule(first_path)
    second_path = archive.export(
        tmp_path / "second.bugcapsule",
        imported.manifest,
        imported.payloads,
    )

    assert first_path.read_bytes() == second_path.read_bytes()
    assert dict(imported.payloads) == payloads
    assert imported.read("evidence/logs.jsonl") == payloads["evidence/logs.jsonl"]


def test_import_rejects_payload_checksum_tampering(tmp_path: Path) -> None:
    archive, source, payloads = make_capsule(tmp_path / "tampered.bugcapsule")
    original = payloads["evidence/logs.jsonl"]
    rewrite_member(source, "evidence/logs.jsonl", b"x" * len(original))

    with pytest.raises(CapsuleIntegrityError, match="checksum mismatch"):
        archive.import_capsule(source)


@pytest.mark.parametrize("unsafe_path", ["../secret", "/absolute", "C:/secret"])
def test_import_rejects_unsafe_member_paths(tmp_path: Path, unsafe_path: str) -> None:
    source = tmp_path / "unsafe.bugcapsule"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(unsafe_path, b"secret")

    with pytest.raises(CapsuleSecurityError, match="unsafe capsule path"):
        CapsuleArchive().import_capsule(source)


def test_import_rejects_symbolic_link_member(tmp_path: Path) -> None:
    source = tmp_path / "link.bugcapsule"
    info = zipfile.ZipInfo("manifest.json")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(info, b"target")

    with pytest.raises(CapsuleSecurityError, match="symbolic links"):
        CapsuleArchive().import_capsule(source)


def test_import_rejects_file_over_configured_limit(tmp_path: Path) -> None:
    source = tmp_path / "large.bugcapsule"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("manifest.json", b"12345")

    limits = ArchiveLimits(max_single_file_size=4)
    with pytest.raises(CapsuleSecurityError, match="size limit"):
        CapsuleArchive(limits).import_capsule(source)


def test_import_rejects_total_size_and_compression_ratio_limits(tmp_path: Path) -> None:
    total_source = tmp_path / "total.bugcapsule"
    with zipfile.ZipFile(total_source, "w") as archive:
        archive.writestr("manifest.json", b"1234")
        archive.writestr("payload.json", b"5678")

    with pytest.raises(CapsuleSecurityError, match="total size"):
        CapsuleArchive(ArchiveLimits(max_total_uncompressed_size=7)).import_capsule(total_source)

    ratio_source = tmp_path / "ratio.bugcapsule"
    with zipfile.ZipFile(ratio_source, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", b"0" * (1024 * 1024 + 1))
    with pytest.raises(CapsuleSecurityError, match="compression ratio"):
        CapsuleArchive(
            ArchiveLimits(
                max_single_file_size=2 * 1024 * 1024,
                max_total_uncompressed_size=2 * 1024 * 1024,
                max_compression_ratio=10,
            )
        ).import_capsule(ratio_source)


def test_import_rejects_duplicate_and_unsupported_members(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.bugcapsule"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr("manifest.json", b"{}")
            archive.writestr("manifest.json", b"{}")
    with pytest.raises(CapsuleSecurityError, match="duplicate"):
        CapsuleArchive().import_capsule(duplicate)

    unsupported = tmp_path / "unsupported.bugcapsule"
    with zipfile.ZipFile(unsupported, "w", compression=zipfile.ZIP_BZIP2) as archive:
        archive.writestr("manifest.json", b"{}")
    with pytest.raises(CapsuleSecurityError, match="compression method"):
        CapsuleArchive().import_capsule(unsupported)


def test_import_rejects_missing_or_invalid_manifest(tmp_path: Path) -> None:
    missing = tmp_path / "missing-manifest.bugcapsule"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("payload.json", b"{}")
    with pytest.raises(CapsuleIntegrityError, match="missing manifest"):
        CapsuleArchive().import_capsule(missing)

    invalid = tmp_path / "invalid-manifest.bugcapsule"
    with zipfile.ZipFile(invalid, "w") as archive:
        archive.writestr("manifest.json", b"{}")
    with pytest.raises(CapsuleIntegrityError, match=r"schema 0\.1\.0"):
        CapsuleArchive().import_capsule(invalid)


def test_export_rejects_inventory_mismatch_and_wrong_suffix(tmp_path: Path) -> None:
    archive, source, _ = make_capsule(tmp_path / "valid.bugcapsule")
    imported = archive.import_capsule(source)

    with pytest.raises(CapsuleIntegrityError, match="payload paths"):
        archive.export(tmp_path / "missing.bugcapsule", imported.manifest, {})
    with pytest.raises(CapsuleArchiveError, match="suffix"):
        archive.export(tmp_path / "wrong.zip", imported.manifest, imported.payloads)
    with pytest.raises(CapsuleArchiveError, match="does not exist"):
        imported.read("missing.json")


def test_create_manifest_requires_matching_media_type_paths(tmp_path: Path) -> None:
    _, source, payloads = make_capsule(tmp_path / "valid.bugcapsule")
    assert source.is_file()

    with pytest.raises(CapsuleIntegrityError, match="media type paths"):
        create_manifest(
            capsule_id="cap_20260826_abcd1234",
            created_at=NOW,
            service=ServiceInfo(name="demo-order-api", entrypoint="POST /demo/leak"),
            trace=TraceInfo(trace_id="1" * 32, root_span_id="2" * 16),
            git=GitInfo(commit_sha="b" * 40, branch="master", dirty=False),
            environment=EnvironmentInfo(
                python_version="3.12.13",
                platform="Windows-10",
                dependency_lock_sha256=SHA256,
            ),
            payloads=payloads,
            media_types={},
        )


def test_import_rejects_invalid_zip_and_missing_file(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.bugcapsule"
    invalid.write_bytes(b"not a zip")

    with pytest.raises(CapsuleArchiveError, match="valid ZIP"):
        CapsuleArchive().import_capsule(invalid)
    with pytest.raises(CapsuleArchiveError, match="does not exist"):
        CapsuleArchive().import_capsule(tmp_path / "missing.bugcapsule")
