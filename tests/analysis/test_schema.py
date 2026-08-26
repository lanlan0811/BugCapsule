from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from bugcapsule.analysis.schema import (
    ModelAnalysisResponse,
    ModelRootCause,
    create_artifact,
)
from bugcapsule.capsule.schema import EvidenceReferenceError

EVIDENCE_ID = "EV-AAAAAAAAAAAA"


def response(*, evidence_id: str = EVIDENCE_ID) -> ModelAnalysisResponse:
    return ModelAnalysisResponse(
        root_causes=(
            ModelRootCause(
                rank=1,
                hypothesis="连接泄漏导致连接池耗尽",
                confidence=0.94,
                evidence_refs=(evidence_id,),
                unknowns=("生产环境连接池大小尚未确认",),
            ),
        )
    )


def test_model_response_requires_contiguous_ordered_ranks() -> None:
    with pytest.raises(ValidationError, match="ordered and contiguous"):
        ModelAnalysisResponse(
            root_causes=(
                ModelRootCause(
                    rank=2,
                    hypothesis="假设",
                    confidence=0.5,
                    evidence_refs=(EVIDENCE_ID,),
                    unknowns=(),
                ),
            )
        )


def test_model_response_rejects_duplicate_references_and_extra_fields() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        ModelRootCause(
            rank=1,
            hypothesis="假设",
            confidence=0.5,
            evidence_refs=(EVIDENCE_ID, EVIDENCE_ID),
            unknowns=(),
        )
    with pytest.raises(ValidationError, match="Extra inputs"):
        ModelAnalysisResponse.model_validate(
            {
                "root_causes": [
                    {
                        "rank": 1,
                        "hypothesis": "假设",
                        "confidence": 0.5,
                        "evidence_refs": [EVIDENCE_ID],
                        "unknowns": [],
                        "model_created_id": "RC-AAAAAAAAAAAA",
                    }
                ]
            }
        )


def test_artifact_rejects_evidence_outside_request_and_assigns_local_id() -> None:
    with pytest.raises(EvidenceReferenceError, match="EV-AAAAAAAAAAAA"):
        create_artifact(
            mode="live",
            provider="test",
            model="test-model",
            request_sha256="a" * 64,
            completed_at=datetime.now(timezone.utc),
            response=response(),
            available_evidence_ids=set(),
        )

    artifact = create_artifact(
        mode="live",
        provider="test",
        model="test-model",
        request_sha256="a" * 64,
        completed_at=datetime.now(timezone.utc),
        response=response(),
        available_evidence_ids={EVIDENCE_ID},
    )
    assert artifact.root_causes[0].root_cause_id.startswith("RC-")
    assert (
        "root_cause_id"
        not in ModelAnalysisResponse.model_json_schema()["$defs"]["ModelRootCause"]["properties"]
    )

    tampered = artifact.model_dump(mode="json")
    tampered["root_causes"][0]["root_cause_id"] = "RC-AAAAAAAAAAAA"
    with pytest.raises(ValidationError, match="canonical hypothesis"):
        artifact.model_validate(tampered)
