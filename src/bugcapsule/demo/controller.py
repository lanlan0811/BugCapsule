"""Safe orchestration for the local Docker demonstration."""

import json
import re
import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

from bugcapsule.demo.config import DemoSettings

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


class DemoControlError(RuntimeError):
    """Explain an unavailable dependency or failed demo operation."""


@dataclass(frozen=True)
class DemoRunResult:
    """Expected HTTP outcomes from one deterministic fault run."""

    first_status: int
    second_status: int
    exhausted_status: int
    fault: str


@dataclass(frozen=True)
class DemoTelemetrySyncResult:
    """Latest captured pool-exhaustion Trace synchronized from Docker."""

    trace_id: str
    telemetry_dir: Path


class DemoController:
    """Coordinate Compose and the order service without invoking a shell."""

    def __init__(
        self,
        settings: DemoSettings,
        *,
        command_runner: CommandRunner = subprocess.run,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._command_runner = command_runner
        self._http_transport = http_transport

    def up(self) -> None:
        self._compose("up", "--build", "--detach", "--wait")

    def down(self) -> None:
        self._compose("down")

    def reset(self) -> dict[str, object]:
        with self._client() as client:
            response = client.post("/demo/reset")
        self._require_status(response, 200, "重置演示")
        payload = response.json()
        if not isinstance(payload, dict):
            raise DemoControlError("重置响应不是 JSON 对象")
        return payload

    def run(self) -> DemoRunResult:
        self.reset()
        with self._client() as client:
            responses = [client.post("/demo/leak") for _ in range(3)]

        expected = (500, 500, 503)
        actual = tuple(response.status_code for response in responses)
        if actual != expected:
            raise DemoControlError(f"故障状态序列不符合预期：{actual}")

        detail = responses[-1].json().get("detail", {})
        fault = detail.get("fault") if isinstance(detail, dict) else None
        if fault != "database_pool_exhausted":
            raise DemoControlError("第三次请求未返回 database_pool_exhausted")
        return DemoRunResult(*actual, fault=fault)

    def sync_telemetry(self) -> DemoTelemetrySyncResult:
        """Copy container telemetry locally and select the latest exhaustion Trace."""
        destination = self.settings.telemetry_dir.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        source = f"{self.settings.compose_order_service}:{self.settings.container_telemetry_dir}/."
        self._compose("cp", source, str(destination))
        trace_id = self._latest_fault_trace(destination / "logs.jsonl")
        return DemoTelemetrySyncResult(trace_id=trace_id, telemetry_dir=destination)

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.api_url.rstrip("/"),
            timeout=self.settings.pool_timeout_seconds + 5,
            transport=self._http_transport,
        )

    def _compose(self, *arguments: str) -> None:
        docker = shutil.which("docker")
        if docker is None:
            raise DemoControlError("未找到 Docker CLI，请先安装并启动 Docker Desktop")

        compose_file = self.settings.compose_file.resolve()
        if not compose_file.is_file():
            raise DemoControlError(f"Compose 文件不存在：{compose_file}")

        command: Sequence[str] = (docker, "compose", "--file", str(compose_file), *arguments)
        try:
            result = self._command_runner(
                command,
                cwd=compose_file.parent,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self.settings.command_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise DemoControlError("Docker Compose 操作超时") from exc
        if result.returncode != 0:
            raise DemoControlError(f"Docker Compose 操作失败，退出码 {result.returncode}")

    def _latest_fault_trace(self, path: Path) -> str:
        if path.is_symlink() or not path.is_file():
            raise DemoControlError("同步结果缺少常规文件 logs.jsonl")
        if path.stat().st_size > self.settings.telemetry_sync_max_bytes:
            raise DemoControlError("同步日志超过 BUGCAPSULE_DEMO_TELEMETRY_SYNC_MAX_BYTES")

        latest: str | None = None
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise DemoControlError(f"同步日志不是有效 JSONL：第 {line_number} 行") from exc
                if not isinstance(record, dict):
                    raise DemoControlError(f"同步日志记录不是 JSON 对象：第 {line_number} 行")
                if record.get("fault") != "database_pool_exhausted":
                    continue
                candidate = record.get("trace_id")
                if (
                    not isinstance(candidate, str)
                    or re.fullmatch(r"[a-f0-9]{32}", candidate) is None
                ):
                    raise DemoControlError(f"池耗尽日志缺少有效 Trace ID：第 {line_number} 行")
                latest = candidate
        if latest is None:
            raise DemoControlError("同步日志中没有 database_pool_exhausted Trace")
        return latest

    @staticmethod
    def _require_status(response: httpx.Response, expected: int, action: str) -> None:
        if response.status_code != expected:
            raise DemoControlError(f"{action}失败，HTTP 状态码 {response.status_code}")
