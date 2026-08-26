"""Explicit approval, temporary worktrees, and before/after verification persistence."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path

from bugcapsule.capsule.archive import CapsuleArchive, CapsuleArchiveError, create_manifest
from bugcapsule.capsule.identifiers import canonical_json, sha256_hex
from bugcapsule.capsule.redaction import Redactor
from bugcapsule.capsule.schema import RedactionReport, TestResult, VerificationRun
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleIndex, CapsuleIndexError
from bugcapsule.verification.docker import (
    DockerVerificationExecutor,
    ExecutionResult,
    VerificationExecutor,
    VerificationExecutorError,
)
from bugcapsule.verification.schema import VerificationArtifact

VERIFICATION_RESULT_PATH = "verification/result.json"
VERIFICATION_BEFORE_LOG_PATH = "verification/before.log"
VERIFICATION_AFTER_LOG_PATH = "verification/after.log"
VERIFICATION_REDACTION_PATH = "verification/redaction-report.json"

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class VerificationError(RuntimeError):
    """Safe failure for approval, isolation, execution, or persistence."""


class VerificationService:
    """Verify an exact approved Patch without changing the configured source root."""

    def __init__(
        self,
        settings: Settings,
        *,
        index: CapsuleIndex | None = None,
        archive: CapsuleArchive | None = None,
        executor: VerificationExecutor | None = None,
        command_runner: CommandRunner = subprocess.run,
        git_path: str | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self.settings = settings
        self.index = index or CapsuleIndex.from_settings(settings)
        self.archive = archive or CapsuleArchive()
        self.executor = executor or DockerVerificationExecutor(settings)
        self._command_runner = command_runner
        self._git_path = git_path
        self.redactor = redactor or Redactor()

    def verify(
        self,
        capsule_id: str,
        *,
        patch_id: str,
        approved_sha256: str,
        explicitly_approved: bool,
    ) -> VerificationArtifact:
        if not explicitly_approved:
            raise VerificationError("verification requires explicit Patch approval")
        try:
            detail = self.index.get_detail(capsule_id)
            if detail is None:
                raise VerificationError(f"capsule does not exist: {capsule_id}")
            if detail.patch is None or detail.patch_diff is None:
                raise VerificationError("verification requires a validated Patch")
            candidate = detail.patch.candidate
            if patch_id != candidate.patch_id:
                raise VerificationError("approved Patch ID does not match capsule Patch")
            if approved_sha256 != candidate.sha256:
                raise VerificationError("approved SHA-256 does not match capsule Patch")
            self._verify_source_revision(
                detail.manifest.git.commit_sha, detail.manifest.git.diff_sha256
            )
            original_hashes = self._workspace_hashes(candidate.modified_files)
            started_at = datetime.now(timezone.utc)
            self.executor.prepare()
            with tempfile.TemporaryDirectory(prefix="bugcapsule-verify-") as temporary:
                temporary_root = Path(temporary)
                before = temporary_root / "before"
                after = temporary_root / "after"
                self._copy_workspace(before)
                self._copy_workspace(after)
                patch_path = temporary_root / "candidate.diff"
                patch_path.write_text(detail.patch_diff, encoding="utf-8", newline="\n")
                self._apply_patch(after, patch_path)
                before_execution = self.executor.run(before)
                after_execution = self.executor.run(after)
            if self._workspace_hashes(candidate.modified_files) != original_hashes:
                raise VerificationError("source workspace changed during isolated verification")
            completed_at = datetime.now(timezone.utc)
            before_log, after_log, redaction_report = self._redact_outputs(
                before_execution,
                after_execution,
                completed_at,
            )
            before_result = self._test_result(before_execution, before_log)
            after_result = self._test_result(after_execution, after_log)
            passed = (
                before_result.exit_code != 0
                and not before_result.timed_out
                and after_result.exit_code == 0
                and not after_result.timed_out
            )
            run = VerificationRun.create(
                patch_id=candidate.patch_id,
                patch_sha256=candidate.sha256,
                approved_sha256=approved_sha256,
                explicitly_approved=True,
                status="passed" if passed else "failed",
                before=before_result,
                after=after_result,
            )
            artifact = VerificationArtifact(
                image=self.executor.image,
                command_id=self.executor.command_id,
                started_at=started_at,
                completed_at=completed_at,
                run=run,
            )
            self._persist(
                detail.archive_path,
                artifact,
                before_log,
                after_log,
                redaction_report,
            )
            return artifact
        except VerificationError:
            raise
        except (
            CapsuleArchiveError,
            CapsuleIndexError,
            OSError,
            subprocess.SubprocessError,
            ValueError,
            VerificationExecutorError,
        ) as exc:
            raise VerificationError(str(exc)) from exc

    def _copy_workspace(self, destination: Path) -> None:
        source_root = self.settings.source_root.resolve()
        if not source_root.is_dir():
            raise VerificationError("configured source root does not exist")
        shutil.copytree(
            source_root,
            destination,
            symlinks=True,
            ignore=shutil.ignore_patterns(*self.settings.verification_copy_excludes),
        )
        symlinks = sorted(path for path in destination.rglob("*") if path.is_symlink())
        if symlinks:
            raise VerificationError("verification source contains symbolic links")

    def _apply_patch(self, worktree: Path, patch_path: Path) -> None:
        git = self._git()
        common = (
            git,
            "apply",
            "--whitespace=error-all",
            "--recount",
        )
        check = self._run((*common, "--check", str(patch_path)), cwd=worktree, timeout=30)
        if check.returncode != 0:
            raise VerificationError(
                f"Patch applicability check failed with exit code {check.returncode}"
            )
        applied = self._run((*common, str(patch_path)), cwd=worktree, timeout=30)
        if applied.returncode != 0:
            raise VerificationError(f"Patch application failed with exit code {applied.returncode}")

    def _verify_source_revision(self, expected_commit: str, expected_diff_sha: str | None) -> None:
        if not self.settings.verification_require_git_match:
            return
        git = self._git()
        source_root = self.settings.source_root.resolve()
        commit = self._run((git, "rev-parse", "HEAD"), cwd=source_root, timeout=10)
        if commit.returncode != 0 or commit.stdout.strip() != expected_commit:
            raise VerificationError("source Git commit does not match capsule")
        diff = self._run(
            (git, "diff", "--no-ext-diff", "--unified=3"),
            cwd=source_root,
            timeout=10,
        )
        if diff.returncode != 0:
            raise VerificationError("source Git diff could not be inspected")
        actual_diff_sha = sha256_hex(diff.stdout.encode("utf-8")) if diff.stdout else None
        if actual_diff_sha != expected_diff_sha:
            raise VerificationError("source Git diff does not match capsule")

    def _workspace_hashes(self, paths: tuple[str, ...]) -> Mapping[str, str | None]:
        root = self.settings.source_root.resolve()
        hashes: dict[str, str | None] = {}
        for path in paths:
            target = (root / Path(*path.split("/"))).resolve()
            if not target.is_relative_to(root):
                raise VerificationError("Patch target escapes source workspace")
            hashes[path] = sha256_hex(target.read_bytes()) if target.is_file() else None
        return hashes

    def _redact_outputs(
        self,
        before: ExecutionResult,
        after: ExecutionResult,
        completed_at: datetime,
    ) -> tuple[bytes, bytes, RedactionReport]:
        before_redaction = self.redactor.redact(
            before.output.decode("utf-8", errors="replace"),
            completed_at=completed_at,
            root_location="$/verification/before",
        )
        after_redaction = self.redactor.redact(
            after.output.decode("utf-8", errors="replace"),
            completed_at=completed_at,
            root_location="$/verification/after",
        )
        if not isinstance(before_redaction.value, str) or not isinstance(
            after_redaction.value, str
        ):
            raise VerificationError("verification output redaction returned invalid data")
        findings = (*before_redaction.report.findings, *after_redaction.report.findings)
        report = RedactionReport(
            completed_at=completed_at,
            total_findings=len(findings),
            findings=findings,
        )
        return (
            before_redaction.value.encode("utf-8"),
            after_redaction.value.encode("utf-8"),
            report,
        )

    def _test_result(self, execution: ExecutionResult, output: bytes) -> TestResult:
        return TestResult(
            command_id=self.executor.command_id,
            exit_code=execution.exit_code,
            duration_ms=execution.duration_ms,
            timed_out=execution.timed_out,
            output_sha256=sha256_hex(output),
        )

    def _persist(
        self,
        archive_path: Path,
        artifact: VerificationArtifact,
        before_log: bytes,
        after_log: bytes,
        redaction_report: RedactionReport,
    ) -> None:
        imported = self.archive.import_capsule(archive_path)
        payloads = dict(imported.payloads)
        payloads.update(
            {
                VERIFICATION_RESULT_PATH: canonical_json(artifact.model_dump(mode="json")) + b"\n",
                VERIFICATION_BEFORE_LOG_PATH: before_log,
                VERIFICATION_AFTER_LOG_PATH: after_log,
                VERIFICATION_REDACTION_PATH: canonical_json(
                    redaction_report.model_dump(mode="json")
                )
                + b"\n",
            }
        )
        media_types = {item.path: item.media_type for item in imported.manifest.files}
        media_types.update(
            {
                VERIFICATION_RESULT_PATH: "application/json",
                VERIFICATION_BEFORE_LOG_PATH: "text/plain",
                VERIFICATION_AFTER_LOG_PATH: "text/plain",
                VERIFICATION_REDACTION_PATH: "application/json",
            }
        )
        manifest = create_manifest(
            capsule_id=imported.manifest.capsule_id,
            created_at=imported.manifest.created_at,
            service=imported.manifest.service,
            trace=imported.manifest.trace,
            git=imported.manifest.git,
            environment=imported.manifest.environment,
            payloads=payloads,
            media_types=media_types,
            analysis_status=imported.manifest.analysis_status,
            verification_status=artifact.run.status,
        )
        self.archive.export(archive_path, manifest, payloads)
        self.index.upsert(archive_path)

    def _git(self) -> str:
        git = self._git_path or shutil.which("git")
        if git is None:
            raise VerificationError("Git CLI is unavailable")
        return git

    def _run(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        return self._command_runner(
            command,
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
