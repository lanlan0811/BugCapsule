"""Validate and checksum release supply-chain artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import tempfile
import zipfile
from dataclasses import asdict, dataclass
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import bugcapsule
from bugcapsule import __version__


class ReleaseIntegrityError(ValueError):
    """Raised when a release artifact violates the bundle contract."""


MAX_METADATA_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ReleaseBundleSummary:
    """Machine-readable result of release bundle validation."""

    project_name: str
    project_version: str
    distribution_files: tuple[str, ...]
    sbom_components: int
    audited_dependencies: int
    known_vulnerabilities: int
    checksum_file: str


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ReleaseIntegrityError(f"{label} is not valid UTF-8 JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ReleaseIntegrityError(f"{label} root must be a JSON object")
    return value


def _validate_distributions(
    dist_dir: Path,
    *,
    expected_name: str,
    expected_version: str,
) -> tuple[Path, Path]:
    if not dist_dir.is_dir():
        raise ReleaseIntegrityError(f"distribution directory does not exist: {dist_dir}")
    wheels = sorted(path for path in dist_dir.glob("*.whl") if path.is_file())
    source_archives = sorted(path for path in dist_dir.glob("*.tar.gz") if path.is_file())
    if len(wheels) != 1 or len(source_archives) != 1:
        raise ReleaseIntegrityError(
            "release bundle requires exactly one wheel and one source archive"
        )

    wheel_prefix = f"{_canonical_name(expected_name).replace('-', '_')}-{expected_version}-"
    source_name = f"{_canonical_name(expected_name)}-{expected_version}.tar.gz"
    if not wheels[0].name.startswith(wheel_prefix):
        raise ReleaseIntegrityError(f"wheel name does not match {expected_name} {expected_version}")
    if source_archives[0].name != source_name:
        raise ReleaseIntegrityError(
            f"source archive name does not match {expected_name} {expected_version}"
        )
    _validate_wheel_metadata(
        wheels[0], expected_name=expected_name, expected_version=expected_version
    )
    _validate_source_metadata(
        source_archives[0], expected_name=expected_name, expected_version=expected_version
    )
    return wheels[0], source_archives[0]


def _validate_core_metadata(
    payload: bytes,
    *,
    label: str,
    expected_name: str,
    expected_version: str,
) -> None:
    metadata = BytesParser().parsebytes(payload, headersonly=True)
    name = metadata.get("Name")
    version = metadata.get("Version")
    if not isinstance(name, str) or _canonical_name(name) != _canonical_name(expected_name):
        raise ReleaseIntegrityError(f"{label} metadata project name does not match")
    if version != expected_version:
        raise ReleaseIntegrityError(f"{label} metadata project version does not match")


def _validate_wheel_metadata(
    path: Path,
    *,
    expected_name: str,
    expected_version: str,
) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            members = [
                item
                for item in archive.infolist()
                if not item.is_dir() and item.filename.endswith(".dist-info/METADATA")
            ]
            if len(members) != 1 or members[0].file_size > MAX_METADATA_BYTES:
                raise ReleaseIntegrityError(
                    "wheel must contain exactly one size-bounded dist-info/METADATA"
                )
            payload = archive.read(members[0])
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseIntegrityError(f"wheel is not a readable ZIP archive: {path}") from exc
    _validate_core_metadata(
        payload,
        label="wheel",
        expected_name=expected_name,
        expected_version=expected_version,
    )


def _validate_source_metadata(
    path: Path,
    *,
    expected_name: str,
    expected_version: str,
) -> None:
    try:
        with tarfile.open(path, mode="r:gz") as archive:
            members = [
                item
                for item in archive.getmembers()
                if item.isfile()
                and len(Path(item.name).parts) == 2
                and Path(item.name).name == "PKG-INFO"
            ]
            if len(members) != 1 or members[0].size > MAX_METADATA_BYTES:
                raise ReleaseIntegrityError(
                    "source archive must contain exactly one size-bounded top-level PKG-INFO"
                )
            stream = archive.extractfile(members[0])
            if stream is None:
                raise ReleaseIntegrityError("source archive PKG-INFO is not readable")
            payload = stream.read(MAX_METADATA_BYTES + 1)
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseIntegrityError(f"source archive is not a readable tar.gz: {path}") from exc
    _validate_core_metadata(
        payload,
        label="source archive",
        expected_name=expected_name,
        expected_version=expected_version,
    )


def _validate_sbom(
    path: Path,
    *,
    expected_name: str,
    expected_version: str,
) -> int:
    document = _read_json_object(path, label="SBOM")
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != "1.6":
        raise ReleaseIntegrityError("SBOM must be CycloneDX JSON specification 1.6")

    metadata = document.get("metadata")
    component = metadata.get("component") if isinstance(metadata, dict) else None
    if not isinstance(component, dict):
        raise ReleaseIntegrityError("SBOM metadata.component must be an object")
    component_name = component.get("name")
    if not isinstance(component_name, str) or _canonical_name(component_name) != _canonical_name(
        expected_name
    ):
        raise ReleaseIntegrityError("SBOM root component name does not match the project")
    if component.get("version") != expected_version:
        raise ReleaseIntegrityError("SBOM root component version does not match the project")

    components = document.get("components")
    if not isinstance(components, list) or not components:
        raise ReleaseIntegrityError("SBOM must contain at least one dependency component")
    if any(not isinstance(item, dict) or not item.get("name") for item in components):
        raise ReleaseIntegrityError("every SBOM component must be an object with a name")
    return len(components)


def _validate_audit(path: Path) -> tuple[int, int]:
    document = _read_json_object(path, label="dependency audit")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ReleaseIntegrityError("dependency audit must contain a non-empty dependencies list")

    vulnerability_count = 0
    for dependency in dependencies:
        if (
            not isinstance(dependency, dict)
            or not dependency.get("name")
            or not dependency.get("version")
        ):
            raise ReleaseIntegrityError("every audited dependency must include name and version")
        vulnerabilities = dependency.get("vulns")
        if not isinstance(vulnerabilities, list):
            raise ReleaseIntegrityError("every audited dependency must include a vulns list")
        vulnerability_count += len(vulnerabilities)
    if vulnerability_count:
        raise ReleaseIntegrityError(
            f"dependency audit reports {vulnerability_count} known vulnerabilities"
        )
    return len(dependencies), vulnerability_count


def _validate_requirements(path: Path) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ReleaseIntegrityError(f"requirements snapshot is not readable UTF-8: {path}") from exc
    if not content.strip() or "--hash=sha256:" not in content:
        raise ReleaseIntegrityError("requirements snapshot must be non-empty and hash-locked")
    if re.search(r"(?m)^\s*(?:-e|--editable)\s", content):
        raise ReleaseIntegrityError("requirements snapshot must not contain editable dependencies")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_checksum_manifest(paths: tuple[Path, ...], output_path: Path) -> None:
    names = [path.name for path in paths]
    if len(names) != len(set(names)):
        raise ReleaseIntegrityError("release artifact basenames must be unique")
    if output_path.name in set(names):
        raise ReleaseIntegrityError("checksum manifest cannot checksum itself")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{_sha256(path)}  {path.name}" for path in sorted(paths, key=lambda item: item.name)]
    payload = ("\n".join(lines) + "\n").encode("ascii")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            stream.write(payload)
            temporary_name = stream.name
        Path(temporary_name).replace(output_path)
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def validate_release_bundle(
    *,
    dist_dir: Path,
    sbom_path: Path,
    audit_path: Path,
    requirements_path: Path,
    checksum_path: Path,
    expected_name: str,
    expected_version: str,
) -> ReleaseBundleSummary:
    """Validate release evidence and atomically write its SHA-256 manifest."""

    wheel, source_archive = _validate_distributions(
        dist_dir,
        expected_name=expected_name,
        expected_version=expected_version,
    )
    component_count = _validate_sbom(
        sbom_path,
        expected_name=expected_name,
        expected_version=expected_version,
    )
    dependency_count, vulnerability_count = _validate_audit(audit_path)
    _validate_requirements(requirements_path)

    artifacts = (wheel, source_archive, sbom_path, audit_path, requirements_path)
    _write_checksum_manifest(artifacts, checksum_path)
    return ReleaseBundleSummary(
        project_name=expected_name,
        project_version=expected_version,
        distribution_files=tuple(path.name for path in (wheel, source_archive)),
        sbom_components=component_count,
        audited_dependencies=dependency_count,
        known_vulnerabilities=vulnerability_count,
        checksum_file=checksum_path.name,
    )


def main() -> None:
    """Validate release artifacts from CI and emit a deterministic JSON summary."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--sbom", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--requirements", type=Path, required=True)
    parser.add_argument("--checksums", type=Path, required=True)
    parser.add_argument("--project-name", default=bugcapsule.__name__.partition(".")[0])
    parser.add_argument("--project-version", default=__version__)
    arguments = parser.parse_args()
    try:
        summary = validate_release_bundle(
            dist_dir=arguments.dist_dir,
            sbom_path=arguments.sbom,
            audit_path=arguments.audit,
            requirements_path=arguments.requirements,
            checksum_path=arguments.checksums,
            expected_name=arguments.project_name,
            expected_version=arguments.project_version,
        )
    except ReleaseIntegrityError as exc:
        parser.error(str(exc))
    print(json.dumps(asdict(summary), ensure_ascii=False, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":  # pragma: no cover - exercised through the public functions
    main()
