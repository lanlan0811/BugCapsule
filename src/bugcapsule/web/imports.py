"""Bounded, validated capsule upload persistence."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from bugcapsule.capsule.identifiers import sha256_hex
from bugcapsule.index import CapsuleIndex, CapsuleIndexError, CapsuleSummary

UPLOAD_CHUNK_SIZE = 64 * 1024


class CapsuleImportError(ValueError):
    """Raised when an uploaded archive cannot be safely persisted."""


@dataclass(frozen=True)
class CapsuleImportResult:
    """Successful import result including duplicate disposition."""

    summary: CapsuleSummary
    created: bool


class CapsuleUploadService:
    """Write a bounded upload, validate it, then atomically place it by capsule ID."""

    def __init__(self, index: CapsuleIndex, max_import_bytes: int) -> None:
        self.index = index
        self.max_import_bytes = max_import_bytes

    async def import_upload(self, upload: UploadFile) -> CapsuleImportResult:
        self.index.capsules_dir.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.index.capsules_dir,
                prefix=".upload-",
                suffix=".bugcapsule",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                total = 0
                while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
                    total += len(chunk)
                    if total > self.max_import_bytes:
                        raise CapsuleImportError("胶囊文件超过配置的导入大小上限")
                    temporary.write(chunk)
                temporary.flush()
                os.fsync(temporary.fileno())
            if total == 0:
                raise CapsuleImportError("胶囊文件为空")

            try:
                inspected = self.index.inspect(temporary_path)
            except CapsuleIndexError as exc:
                raise CapsuleImportError(f"胶囊校验失败：{exc}") from exc
            destination = self.index.capsules_dir / f"{inspected.capsule_id}.bugcapsule"
            if destination.exists():
                if sha256_hex(destination.read_bytes()) != inspected.archive_sha256:
                    raise CapsuleImportError("同一 capsule_id 已存在不同内容，未覆盖原文件")
                summary = self.index.upsert(destination)
                return CapsuleImportResult(summary=summary, created=False)

            temporary_path.replace(destination)
            temporary_path = None
            summary = self.index.upsert(destination)
            return CapsuleImportResult(summary=summary, created=True)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
