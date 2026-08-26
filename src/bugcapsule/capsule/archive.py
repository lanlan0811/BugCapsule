"""Deterministic capsule ZIP export, safe import, and integrity verification."""

from __future__ import annotations

import stat
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from pydantic import ValidationError

from bugcapsule.capsule.identifiers import canonical_json, sha256_hex
from bugcapsule.capsule.schema import (
    CapsuleFile,
    CapsuleManifest,
    EnvironmentInfo,
    GitInfo,
    ServiceInfo,
    TraceInfo,
    validate_archive_path,
)

MANIFEST_PATH = "manifest.json"
DETERMINISTIC_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
ALLOWED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})


class CapsuleArchiveError(ValueError):
    """Base error for invalid or unsafe capsule archives."""


class CapsuleSecurityError(CapsuleArchiveError):
    """Raised when an archive violates path, type, encryption, or size limits."""


class CapsuleIntegrityError(CapsuleArchiveError):
    """Raised when the manifest inventory does not match archive bytes."""


@dataclass(frozen=True)
class ArchiveLimits:
    """Import limits that bound memory and ZIP bomb exposure."""

    max_files: int = 64
    max_single_file_size: int = 10 * 1024 * 1024
    max_total_uncompressed_size: int = 50 * 1024 * 1024
    max_compression_ratio: float = 100.0


@dataclass(frozen=True)
class ImportedCapsule:
    """Validated capsule payload held after a safe import."""

    manifest: CapsuleManifest
    payloads: Mapping[str, bytes]

    def read(self, path: str) -> bytes:
        try:
            return self.payloads[path]
        except KeyError as exc:
            raise CapsuleArchiveError(f"capsule payload does not exist: {path}") from exc


def create_manifest(
    *,
    capsule_id: str,
    created_at: datetime,
    service: ServiceInfo,
    trace: TraceInfo,
    git: GitInfo,
    environment: EnvironmentInfo,
    payloads: Mapping[str, bytes],
    media_types: Mapping[str, str],
    analysis_status: str = "not_run",
    verification_status: str = "not_run",
) -> CapsuleManifest:
    """Create a sorted integrity inventory from already-redacted payload bytes."""
    if set(payloads) != set(media_types):
        raise CapsuleIntegrityError("payload and media type paths must match exactly")
    files = tuple(
        CapsuleFile(
            path=path,
            sha256=sha256_hex(payloads[path]),
            size=len(payloads[path]),
            media_type=media_types[path],
        )
        for path in sorted(payloads)
    )
    return CapsuleManifest(
        capsule_id=capsule_id,
        created_at=created_at,
        service=service,
        trace=trace,
        git=git,
        environment=environment,
        analysis_status=analysis_status,
        verification_status=verification_status,
        files=files,
    )


class CapsuleArchive:
    """Read and write capsule archives using a deterministic, auditable layout."""

    def __init__(self, limits: ArchiveLimits | None = None) -> None:
        self.limits = limits or ArchiveLimits()

    def export(
        self,
        destination: Path,
        manifest: CapsuleManifest,
        payloads: Mapping[str, bytes],
    ) -> Path:
        """Atomically export a byte-stable ZIP_STORED capsule."""
        if destination.suffix != ".bugcapsule":
            raise CapsuleArchiveError("capsule destination must use .bugcapsule suffix")
        self._verify_payloads(manifest, payloads)
        destination.parent.mkdir(parents=True, exist_ok=True)
        manifest_bytes = canonical_json(manifest.model_dump(mode="json")) + b"\n"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
            with zipfile.ZipFile(
                temporary_path,
                mode="w",
                compression=zipfile.ZIP_STORED,
            ) as archive:
                self._write_member(archive, MANIFEST_PATH, manifest_bytes)
                for path in sorted(payloads):
                    self._write_member(archive, path, payloads[path])
            temporary_path.replace(destination)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return destination

    def import_capsule(self, source: Path) -> ImportedCapsule:
        """Safely load an archive and verify its manifest inventory before use."""
        if not source.is_file():
            raise CapsuleArchiveError(f"capsule file does not exist: {source}")
        try:
            with zipfile.ZipFile(source, mode="r") as archive:
                infos = archive.infolist()
                self._validate_members(infos)
                if MANIFEST_PATH not in {info.filename for info in infos}:
                    raise CapsuleIntegrityError("capsule is missing manifest.json")
                manifest_bytes = archive.read(MANIFEST_PATH)
                try:
                    manifest = CapsuleManifest.model_validate_json(manifest_bytes)
                except ValidationError as exc:
                    raise CapsuleIntegrityError(
                        "manifest.json does not match schema 0.1.0"
                    ) from exc
                payloads = {
                    info.filename: archive.read(info)
                    for info in infos
                    if info.filename != MANIFEST_PATH
                }
        except zipfile.BadZipFile as exc:
            raise CapsuleArchiveError("capsule is not a valid ZIP archive") from exc
        self._verify_payloads(manifest, payloads)
        return ImportedCapsule(manifest=manifest, payloads=MappingProxyType(payloads))

    def _validate_members(self, infos: list[zipfile.ZipInfo]) -> None:
        if len(infos) > self.limits.max_files:
            raise CapsuleSecurityError("capsule contains too many files")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise CapsuleSecurityError("capsule contains duplicate file names")

        total_size = 0
        for info in infos:
            try:
                validate_archive_path(info.filename)
            except ValueError as exc:
                raise CapsuleSecurityError(f"unsafe capsule path: {info.filename}") from exc
            if info.is_dir():
                raise CapsuleSecurityError("directory entries are not permitted")
            if info.flag_bits & 0x1:
                raise CapsuleSecurityError("encrypted capsule members are not permitted")
            if info.compress_type not in ALLOWED_COMPRESSION:
                raise CapsuleSecurityError("unsupported capsule compression method")
            unix_mode = info.external_attr >> 16
            if unix_mode and stat.S_ISLNK(unix_mode):
                raise CapsuleSecurityError("symbolic links are not permitted")
            if info.file_size > self.limits.max_single_file_size:
                raise CapsuleSecurityError("capsule member exceeds size limit")
            total_size += info.file_size
            if total_size > self.limits.max_total_uncompressed_size:
                raise CapsuleSecurityError("capsule exceeds total size limit")
            if info.file_size > 1024 * 1024:
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > self.limits.max_compression_ratio:
                    raise CapsuleSecurityError("capsule compression ratio exceeds limit")

    @staticmethod
    def _verify_payloads(manifest: CapsuleManifest, payloads: Mapping[str, bytes]) -> None:
        inventory = {item.path: item for item in manifest.files}
        if set(inventory) != set(payloads):
            raise CapsuleIntegrityError("manifest inventory does not match capsule payload paths")
        for path, item in inventory.items():
            payload = payloads[path]
            if len(payload) != item.size:
                raise CapsuleIntegrityError(f"capsule payload size mismatch: {path}")
            if sha256_hex(payload) != item.sha256:
                raise CapsuleIntegrityError(f"capsule payload checksum mismatch: {path}")

    @staticmethod
    def _write_member(archive: zipfile.ZipFile, path: str, value: bytes) -> None:
        info = zipfile.ZipInfo(path, date_time=DETERMINISTIC_ZIP_TIME)
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        archive.writestr(info, value)
