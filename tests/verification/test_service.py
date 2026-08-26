import subprocess
from pathlib import Path

import pytest

from bugcapsule.capsule import CapsuleArchive
from bugcapsule.capsule.identifiers import sha256_hex
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleIndex
from bugcapsule.patching.request import PatchRequest
from bugcapsule.patching.schema import ModelPatchResponse
from bugcapsule.patching.service import PatchGenerationService
from bugcapsule.verification.docker import ExecutionResult, VerificationExecutor
from bugcapsule.verification.service import VerificationError, VerificationService
from tests.patching.test_safety import SOURCE_PATH
from tests.patching.test_service import setup_analyzed_capsule


class ApplicablePatchClient:
    def __init__(self, evidence_id: str) -> None:
        self.evidence_id = evidence_id

    def generate(self, request: PatchRequest) -> ModelPatchResponse:
        diff = (
            f"diff --git a/{SOURCE_PATH} b/{SOURCE_PATH}\n"
            "index 1111111..2222222 100644\n"
            f"--- a/{SOURCE_PATH}\n"
            f"+++ b/{SOURCE_PATH}\n"
            "@@ -1,2 +1,3 @@\n"
            " session = session_factory()\n"
            "+session.close()\n"
            " session.execute(statement)\n"
        )
        return ModelPatchResponse(
            summary="在异常路径释放连接",
            unified_diff=diff,
            evidence_refs=(self.evidence_id,),
            safety_notes=(),
        )


class FakeExecutor(VerificationExecutor):
    image = "test-verifier:1"
    command_id = "connection-release-regression-v1"

    def __init__(self, *, after_exit_code: int = 0) -> None:
        self.after_exit_code = after_exit_code
        self.prepared = 0
        self.worktrees: list[Path] = []

    def prepare(self) -> None:
        self.prepared += 1

    def run(self, worktree: Path) -> ExecutionResult:
        self.worktrees.append(worktree)
        source = worktree / Path(*SOURCE_PATH.split("/"))
        patched = "session.close()" in source.read_text(encoding="utf-8")
        if patched:
            return ExecutionResult(
                self.after_exit_code,
                21,
                False,
                b"after user@example.com",
            )
        return ExecutionResult(1, 14, False, b"before token=secret-value-123456")


def setup_patch(tmp_path: Path) -> tuple[Settings, CapsuleIndex, Path, str, str]:
    settings, index, path, evidence_id = setup_analyzed_capsule(tmp_path)
    settings = settings.model_copy(update={"verification_require_git_match": False})
    index = CapsuleIndex.from_settings(settings)
    result = PatchGenerationService(
        settings,
        index=index,
        client=ApplicablePatchClient(evidence_id),
    ).generate("cap_stage3_0001", mode="live")
    assert result.artifact is not None
    candidate = result.artifact.candidate
    return settings, index, path, candidate.patch_id, candidate.sha256


def test_verification_requires_exact_explicit_approval_before_execution(tmp_path: Path) -> None:
    settings, index, _, patch_id, patch_sha = setup_patch(tmp_path)
    executor = FakeExecutor()
    service = VerificationService(settings, index=index, executor=executor)

    with pytest.raises(VerificationError, match="explicit Patch approval"):
        service.verify(
            "cap_stage3_0001",
            patch_id=patch_id,
            approved_sha256=patch_sha,
            explicitly_approved=False,
        )
    with pytest.raises(VerificationError, match="Patch ID"):
        service.verify(
            "cap_stage3_0001",
            patch_id="PATCH-AAAAAAAAAAAA",
            approved_sha256=patch_sha,
            explicitly_approved=True,
        )
    with pytest.raises(VerificationError, match="SHA-256"):
        service.verify(
            "cap_stage3_0001",
            patch_id=patch_id,
            approved_sha256="a" * 64,
            explicitly_approved=True,
        )
    assert executor.prepared == 0


def test_verification_uses_two_temp_copies_redacts_logs_and_preserves_source(
    tmp_path: Path,
) -> None:
    settings, index, path, patch_id, patch_sha = setup_patch(tmp_path)
    source = settings.source_root / Path(*SOURCE_PATH.split("/"))
    original = source.read_bytes()
    executor = FakeExecutor()
    artifact = VerificationService(settings, index=index, executor=executor).verify(
        "cap_stage3_0001",
        patch_id=patch_id,
        approved_sha256=patch_sha,
        explicitly_approved=True,
    )

    assert artifact.run.status == "passed"
    assert artifact.run.patch_sha256 == patch_sha
    assert artifact.run.approved_sha256 == patch_sha
    assert executor.prepared == 1
    assert len(executor.worktrees) == 2
    assert executor.worktrees[0] != executor.worktrees[1]
    assert source.read_bytes() == original
    imported = CapsuleArchive().import_capsule(path)
    assert b"secret-value" not in imported.read("verification/before.log")
    assert b"user@example.com" not in imported.read("verification/after.log")
    detail = index.get_detail("cap_stage3_0001")
    assert detail is not None
    assert detail.verification == artifact
    assert detail.summary.verification_status == "passed"
    assert "[REDACTED:EMAIL]" in (detail.verification_after_log or "")


def test_verification_records_failed_before_after_contract(tmp_path: Path) -> None:
    settings, index, _, patch_id, patch_sha = setup_patch(tmp_path)
    artifact = VerificationService(
        settings,
        index=index,
        executor=FakeExecutor(after_exit_code=1),
    ).verify(
        "cap_stage3_0001",
        patch_id=patch_id,
        approved_sha256=patch_sha,
        explicitly_approved=True,
    )
    assert artifact.run.status == "failed"


def test_revision_binding_rejects_commit_diff_and_command_failures(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    expected_commit = "b" * 40
    diff = "diff --git a/a b/a\n"
    expected_diff_sha = sha256_hex(diff.encode("utf-8"))

    def service_with(results: list[subprocess.CompletedProcess[str]]) -> VerificationService:
        iterator = iter(results)

        def runner(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
            return next(iterator)

        return VerificationService(
            Settings(source_root=source_root),
            executor=FakeExecutor(),
            command_runner=runner,
            git_path="git",
        )

    success = service_with(
        [
            subprocess.CompletedProcess((), 0, expected_commit + "\n", ""),
            subprocess.CompletedProcess((), 0, diff, ""),
        ]
    )
    success._verify_source_revision(expected_commit, expected_diff_sha)

    wrong_commit = service_with([subprocess.CompletedProcess((), 0, "a" * 40, "")])
    with pytest.raises(VerificationError, match="commit does not match"):
        wrong_commit._verify_source_revision(expected_commit, expected_diff_sha)

    bad_diff = service_with(
        [
            subprocess.CompletedProcess((), 0, expected_commit, ""),
            subprocess.CompletedProcess((), 1, "", ""),
        ]
    )
    with pytest.raises(VerificationError, match="diff could not"):
        bad_diff._verify_source_revision(expected_commit, expected_diff_sha)

    wrong_diff = service_with(
        [
            subprocess.CompletedProcess((), 0, expected_commit, ""),
            subprocess.CompletedProcess((), 0, "different", ""),
        ]
    )
    with pytest.raises(VerificationError, match="diff does not match"):
        wrong_diff._verify_source_revision(expected_commit, expected_diff_sha)


def test_copy_apply_and_git_dependency_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = VerificationService(
        Settings(source_root=tmp_path / "missing", verification_require_git_match=False),
        executor=FakeExecutor(),
    )
    with pytest.raises(VerificationError, match="source root"):
        missing._copy_workspace(tmp_path / "copy")

    source_root = tmp_path / "source"
    source_root.mkdir()
    patch = tmp_path / "patch.diff"
    patch.write_text("diff", encoding="utf-8")

    def check_fails(*_: object, **__: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess((), 1, "", "")

    failed_check = VerificationService(
        Settings(source_root=source_root, verification_require_git_match=False),
        executor=FakeExecutor(),
        command_runner=check_fails,
        git_path="git",
    )
    with pytest.raises(VerificationError, match="applicability check"):
        failed_check._apply_patch(source_root, patch)

    results = iter(
        [
            subprocess.CompletedProcess((), 0, "", ""),
            subprocess.CompletedProcess((), 1, "", ""),
        ]
    )
    failed_apply = VerificationService(
        Settings(source_root=source_root, verification_require_git_match=False),
        executor=FakeExecutor(),
        command_runner=lambda *_args, **_kwargs: next(results),
        git_path="git",
    )
    with pytest.raises(VerificationError, match="Patch application failed"):
        failed_apply._apply_patch(source_root, patch)

    monkeypatch.setattr("bugcapsule.verification.service.shutil.which", lambda _: None)
    unavailable = VerificationService(
        Settings(source_root=source_root),
        executor=FakeExecutor(),
    )
    with pytest.raises(VerificationError, match="Git CLI"):
        unavailable._git()
