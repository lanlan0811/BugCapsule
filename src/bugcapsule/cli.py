"""Command-line entry point for BugCapsule."""

from collections.abc import Callable
from typing import Annotated, Literal, cast

import typer
import uvicorn
from pydantic import ValidationError

from bugcapsule import __version__
from bugcapsule.analysis.service import AnalysisError, AnalysisService
from bugcapsule.capsule.capture import CaptureError, CaptureService
from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.config import Settings, get_settings
from bugcapsule.demo.config import DemoSettings
from bugcapsule.demo.controller import DemoControlError, DemoController, DemoRunResult
from bugcapsule.index import CapsuleIndex, CapsuleIndexError

app = typer.Typer(
    name="bugcapsule",
    help="以运行时证据为核心、能够验证修复结果的 AI 调试工具。",
    no_args_is_help=True,
)
demo_app = typer.Typer(help="管理可重复的数据库连接池故障演示。", no_args_is_help=True)
index_app = typer.Typer(help="重建本地胶囊元数据索引。", no_args_is_help=True)
capsules_app = typer.Typer(help="查询已索引的故障胶囊。", no_args_is_help=True)
app.add_typer(demo_app, name="demo")
app.add_typer(index_app, name="index")
app.add_typer(capsules_app, name="capsules")


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
    settings = get_settings()
    try:
        destination = CaptureService(settings).capture(trace_id)
        CapsuleIndex.from_settings(settings).upsert(destination)
    except (CaptureError, CapsuleIndexError) as exc:
        typer.echo(f"捕获失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(str(destination))


@app.command()
def analyze(
    capsule_id: str,
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="模型模式：live、replay 或 off；默认读取环境配置。"),
    ] = None,
) -> None:
    """用胶囊内已脱敏证据生成可追溯的根因候选。"""
    if mode not in {None, "live", "replay", "off"}:
        typer.echo("分析失败：未知模型模式", err=True)
        raise typer.Exit(code=1)
    try:
        selected_mode = cast(Literal["live", "replay", "off"] | None, mode)
        result = AnalysisService(get_settings()).analyze(capsule_id, mode=selected_mode)
    except AnalysisError as exc:
        typer.echo(f"分析失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(canonical_json(result.to_dict()).decode("utf-8"))


@index_app.command("rebuild")
def index_rebuild() -> None:
    """从胶囊目录完整重建 SQLite 元数据索引。"""
    try:
        result = CapsuleIndex.from_settings(get_settings()).rebuild()
    except CapsuleIndexError as exc:
        typer.echo(f"索引重建失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(canonical_json(result.to_dict()).decode("utf-8"))


@capsules_app.command("list")
def capsules_list(
    query: Annotated[
        str | None, typer.Option("--query", help="匹配 ID、服务、入口或 Trace ID。")
    ] = None,
    analysis_status: Annotated[
        str | None,
        typer.Option("--analysis-status", help="按分析状态精确筛选。"),
    ] = None,
    verification_status: Annotated[
        str | None,
        typer.Option("--verification-status", help="按验证状态精确筛选。"),
    ] = None,
    sort_by: Annotated[
        str,
        typer.Option("--sort", help="排序方式：time 或 status。"),
    ] = "time",
    limit: Annotated[int, typer.Option("--limit", min=1, max=500)] = 100,
) -> None:
    """以确定性 JSON 输出胶囊摘要。"""
    try:
        summaries = CapsuleIndex.from_settings(get_settings()).list_capsules(
            query=query,
            analysis_status=analysis_status,
            verification_status=verification_status,
            sort_by=sort_by,
            limit=limit,
        )
    except CapsuleIndexError as exc:
        typer.echo(f"胶囊查询失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(canonical_json([summary.to_dict() for summary in summaries]).decode("utf-8"))


@capsules_app.command("show")
def capsules_show(capsule_id: str) -> None:
    """显示胶囊清单、证据优先级和因果时间线。"""
    try:
        detail = CapsuleIndex.from_settings(get_settings()).get_detail(capsule_id)
    except CapsuleIndexError as exc:
        typer.echo(f"胶囊查询失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    if detail is None:
        typer.echo(f"胶囊不存在：{capsule_id}", err=True)
        raise typer.Exit(code=1)
    typer.echo(canonical_json(detail.to_dict()).decode("utf-8"))


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
