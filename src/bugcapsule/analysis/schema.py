"""Strict exchange schemas for model-backed root-cause analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from bugcapsule.capsule.identifiers import stable_identifier
from bugcapsule.capsule.schema import (
    CapsuleModel,
    EvidenceId,
    RootCauseCandidate,
    Sha256,
    validate_evidence_references,
)


class ModelRootCause(CapsuleModel):
    """One root cause returned by a model before local ID assignment."""

    rank: int = Field(ge=1, le=3)
    hypothesis: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    evidence_refs: tuple[EvidenceId, ...] = Field(min_length=1, max_length=20)
    unknowns: tuple[str, ...] = Field(max_length=20)

    @model_validator(mode="after")
    def validate_content(self) -> ModelRootCause:
        if self.hypothesis != self.hypothesis.strip():
            raise ValueError("hypothesis must not have surrounding whitespace")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("evidence_refs must not contain duplicates")
        if any(not item.strip() or item != item.strip() for item in self.unknowns):
            raise ValueError("unknowns must contain non-empty trimmed strings")
        return self


class ModelAnalysisResponse(CapsuleModel):
    """Complete structured response accepted from the configured model."""

    root_causes: tuple[ModelRootCause, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_ranks(self) -> ModelAnalysisResponse:
        ranks = [candidate.rank for candidate in self.root_causes]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("root cause ranks must be ordered and contiguous from 1")
        return self


class AnalysisArtifact(CapsuleModel):
    """Validated analysis persisted inside a capsule."""

    schema_version: Literal["0.1.0"] = "0.1.0"
    mode: Literal["live", "replay"]
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=240)
    request_sha256: Sha256
    completed_at: AwareDatetime
    root_causes: tuple[RootCauseCandidate, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_candidate_order(self) -> AnalysisArtifact:
        ranks = [candidate.rank for candidate in self.root_causes]
        if ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("artifact root cause ranks must be ordered and contiguous from 1")
        identifiers = [candidate.root_cause_id for candidate in self.root_causes]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("artifact root causes must not contain duplicates")
        return self


def materialize_root_causes(
    response: ModelAnalysisResponse,
    available_evidence_ids: set[str],
) -> tuple[RootCauseCandidate, ...]:
    """Validate all citations and assign content-derived root-cause IDs locally."""
    candidates: list[RootCauseCandidate] = []
    seen_ids: set[str] = set()
    for item in response.root_causes:
        validate_evidence_references(item.evidence_refs, available_evidence_ids)
        root_cause_id = stable_identifier(
            "RC",
            {
                "hypothesis": item.hypothesis,
                "evidence_refs": list(item.evidence_refs),
            },
        )
        if root_cause_id in seen_ids:
            raise ValueError("model returned duplicate root-cause candidates")
        seen_ids.add(root_cause_id)
        candidates.append(
            RootCauseCandidate.create(
                rank=item.rank,
                hypothesis=item.hypothesis,
                confidence=item.confidence,
                evidence_refs=item.evidence_refs,
                unknowns=item.unknowns,
            )
        )
    return tuple(candidates)


def create_artifact(
    *,
    mode: Literal["live", "replay"],
    provider: str,
    model: str,
    request_sha256: str,
    completed_at: datetime,
    response: ModelAnalysisResponse,
    available_evidence_ids: set[str],
) -> AnalysisArtifact:
    """Build a capsule artifact only after local evidence validation succeeds."""
    return AnalysisArtifact(
        mode=mode,
        provider=provider,
        model=model,
        request_sha256=request_sha256,
        completed_at=completed_at,
        root_causes=materialize_root_causes(response, available_evidence_ids),
    )
