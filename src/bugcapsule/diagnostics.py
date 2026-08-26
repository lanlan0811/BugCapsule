"""Read-only startup diagnostics for first-run and demo readiness."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import Field

from bugcapsule.capsule.schema import CapsuleModel
from bugcapsule.config import Settings


class DoctorCheck(CapsuleModel):
    """One stable readiness assertion with an actionable diagnostic."""

    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    status: Literal["passed", "warning", "failed"]
    message: str = Field(min_length=1, max_length=500)


class DoctorReport(CapsuleModel):
    """Complete startup readiness result."""

    ready: bool
    checks: tuple[DoctorCheck, ...]


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class DoctorService:
    """Inspect local prerequisites without starting containers or changing files."""

    def __init__(
        self,
        settings: Settings,
        *,
        command_runner: CommandRunner = subprocess.run,
        executable_finder: Callable[[str], str | None] = shutil.which,
    ) -> None:
        self.settings = settings
        self.command_runner = command_runner
        self.executable_finder = executable_finder

    def run(self) -> DoctorReport:
        checks = (
            self._python(),
            self._source_root(),
            self._data_directory(),
            self._executable("git", required=True),
            self._docker(),
            self._verification_dockerfile(),
            self._model_mode(),
        )
        return DoctorReport(
            ready=all(check.status != "failed" for check in checks),
            checks=checks,
        )

    @staticmethod
    def _python() -> DoctorCheck:
        supported = (3, 10) <= sys.version_info[:2] <= (3, 12)
        return DoctorCheck(
            check_id="python_version",
            status="passed" if supported else "failed",
            message=(
                f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
                + (" 受支持" if supported else " 不在 3.10-3.12 支持范围")
            ),
        )

    def _source_root(self) -> DoctorCheck:
        root = self.settings.source_root.resolve()
        return DoctorCheck(
            check_id="source_root",
            status="passed" if root.is_dir() else "failed",
            message=f"源码根目录{'可用' if root.is_dir() else '不存在'}：{root}",
        )

    def _data_directory(self) -> DoctorCheck:
        target = self.settings.data_dir.resolve()
        parent = self._nearest_existing_parent(target)
        writable = parent.is_dir() and os.access(parent, os.W_OK)
        return DoctorCheck(
            check_id="data_directory",
            status="passed" if writable else "failed",
            message=f"数据目录父级{'可写' if writable else '不可写'}：{parent}",
        )

    @staticmethod
    def _nearest_existing_parent(path: Path) -> Path:
        candidate = path
        while not candidate.exists() and candidate != candidate.parent:
            candidate = candidate.parent
        return candidate

    def _executable(self, name: str, *, required: bool) -> DoctorCheck:
        executable = self.executable_finder(name)
        return DoctorCheck(
            check_id=f"{name}_cli",
            status="passed" if executable else "failed" if required else "warning",
            message=f"{name} CLI {'可用：' + executable if executable else '未找到'}",
        )

    def _docker(self) -> DoctorCheck:
        executable = self.executable_finder("docker")
        if executable is None:
            return DoctorCheck(
                check_id="docker_engine",
                status="failed",
                message="未找到 Docker CLI；隔离验证与主演示不可运行",
            )
        result = self._command((executable, "version", "--format", "{{.Server.Version}}"))
        version = result.stdout.strip() if result.returncode == 0 else ""
        return DoctorCheck(
            check_id="docker_engine",
            status="passed" if version else "failed",
            message=(f"Docker Engine {version}" if version else "Docker Engine 当前不可访问"),
        )

    def _verification_dockerfile(self) -> DoctorCheck:
        path = self.settings.verification_dockerfile.resolve()
        exists = path.is_file()
        return DoctorCheck(
            check_id="verification_dockerfile",
            status="passed" if exists else "failed",
            message=f"验证镜像定义{'可用' if exists else '不存在'}：{path}",
        )

    def _model_mode(self) -> DoctorCheck:
        mode = self.settings.model_mode
        if mode == "live":
            configured = bool(self.settings.model_name and self.settings.model_api_key)
            return DoctorCheck(
                check_id="model_mode",
                status="passed" if configured else "failed",
                message=("Live 模型配置完整" if configured else "Live 模式缺少模型名称或 API Key"),
            )
        if mode == "replay":
            available = self.settings.replay_dir.is_dir()
            return DoctorCheck(
                check_id="model_mode",
                status="passed" if available else "warning",
                message=("Replay 目录可用" if available else "Replay 目录尚未创建"),
            )
        return DoctorCheck(
            check_id="model_mode",
            status="warning",
            message="模型模式为 off；证据浏览可用，AI 分析不可用",
        )

    def _command(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return self.command_runner(
                command,
                cwd=self.settings.source_root,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return subprocess.CompletedProcess(command, 1, "", "")
