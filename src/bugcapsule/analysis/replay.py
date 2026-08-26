"""Validated, exact-request replay records for offline analysis."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, ValidationError

from bugcapsule.analysis.schema import ModelAnalysisResponse
from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.capsule.schema import CapsuleModel, Sha256


class ReplayError(RuntimeError):
    """Raised when a replay record is unavailable or does not match exactly."""


class ReplayRecord(CapsuleModel):
    """Only validated structured model data is retained for replay."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    request_sha256: Sha256
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=240)
    completed_at: AwareDatetime
    response: ModelAnalysisResponse


class ReplayStore:
    """Persist records atomically under hash-derived file names."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()

    def load(self, request_sha256: str, *, provider: str, model: str) -> ReplayRecord:
        path = self.directory / f"{request_sha256}.json"
        try:
            record = ReplayRecord.model_validate_json(path.read_bytes())
        except FileNotFoundError as exc:
            raise ReplayError(f"replay record not found for request {request_sha256}") from exc
        except (OSError, ValidationError) as exc:
            raise ReplayError("replay record is unreadable or invalid") from exc
        if record.request_sha256 != request_sha256:
            raise ReplayError("replay record request hash does not match")
        if record.provider != provider or record.model != model:
            raise ReplayError("replay record provider or model does not match")
        return record

    def save(
        self,
        *,
        request_sha256: str,
        provider: str,
        model: str,
        completed_at: datetime,
        response: ModelAnalysisResponse,
    ) -> ReplayRecord:
        record = ReplayRecord(
            request_sha256=request_sha256,
            provider=provider,
            model=model,
            completed_at=completed_at,
            response=response,
        )
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{request_sha256}.json"
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=self.directory,
                prefix=f".{request_sha256}.",
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
