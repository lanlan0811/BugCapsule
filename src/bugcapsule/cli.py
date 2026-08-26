"""Command-line entry point for BugCapsule."""

from typing import Annotated

import typer
import uvicorn

from bugcapsule import __version__
from bugcapsule.config import Settings, get_settings

app = typer.Typer(
    name="bugcapsule",
    help="以运行时证据为核心、能够验证修复结果的 AI 调试工具。",
    no_args_is_help=True,
)


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
