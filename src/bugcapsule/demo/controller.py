"""Safe orchestration for the local Docker demonstration."""

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

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

    @staticmethod
    def _require_status(response: httpx.Response, expected: int, action: str) -> None:
        if response.status_code != expected:
            raise DemoControlError(f"{action}失败，HTTP 状态码 {response.status_code}")
