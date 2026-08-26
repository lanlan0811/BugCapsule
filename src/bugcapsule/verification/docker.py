"""Resource-constrained Docker execution for fixed regression commands."""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from bugcapsule.config import Settings

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class VerificationExecutorError(RuntimeError):
    """Safe diagnostic for unavailable or failed isolated execution."""


@dataclass(frozen=True)
class ExecutionResult:
    """Bounded raw output and process outcome from one container."""

    exit_code: int
    duration_ms: int
    timed_out: bool
    output: bytes


class VerificationExecutor:
    """Interface shared by the Docker executor and deterministic test doubles."""

    image: str
    command_id: str

    def prepare(self) -> None:
        raise NotImplementedError

    def run(self, worktree: Path) -> ExecutionResult:
        raise NotImplementedError


class DockerVerificationExecutor(VerificationExecutor):
    """Build one verifier image, then run read-only, networkless worktree mounts."""

    def __init__(
        self,
        settings: Settings,
        *,
        command_runner: CommandRunner = subprocess.run,
        docker_path: str | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self.settings = settings
        self.image = settings.verification_image
        self.command_id = settings.verification_command_id
        self._command_runner = command_runner
        self._docker_path = docker_path
        self._clock = clock

    def prepare(self) -> None:
        docker = self._docker()
        inspect = self._run_command((docker, "image", "inspect", self.image), timeout=30)
        if inspect.returncode == 0:
            return
        dockerfile = (self.settings.source_root / self.settings.verification_dockerfile).resolve()
        source_root = self.settings.source_root.resolve()
        if not dockerfile.is_file() or not dockerfile.is_relative_to(source_root):
            raise VerificationExecutorError(
                "verification Dockerfile is missing or outside source root"
            )
        build = self._run_command(
            (
                docker,
                "build",
                "--file",
                str(dockerfile),
                "--tag",
                self.image,
                str(source_root),
            ),
            timeout=600,
        )
        if build.returncode != 0:
            raise VerificationExecutorError(
                f"verification image build failed with exit code {build.returncode}"
            )

    def run(self, worktree: Path) -> ExecutionResult:
        docker = self._docker()
        resolved_worktree = worktree.resolve()
        if not resolved_worktree.is_dir():
            raise VerificationExecutorError("verification worktree does not exist")
        mount = f"type=bind,source={resolved_worktree},target=/workspace,readonly"
        command: Sequence[str] = (
            docker,
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.settings.verification_pids_limit),
            "--memory",
            self.settings.verification_memory,
            "--cpus",
            str(self.settings.verification_cpus),
            "--user",
            "10001:10001",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m,mode=1777",
            "--mount",
            mount,
            "--workdir",
            "/workspace",
            "--env",
            "PYTHONPATH=/workspace/src",
            self.image,
            *self.settings.verification_command,
        )
        started = self._clock()
        try:
            result = self._run_command(
                command,
                timeout=self.settings.verification_timeout_seconds,
            )
            duration_ms = max(0, round((self._clock() - started) * 1000))
            output = self._output(result.stdout, result.stderr)
            return ExecutionResult(result.returncode, duration_ms, False, output)
        except subprocess.TimeoutExpired as exc:
            duration_ms = max(0, round((self._clock() - started) * 1000))
            output = self._output(exc.stdout or "", exc.stderr or "")
            return ExecutionResult(124, duration_ms, True, output)

    def _docker(self) -> str:
        docker = self._docker_path if self._docker_path is not None else shutil.which("docker")
        if not docker:
            raise VerificationExecutorError(
                "Docker CLI is unavailable; install and start Docker Desktop"
            )
        return docker

    def _run_command(
        self,
        command: Sequence[str],
        *,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        return self._command_runner(
            command,
            cwd=self.settings.source_root.resolve(),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )

    def _output(self, stdout: str | bytes, stderr: str | bytes) -> bytes:
        stdout_text = (
            stdout.decode("utf-8", errors="replace") if isinstance(stdout, bytes) else stdout
        )
        stderr_text = (
            stderr.decode("utf-8", errors="replace") if isinstance(stderr, bytes) else stderr
        )
        output = f"STDOUT\n{stdout_text}\nSTDERR\n{stderr_text}".encode()
        if len(output) > self.settings.verification_output_max_bytes:
            raise VerificationExecutorError("verification output exceeds configured byte limit")
        return output
