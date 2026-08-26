"""Tests for release supply-chain integrity validation."""

import hashlib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from scripts.release_integrity import ReleaseIntegrityError, main, validate_release_bundle


def _write_release_fixture(root: Path) -> dict[str, Path]:
    dist_dir = root / "dist"
    dist_dir.mkdir()
    wheel = dist_dir / "bugcapsule-0.1.0-py3-none-any.whl"
    source = dist_dir / "bugcapsule-0.1.0.tar.gz"
    core_metadata = b"Metadata-Version: 2.4\nName: bugcapsule\nVersion: 0.1.0\n\n"
    with zipfile.ZipFile(wheel, mode="w") as archive:
        archive.writestr("bugcapsule-0.1.0.dist-info/METADATA", core_metadata)
    with tarfile.open(source, mode="w:gz") as archive:
        member = tarfile.TarInfo("bugcapsule-0.1.0/PKG-INFO")
        member.size = len(core_metadata)
        archive.addfile(member, io.BytesIO(core_metadata))

    sbom = root / "bugcapsule.cdx.json"
    sbom.write_text(
        json.dumps(
            {
                "bomFormat": "CycloneDX",
                "specVersion": "1.6",
                "metadata": {"component": {"name": "BugCapsule", "version": "0.1.0"}},
                "components": [{"name": "fastapi", "version": "0.1"}],
            }
        ),
        encoding="utf-8",
    )
    audit = root / "dependency-audit.json"
    audit.write_text(
        json.dumps(
            {
                "dependencies": [
                    {"name": "fastapi", "version": "0.1", "vulns": []},
                    {"name": "pydantic", "version": "2.0", "vulns": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    requirements = root / "release-requirements.txt"
    requirements.write_text(
        "fastapi==0.1 \\\n+    --hash=sha256:0123456789abcdef\n",
        encoding="utf-8",
    )
    return {
        "dist_dir": dist_dir,
        "wheel": wheel,
        "source": source,
        "sbom": sbom,
        "audit": audit,
        "requirements": requirements,
        "checksums": root / "SHA256SUMS",
    }


def _validate(paths: dict[str, Path]) -> None:
    validate_release_bundle(
        dist_dir=paths["dist_dir"],
        sbom_path=paths["sbom"],
        audit_path=paths["audit"],
        requirements_path=paths["requirements"],
        checksum_path=paths["checksums"],
        expected_name="bugcapsule",
        expected_version="0.1.0",
    )


def test_validate_release_bundle_writes_sorted_checksums(tmp_path: Path) -> None:
    paths = _write_release_fixture(tmp_path)

    summary = validate_release_bundle(
        dist_dir=paths["dist_dir"],
        sbom_path=paths["sbom"],
        audit_path=paths["audit"],
        requirements_path=paths["requirements"],
        checksum_path=paths["checksums"],
        expected_name="bugcapsule",
        expected_version="0.1.0",
    )

    assert summary.sbom_components == 1
    assert summary.audited_dependencies == 2
    assert summary.known_vulnerabilities == 0
    lines = paths["checksums"].read_text(encoding="ascii").splitlines()
    assert [line.split("  ", 1)[1] for line in lines] == sorted(
        [
            paths["wheel"].name,
            paths["source"].name,
            paths["sbom"].name,
            paths["audit"].name,
            paths["requirements"].name,
        ]
    )
    wheel_line = next(line for line in lines if line.endswith(paths["wheel"].name))
    assert wheel_line.startswith(hashlib.sha256(paths["wheel"].read_bytes()).hexdigest())


def test_validate_release_bundle_rejects_vulnerabilities(tmp_path: Path) -> None:
    paths = _write_release_fixture(tmp_path)
    paths["audit"].write_text(
        json.dumps(
            {
                "dependencies": [
                    {
                        "name": "unsafe-package",
                        "version": "1.0",
                        "vulns": [{"id": "PYSEC-TEST"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ReleaseIntegrityError, match="1 known vulnerabilities"):
        _validate(paths)
    assert not paths["checksums"].exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("bomFormat", "SPDX", "CycloneDX JSON"),
        ("specVersion", "1.5", "CycloneDX JSON"),
    ],
)
def test_validate_release_bundle_rejects_wrong_sbom_contract(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    paths = _write_release_fixture(tmp_path)
    document = json.loads(paths["sbom"].read_text(encoding="utf-8"))
    document[field] = value
    paths["sbom"].write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ReleaseIntegrityError, match=message):
        _validate(paths)


def test_validate_release_bundle_rejects_unlocked_requirements(tmp_path: Path) -> None:
    paths = _write_release_fixture(tmp_path)
    paths["requirements"].write_text("fastapi==0.1\n", encoding="utf-8")

    with pytest.raises(ReleaseIntegrityError, match="hash-locked"):
        _validate(paths)


def test_validate_release_bundle_rejects_mismatched_package_metadata(tmp_path: Path) -> None:
    paths = _write_release_fixture(tmp_path)
    with zipfile.ZipFile(paths["wheel"], mode="w") as archive:
        archive.writestr(
            "bugcapsule-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.4\nName: bugcapsule\nVersion: 9.9.9\n\n",
        )

    with pytest.raises(ReleaseIntegrityError, match="wheel metadata project version"):
        _validate(paths)


def test_cli_derives_project_identity_from_installed_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _write_release_fixture(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_integrity",
            "--dist-dir",
            str(paths["dist_dir"]),
            "--sbom",
            str(paths["sbom"]),
            "--audit",
            str(paths["audit"]),
            "--requirements",
            str(paths["requirements"]),
            "--checksums",
            str(paths["checksums"]),
        ],
    )

    main()

    result = json.loads(capsys.readouterr().out)
    assert result["project_name"] == "bugcapsule"
    assert result["project_version"] == "0.1.0"
