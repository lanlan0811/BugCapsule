from pathlib import Path

import pytest

from bugcapsule.analysis.client import InvalidModelResponseError
from bugcapsule.analysis.request import AnalysisRequest
from bugcapsule.analysis.schema import ModelAnalysisResponse, ModelRootCause
from bugcapsule.analysis.service import ANALYSIS_PATH, AnalysisError, AnalysisService
from bugcapsule.capsule import CapsuleArchive
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleIndex
from tests.capsule.factories import make_stage_three_capsule


class FakeClient:
    def __init__(self, *, invalid_attempts: int = 0) -> None:
        self.requests: list[AnalysisRequest] = []
        self.invalid_attempts = invalid_attempts

    def analyze(self, request: AnalysisRequest) -> ModelAnalysisResponse:
        self.requests.append(request)
        evidence_id = "EV-AAAAAAAAAAAA"
        if len(self.requests) > self.invalid_attempts:
            evidence_id = sorted(request.included_evidence_ids)[0]
        return ModelAnalysisResponse(
            root_causes=(
                ModelRootCause(
                    rank=1,
                    hypothesis="连接未归还导致连接池耗尽",
                    confidence=0.97,
                    evidence_refs=(evidence_id,),
                    unknowns=("需要核对生产环境池配置",),
                ),
            )
        )


def setup_capsule(tmp_path: Path) -> tuple[Settings, CapsuleIndex, Path]:
    settings = Settings(
        data_dir=tmp_path,
        replay_dir=tmp_path / "replay",
        model_name="gpt-test",
        model_api_key="test-key",
        model_provider="test-provider",
    )
    index = CapsuleIndex.from_settings(settings)
    index.capsules_dir.mkdir(parents=True)
    path, _ = make_stage_three_capsule(index.capsules_dir)
    index.upsert(path)
    return settings, index, path


def test_live_analysis_persists_validated_artifact_and_exact_replay(tmp_path: Path) -> None:
    settings, index, path = setup_capsule(tmp_path)
    client = FakeClient()
    result = AnalysisService(settings, index=index, client=client).analyze(
        "cap_stage3_0001", mode="live"
    )

    assert result.status == "completed"
    assert result.artifact is not None
    assert result.artifact.root_causes[0].root_cause_id.startswith("RC-")
    imported = CapsuleArchive().import_capsule(path)
    assert imported.manifest.analysis_status == "completed"
    assert result.artifact == result.artifact.model_validate_json(imported.read(ANALYSIS_PATH))
    replay_path = settings.replay_dir / f"{result.artifact.request_sha256}.json"
    assert replay_path.is_file()
    assert "CAPSULE_CONTEXT" not in replay_path.read_text(encoding="utf-8")
    indexed_detail = index.get_detail("cap_stage3_0001")
    assert indexed_detail is not None
    assert indexed_detail.summary.analysis_status == "completed"

    replayed = AnalysisService(settings, index=index).analyze("cap_stage3_0001", mode="replay")
    assert replayed.status == "completed"
    assert replayed.artifact is not None
    assert replayed.artifact.mode == "replay"
    assert replayed.artifact.root_causes == result.artifact.root_causes


def test_unknown_model_reference_leaves_archive_and_replay_unchanged(tmp_path: Path) -> None:
    settings, index, path = setup_capsule(tmp_path)
    before = path.read_bytes()
    with pytest.raises(AnalysisError, match="unknown evidence references"):
        AnalysisService(
            settings,
            index=index,
            client=FakeClient(invalid_attempts=2),
        ).analyze("cap_stage3_0001", mode="live")
    assert path.read_bytes() == before
    assert not settings.replay_dir.exists()


def test_live_analysis_retries_invalid_evidence_reference_once(tmp_path: Path) -> None:
    settings, index, _ = setup_capsule(tmp_path)
    client = FakeClient(invalid_attempts=1)
    result = AnalysisService(settings, index=index, client=client).analyze(
        "cap_stage3_0001", mode="live"
    )
    assert result.status == "completed"
    assert len(client.requests) == 2


def test_live_analysis_retries_invalid_structure_once(tmp_path: Path) -> None:
    settings, index, _ = setup_capsule(tmp_path)

    class InvalidThenValidClient(FakeClient):
        def analyze(self, request: AnalysisRequest) -> ModelAnalysisResponse:
            if not self.requests:
                self.requests.append(request)
                raise InvalidModelResponseError("invalid structured response")
            return super().analyze(request)

    client = InvalidThenValidClient()
    result = AnalysisService(settings, index=index, client=client).analyze(
        "cap_stage3_0001", mode="live"
    )
    assert result.status == "completed"
    assert len(client.requests) == 2


def test_replay_requires_exact_record_and_off_mode_does_not_access_index(tmp_path: Path) -> None:
    settings, index, _ = setup_capsule(tmp_path)
    with pytest.raises(AnalysisError, match="replay record not found"):
        AnalysisService(settings, index=index).analyze("cap_stage3_0001", mode="replay")

    empty_settings = Settings(data_dir=tmp_path / "empty")
    result = AnalysisService(empty_settings).analyze("does-not-exist", mode="off")
    assert result.status == "model_off"
    assert not (tmp_path / "empty").exists()
