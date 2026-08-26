"""Persisted isolated verification artifact."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from bugcapsule.capsule.schema import CapsuleModel, VerificationRun


class VerificationArtifact(CapsuleModel):
    """Approval binding, executor identity, and before/after results."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    executor: Literal["docker"] = "docker"
    image: str = Field(min_length=1, max_length=240)
    command_id: str = Field(min_length=1, max_length=120)
    started_at: AwareDatetime
    completed_at: AwareDatetime
    run: VerificationRun
