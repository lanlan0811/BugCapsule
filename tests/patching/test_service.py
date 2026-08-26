from pathlib import Path

import pytest

from bugcapsule.analysis.request import AnalysisRequest
from bugcapsule.analysis.schema import ModelAnalysisResponse, ModelRootCause
from bugcapsule.analysis.service import AnalysisService
from bugcapsule.capsule import CapsuleArchive, EvidenceKind, PatchCandidate, create_manifest
from bugcapsule.capsule.identifiers import canonical_json, sha256_hex
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleIndex, CapsuleIndexError
from bugcapsule.patching.request import PatchRequest
from bugcapsule.patching.schema import ModelPatchResponse
from bugcapsule.patching.service import (
    PATCH_DIFF_PATH,
    PATCH_METADATA_PATH,
    PatchGenerationError,
    PatchGenerationService,
)
from tests.capsule.factories import make_stage_three_capsule
from tests.patching.test_safety import SOURCE_PATH, diff_for


class RootCauseClient:
    def __init__(self, source_evidence_id: str) -> None:
        self.source_evidence_id = source_evidence_id

    def analyze(self, request: AnalysisRequest) -> ModelAnalysisResponse:
        assert self.source_evidence_id in request.included_evidence_ids
        return ModelAnalysisResponse(
            root_causes=(
                ModelRootCause(
                    rank=1,
                    hypothesis="连接未归还导致连接池耗尽",
                    confidence=0.97,
                    evidence_refs=(self.source_evidence_id,),
                    unknowns=(),
                ),
            )
        )


class PatchClient:
    def __init__(self, source_evidence_id: str, *, invalid_attempts: int = 0) -> None:
        self.source_evidence_id = source_evidence_id
        self.invalid_attempts = invalid_attempts
        self.requests: list[PatchRequest] = []

    def generate(self, request: PatchRequest) -> ModelPatchResponse:
        self.requests.append(request)
        path = "src/bugcapsule/demo/uncited.py"
        if len(self.requests) > self.invalid_attempts:
            path = SOURCE_PATH
        return ModelPatchResponse(
            summary="确保异常路径归还数据库连接",
            unified_diff=diff_for(path),
            evidence_refs=(self.source_evidence_id,),
            safety_notes=("保持现有接口行为",),
        )


def setup_analyzed_capsule(
    tmp_path: Path,
) -> tuple[Settings, CapsuleIndex, Path, str]:
    workspace = tmp_path / "workspace"
    source = workspace / Path(*SOURCE_PATH.split("/"))
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("session = session_factory()\nsession.execute(statement)\n", encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data",
        replay_dir=tmp_path / "replay",
        source_root=workspace,
        model_name="gpt-test",
        model_api_key="test-key",
        model_provider="test-provider",
    )
    index = CapsuleIndex.from_settings(settings)
    index.capsules_dir.mkdir(parents=True)
    path, evidence = make_stage_three_capsule(index.capsules_dir)
    index.upsert(path)
    source_evidence_id = next(
        item.evidence_id for item in evidence if item.kind is EvidenceKind.SOURCE
    )
    AnalysisService(
        settings,
        index=index,
        client=RootCauseClient(source_evidence_id),
    ).analyze("cap_stage3_0001", mode="live")
    return settings, index, path, source_evidence_id


def test_live_patch_is_validated_persisted_indexed_and_replayable(tmp_path: Path) -> None:
    settings, index, path, source_evidence_id = setup_analyzed_capsule(tmp_path)
    client = PatchClient(source_evidence_id)
    result = PatchGenerationService(settings, index=index, client=client).generate(
        "cap_stage3_0001", mode="live"
    )

    assert result.status == "completed"
    assert result.artifact is not None
    candidate = result.artifact.candidate
    assert candidate.modified_files == (SOURCE_PATH,)
    assert candidate.patch_id.startswith("PATCH-")
    imported = CapsuleArchive().import_capsule(path)
    assert imported.read(PATCH_DIFF_PATH).decode("utf-8").endswith("\n")
    assert result.artifact == result.artifact.model_validate_json(
        imported.read(PATCH_METADATA_PATH)
    )
    detail = index.get_detail("cap_stage3_0001")
    assert detail is not None
    assert detail.patch == result.artifact
    assert detail.patch_diff == imported.read(PATCH_DIFF_PATH).decode("utf-8")
    replay_files = list(settings.replay_dir.glob("*.patch.json"))
    assert len(replay_files) == 1
    assert "PATCH_CONTEXT" not in replay_files[0].read_text(encoding="utf-8")

    replayed = PatchGenerationService(settings, index=index).generate(
        "cap_stage3_0001", mode="replay"
    )
    assert replayed.artifact is not None
    assert replayed.artifact.mode == "replay"
    assert replayed.artifact.candidate == candidate


def test_unsafe_patch_retries_once_then_leaves_capsule_unchanged(tmp_path: Path) -> None:
    settings, index, path, source_evidence_id = setup_analyzed_capsule(tmp_path)
    before = path.read_bytes()
    client = PatchClient(source_evidence_id, invalid_attempts=2)
    with pytest.raises(PatchGenerationError, match="no matching source evidence"):
        PatchGenerationService(settings, index=index, client=client).generate(
            "cap_stage3_0001", mode="live"
        )
    assert len(client.requests) == 2
    assert path.read_bytes() == before
    assert list(settings.replay_dir.glob("*.patch.json")) == []


def test_patch_requires_analysis_exact_replay_and_known_root_cause(tmp_path: Path) -> None:
    settings, index, _, source_evidence_id = setup_analyzed_capsule(tmp_path)
    with pytest.raises(PatchGenerationError, match="Patch replay not found"):
        PatchGenerationService(settings, index=index).generate("cap_stage3_0001", mode="replay")
    with pytest.raises(PatchGenerationError, match="root cause does not exist"):
        PatchGenerationService(
            settings,
            index=index,
            client=PatchClient(source_evidence_id),
        ).generate(
            "cap_stage3_0001",
            root_cause_id="RC-AAAAAAAAAAAA",
            mode="live",
        )

    off = PatchGenerationService(Settings(data_dir=tmp_path / "empty")).generate(
        "missing", mode="off"
    )
    assert off.status == "model_off"
    assert not (tmp_path / "empty").exists()

    raw_settings = Settings(
        data_dir=tmp_path / "raw",
        model_name="gpt-test",
        model_api_key="test-key",
    )
    raw_index = CapsuleIndex.from_settings(raw_settings)
    raw_index.capsules_dir.mkdir(parents=True)
    make_stage_three_capsule(raw_index.capsules_dir)
    raw_index.rebuild()
    with pytest.raises(PatchGenerationError, match="requires completed root-cause analysis"):
        PatchGenerationService(raw_settings, index=raw_index).generate(
            "cap_stage3_0001", mode="live"
        )


def test_index_revalidates_patch_policy_instead_of_trusting_metadata(tmp_path: Path) -> None:
    settings, index, path, source_evidence_id = setup_analyzed_capsule(tmp_path)
    result = PatchGenerationService(
        settings,
        index=index,
        client=PatchClient(source_evidence_id),
    ).generate("cap_stage3_0001", mode="live")
    assert result.artifact is not None
    imported = CapsuleArchive().import_capsule(path)
    unsafe_path = "src/bugcapsule/demo/uncited.py"
    unsafe_diff = diff_for(unsafe_path) + "\n"
    unsafe_candidate = PatchCandidate.create(
        root_cause_id=result.artifact.candidate.root_cause_id,
        summary="尝试修改无证据文件",
        diff_path=PATCH_DIFF_PATH,
        sha256=sha256_hex(unsafe_diff.encode("utf-8")),
        modified_files=(unsafe_path,),
        evidence_refs=(source_evidence_id,),
        safety_checks=result.artifact.candidate.safety_checks,
    )
    unsafe_artifact = result.artifact.model_copy(update={"candidate": unsafe_candidate})
    payloads = dict(imported.payloads)
    payloads[PATCH_DIFF_PATH] = unsafe_diff.encode("utf-8")
    payloads[PATCH_METADATA_PATH] = canonical_json(unsafe_artifact.model_dump(mode="json")) + b"\n"
    media_types = {item.path: item.media_type for item in imported.manifest.files}
    manifest = create_manifest(
        capsule_id=imported.manifest.capsule_id,
        created_at=imported.manifest.created_at,
        service=imported.manifest.service,
        trace=imported.manifest.trace,
        git=imported.manifest.git,
        environment=imported.manifest.environment,
        payloads=payloads,
        media_types=media_types,
        analysis_status="completed",
    )
    CapsuleArchive().export(path, manifest, payloads)
    with pytest.raises(CapsuleIndexError, match="invalid or unsafe Patch"):
        index.upsert(path)
