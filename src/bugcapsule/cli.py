"""Command-line entry point for BugCapsule."""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, cast

import typer
import uvicorn
from pydantic import ValidationError

from bugcapsule import __version__
from bugcapsule.analysis.service import AnalysisError, AnalysisService
from bugcapsule.benchmarking.dataset import BenchmarkDatasetBuilder, BenchmarkDatasetError
from bugcapsule.benchmarking.evaluation import EvaluationError, EvaluationRunner
from bugcapsule.capsule.capture import CaptureError, CaptureService
from bugcapsule.capsule.identifiers import canonical_json
from bugcapsule.config import Settings, get_settings
from bugcapsule.demo.config import DemoSettings
from bugcapsule.demo.controller import DemoControlError, DemoController, DemoRunResult
from bugcapsule.diagnostics import DoctorService
from bugcapsule.index import CapsuleIndex, CapsuleIndexError
from bugcapsule.patching.service import PatchGenerationError, PatchGenerationService
from bugcapsule.reporting.service import HtmlReportError, HtmlReportService
from bugcapsule.verification.service import VerificationError, VerificationService

app = typer.Typer(
    name="bugcapsule",
    help="以运行时证据为核心、能够验证修复结果的 AI 调试工具。",
    no_args_is_help=True,
)
demo_app = typer.Typer(help="管理可重复的数据库连接池故障演示。", no_args_is_help=True)
index_app = typer.Typer(help="重建本地胶囊元数据索引。", no_args_is_help=True)
capsules_app = typer.Typer(help="查询已索引的故障胶囊。", no_args_is_help=True)
patch_app = typer.Typer(help="生成并检查证据约束的修复 Patch。", no_args_is_help=True)
benchmark_app = typer.Typer(help="构建并评测版本化仿真胶囊数据集。", no_args_is_help=True)
app.add_typer(demo_app, name="demo")
app.add_typer(index_app, name="index")
app.add_typer(capsules_app, name="capsules")
app.add_typer(patch_app, name="patch")
app.add_typer(benchmark_app, name="benchmark")


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
def doctor() -> None:
    """只读检查首次启动、主演示与隔离验证的本地前置条件。"""
    report = DoctorService(get_settings()).run()
    typer.echo(canonical_json(report.model_dump(mode="json")).decode("utf-8"))
    if not report.ready:
        raise typer.Exit(code=1)


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


@patch_app.command("generate")
def patch_generate(
    capsule_id: str,
    root_cause_id: Annotated[
        str | None,
        typer.Option("--root-cause-id", help="要修复的 Root Cause ID；默认选择排名第一项。"),
    ] = None,
    mode: Annotated[
        str | None,
        typer.Option("--mode", help="模型模式：live、replay 或 off；默认读取环境配置。"),
    ] = None,
) -> None:
    """生成 unified diff，并在写入胶囊前完成确定性安全校验。"""
    if mode not in {None, "live", "replay", "off"}:
        typer.echo("Patch 生成失败：未知模型模式", err=True)
        raise typer.Exit(code=1)
    selected_mode = cast(Literal["live", "replay", "off"] | None, mode)
    try:
        result = PatchGenerationService(get_settings()).generate(
            capsule_id,
            root_cause_id=root_cause_id,
            mode=selected_mode,
        )
    except PatchGenerationError as exc:
        typer.echo(f"Patch 生成失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(canonical_json(result.to_dict()).decode("utf-8"))


@app.command()
def verify(
    capsule_id: str,
    patch_id: Annotated[str, typer.Option("--patch-id", help="页面展示的完整 Patch ID。")],
    approved_sha256: Annotated[
        str,
        typer.Option("--approved-sha256", help="人工核对后的完整 Patch SHA-256。"),
    ],
    approve: Annotated[
        bool,
        typer.Option("--approve", help="明确批准在隔离临时副本中验证该 Patch。"),
    ] = False,
) -> None:
    """在受限 Docker 临时副本中运行修复前后回归。"""
    try:
        artifact = VerificationService(get_settings()).verify(
            capsule_id,
            patch_id=patch_id,
            approved_sha256=approved_sha256,
            explicitly_approved=approve,
        )
    except VerificationError as exc:
        typer.echo(f"验证失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(canonical_json(artifact.model_dump(mode="json")).decode("utf-8"))


@app.command()
def report(
    capsule_id: str,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="HTML 报告输出路径；默认写入当前目录。"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="允许覆盖已存在的报告文件。"),
    ] = False,
) -> None:
    """从胶囊内已校验事实生成自包含 HTML 前后对比报告。"""
    try:
        rendered = HtmlReportService(get_settings()).render(capsule_id)
        destination = (output or Path(rendered.filename)).resolve()
        if not destination.parent.is_dir():
            raise HtmlReportError(f"输出目录不存在：{destination.parent}")
        if destination.exists() and not force:
            raise HtmlReportError(f"输出文件已存在：{destination}")
        destination.write_bytes(rendered.content)
    except (HtmlReportError, OSError) as exc:
        typer.echo(f"报告生成失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"报告已写入：{destination}")
    typer.echo(f"SHA-256：{rendered.sha256}")


@benchmark_app.command("build")
def benchmark_build(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="写入 annotations.json 与 capsules/ 的目录。"),
    ],
    force: Annotated[
        bool,
        typer.Option("--force", help="显式覆盖已存在的同名基准文件。"),
    ] = False,
) -> None:
    """确定性生成 12 个带人工标注的仿真故障胶囊。"""
    try:
        result = BenchmarkDatasetBuilder().build(output, overwrite=force)
    except (BenchmarkDatasetError, OSError) as exc:
        typer.echo(f"基准数据集构建失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(canonical_json(result.to_dict()).decode("utf-8"))


@benchmark_app.command("run")
def benchmark_run(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="写入胶囊与 evaluation.json 的目录。"),
    ],
    mode: Annotated[
        str,
        typer.Option("--mode", help="评测模式：replay 或 live。"),
    ] = "replay",
    force: Annotated[
        bool,
        typer.Option("--force", help="显式覆盖已存在的同名基准文件。"),
    ] = False,
) -> None:
    """实测 12 个案例的准确率、引用有效率与 P50/P95。"""
    if mode not in {"live", "replay"}:
        typer.echo("基准评测失败：未知评测模式", err=True)
        raise typer.Exit(code=1)
    selected_mode = cast(Literal["live", "replay"], mode)
    try:
        report = EvaluationRunner(get_settings()).run(
            output,
            mode=selected_mode,
            overwrite=force,
        )
    except (BenchmarkDatasetError, EvaluationError, OSError) as exc:
        typer.echo(f"基准评测失败：{exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(canonical_json(report.model_dump(mode="json")).decode("utf-8"))


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
