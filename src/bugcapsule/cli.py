"""Command-line entry point for BugCapsule."""

from collections.abc import Callable
from typing import Annotated

import typer
import uvicorn
from pydantic import ValidationError

from bugcapsule import __version__
from bugcapsule.capsule.capture import CaptureError, CaptureService
from bugcapsule.config import Settings, get_settings
from bugcapsule.demo.config import DemoSettings
from bugcapsule.demo.controller import DemoControlError, DemoController, DemoRunResult

app = typer.Typer(
    name="bugcapsule",
    help="以运行时证据为核心、能够验证修复结果的 AI 调试工具。",
    no_args_is_help=True,
)
demo_app = typer.Typer(help="管理可重复的数据库连接池故障演示。", no_args_is_help=True)
app.add_typer(demo_app, name="demo")


def version_callback(value: bool) -> None:
    """Print the package version and exit."""
    if value:
        typer.echo(f"BugCapsule {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=version_callback, is_eager=True, help="显示版本。"),
    ] = None,
) -> None:
    """BugCapsule 命令行入口。"""


@app.command()
def serve() -> None:
    """启动仅监听本机的 Web 与 API 服务。"""
    settings: Settings = get_settings()
    uvicorn.run(
        "bugcapsule.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


@app.command()
def capture(
    trace_id: Annotated[str, typer.Option("--trace-id", help="32 位小写十六进制 Trace ID。")],
) -> None:
    """从本地运行时证据生成已脱敏且可校验的故障胶囊。"""
    try:
        destination = CaptureService(get_settings()).capture(trace_id)
    except CaptureError as exc:
        typer.echo(f"捕获失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(destination))


def get_demo_controller() -> DemoController:
    """Build the environment-configured demo controller."""
    return DemoController(DemoSettings())


def run_demo_action(action: Callable[[DemoController], object]) -> object:
    """Run a demo action with concise user-facing failure output."""
    try:
        return action(get_demo_controller())
    except (DemoControlError, ValidationError) as exc:
        typer.echo(f"演示操作失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc


@demo_app.command("up")
def demo_up() -> None:
    """构建并启动 PostgreSQL 与订单服务。"""
    run_demo_action(lambda controller: controller.up())
    typer.echo("演示环境已启动。")


@demo_app.command("run")
def demo_run() -> None:
    """重置环境并稳定触发数据库连接池耗尽。"""
    result = run_demo_action(lambda controller: controller.run())
    if not isinstance(result, DemoRunResult):
        raise typer.Exit(code=1)
    typer.echo(
        "故障复现成功："
        f"HTTP {result.first_status} → {result.second_status} → {result.exhausted_status}；"
        f"{result.fault}"
    )


@demo_app.command("reset")
def demo_reset() -> None:
    """释放泄漏 Session 并恢复连接池。"""
    run_demo_action(lambda controller: controller.reset())
    typer.echo("演示状态已重置。")


@demo_app.command("down")
def demo_down() -> None:
    """停止演示容器并保留数据库卷。"""
    run_demo_action(lambda controller: controller.down())
    typer.echo("演示环境已停止。")
