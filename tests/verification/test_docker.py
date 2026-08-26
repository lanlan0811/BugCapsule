import subprocess
from pathlib import Path

import pytest

from bugcapsule.config import Settings
from bugcapsule.verification.docker import (
    DockerVerificationExecutor,
    VerificationExecutorError,
)


def test_docker_executor_uses_read_only_networkless_resource_limits(tmp_path: Path) -> None:
    commands: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(command))
        return subprocess.CompletedProcess(command, 0, stdout="passed", stderr="")

    settings = Settings(source_root=tmp_path)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    clock_values = iter((1.0, 1.125))
    executor = DockerVerificationExecutor(
        settings,
        command_runner=runner,
        docker_path="docker",
        clock=lambda: next(clock_values),
    )
    executor.prepare()
    result = executor.run(worktree)

    assert commands[0] == ("docker", "image", "inspect", settings.verification_image)
    run = commands[1]
    assert run[:3] == ("docker", "run", "--rm")
    assert ("--network", "none") == run[3:5]
    assert "--read-only" in run
    assert ("--cap-drop", "ALL") == run[6:8]
    assert "no-new-privileges:true" in run
    assert "--pids-limit" in run
    assert "--memory" in run
    assert "--cpus" in run
    assert "--user" in run
    assert "10001:10001" in run
    assert "readonly" in run[run.index("--mount") + 1]
    assert run[-len(settings.verification_command) :] == settings.verification_command
    assert result.exit_code == 0
    assert result.duration_ms == 125
    assert result.output == b"STDOUT\npassed\nSTDERR\n"


def test_docker_executor_builds_missing_image_and_bounds_failures(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile.verify").write_text("FROM scratch\n", encoding="utf-8")
    commands: list[tuple[str, ...]] = []

    def runner(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(tuple(command))
        returncode = 1 if command[1:3] == ("image", "inspect") else 0
        return subprocess.CompletedProcess(command, returncode, stdout="", stderr="")

    settings = Settings(source_root=tmp_path)
    executor = DockerVerificationExecutor(settings, command_runner=runner, docker_path="docker")
    executor.prepare()
    assert commands[1][1] == "build"
    assert "--file" in commands[1]
    assert "--tag" in commands[1]

    missing = DockerVerificationExecutor(settings, docker_path="")
    with pytest.raises(VerificationExecutorError, match="Docker CLI"):
        missing._docker()

    small = Settings(source_root=tmp_path, verification_output_max_bytes=1024)
    oversized = DockerVerificationExecutor(small, docker_path="docker")
    with pytest.raises(VerificationExecutorError, match="output exceeds"):
        oversized._output("x" * 1024, "y")


def test_docker_executor_reports_build_worktree_and_timeout_failures(tmp_path: Path) -> None:
    settings = Settings(source_root=tmp_path)

    missing_file = DockerVerificationExecutor(
        settings,
        command_runner=lambda command, **_: subprocess.CompletedProcess(command, 1, "", ""),
        docker_path="docker",
    )
    with pytest.raises(VerificationExecutorError, match="Dockerfile"):
        missing_file.prepare()

    (tmp_path / "Dockerfile.verify").write_text("FROM scratch\n", encoding="utf-8")

    def build_fails(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 1, "", "")

    failed_build = DockerVerificationExecutor(
        settings,
        command_runner=build_fails,
        docker_path="docker",
    )
    with pytest.raises(VerificationExecutorError, match="image build failed"):
        failed_build.prepare()
    with pytest.raises(VerificationExecutorError, match="worktree"):
        failed_build.run(tmp_path / "missing")

    worktree = tmp_path / "worktree"
    worktree.mkdir()

    def times_out(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 1, output=b"partial", stderr=b"late")

    clock_values = iter((1.0, 2.5))
    timed = DockerVerificationExecutor(
        settings,
        command_runner=times_out,
        docker_path="docker",
        clock=lambda: next(clock_values),
    ).run(worktree)
    assert timed.timed_out is True
    assert timed.exit_code == 124
    assert timed.duration_ms == 1500
    assert b"partial" in timed.output
