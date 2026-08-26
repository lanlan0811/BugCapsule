"""Strict schemas for model-proposed and persisted Patch data."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from bugcapsule.capsule.schema import CapsuleModel, EvidenceId, PatchCandidate, Sha256


class ModelPatchResponse(CapsuleModel):
    """A model proposal without trusted IDs or file metadata."""

    summary: str = Field(min_length=1, max_length=4000)
    unified_diff: str = Field(min_length=1, max_length=1024 * 1024)
    evidence_refs: tuple[EvidenceId, ...] = Field(min_length=1, max_length=20)
    safety_notes: tuple[str, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_text(self) -> ModelPatchResponse:
        if self.summary != self.summary.strip():
            raise ValueError("Patch summary must not have surrounding whitespace")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("Patch evidence_refs must not contain duplicates")
        if any(not item.strip() or item != item.strip() for item in self.safety_notes):
            raise ValueError("safety_notes must contain non-empty trimmed strings")
        return self


class PatchArtifact(CapsuleModel):
    """Validated Patch metadata persisted beside its canonical unified diff."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    mode: Literal["live", "replay"]
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=240)
    request_sha256: Sha256
    completed_at: AwareDatetime
    candidate: PatchCandidate
