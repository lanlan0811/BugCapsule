"""Exact structured replay records for Patch proposals."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, ValidationError

from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.capsule.schema import CapsuleModel, Sha256
from bugcapsule.patching.schema import ModelPatchResponse


class PatchReplayError(RuntimeError):
    """Raised when an exact Patch replay cannot be loaded."""


class PatchReplayRecord(CapsuleModel):
    """Validated Patch proposal retained without the original prompt or provider payload."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    request_sha256: Sha256
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=240)
    completed_at: AwareDatetime
    response: ModelPatchResponse


class PatchReplayStore:
    """Use a Patch-specific suffix to avoid collisions with analysis records."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def load(self, request_sha256: str, *, provider: str, model: str) -> PatchReplayRecord:
        path = self.directory / f"{request_sha256}.patch.json"
        try:
            record = PatchReplayRecord.model_validate_json(path.read_bytes())
        except FileNotFoundError as exc:
            raise PatchReplayError(f"Patch replay not found for request {request_sha256}") from exc
        except (OSError, ValidationError) as exc:
            raise PatchReplayError("Patch replay is unreadable or invalid") from exc
        if record.request_sha256 != request_sha256:
            raise PatchReplayError("Patch replay request hash does not match")
        if record.provider != provider or record.model != model:
            raise PatchReplayError("Patch replay provider or model does not match")
        return record

    def save(
        self,
        *,
        request_sha256: str,
        provider: str,
        model: str,
        completed_at: datetime,
        response: ModelPatchResponse,
    ) -> PatchReplayRecord:
        record = PatchReplayRecord(
            request_sha256=request_sha256,
            provider=provider,
            model=model,
            completed_at=completed_at,
            response=response,
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{request_sha256}.patch.json"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.directory,
                prefix=f".{request_sha256}.patch.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(canonical_json(record.model_dump(mode="json")) + b"\n")
            temporary_path.replace(destination)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
        return record
