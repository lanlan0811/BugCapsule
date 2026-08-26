"""Deterministic, self-contained HTML verification reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from bugcapsule import __version__
from bugcapsule.capsule.identifiers import sha256_hex
from bugcapsule.config import Settings
from bugcapsule.index import CapsuleDetail, CapsuleIndex, CapsuleIndexError
from bugcapsule.verification.schema import VerificationArtifact
from bugcapsule.web.viewmodels import build_detail_view, format_bytes, format_datetime

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


class HtmlReportError(RuntimeError):
    """Raised when a report cannot be safely generated."""


class HtmlReportNotFoundError(HtmlReportError):
    """Raised when the requested capsule does not exist."""


class HtmlReportNotReadyError(HtmlReportError):
    """Raised when the debugging loop is not complete enough to report."""


@dataclass(frozen=True)
class HtmlReport:
    """Rendered report bytes and their deterministic delivery metadata."""

    capsule_id: str
    filename: str
    content: bytes
    sha256: str


class HtmlReportService:
    """Render authoritative capsule facts without external report dependencies."""

    def __init__(
        self,
        settings: Settings,
        *,
        index: CapsuleIndex | None = None,
        templates_dir: Path = TEMPLATES_DIR,
    ) -> None:
        self.settings = settings
        self.index = index or CapsuleIndex.from_settings(settings)
        self.environment = Environment(
            loader=FileSystemLoader(templates_dir),
            autoescape=select_autoescape(enabled_extensions=("html",)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.environment.filters["datetime"] = lambda value: format_datetime(
            value, self.settings.display_timezone
        )
        self.environment.filters["bytes"] = format_bytes

    def render(self, capsule_id: str) -> HtmlReport:
        """Render one immutable snapshot from a fully validated capsule detail."""
        try:
            detail = self.index.get_detail(capsule_id)
        except CapsuleIndexError as exc:
            raise HtmlReportError(str(exc)) from exc
        if detail is None:
            raise HtmlReportNotFoundError(f"胶囊不存在：{capsule_id}")
        verification = self._require_complete_loop(detail)

        context = build_detail_view(detail)
        rendered = self.environment.get_template("verification_report.html").render(
            version=__version__,
            report_completed_at=verification.completed_at,
            **context,
        )
        content = (rendered.rstrip() + "\n").encode("utf-8")
        return HtmlReport(
            capsule_id=capsule_id,
            filename=f"{capsule_id}-verification-report.html",
            content=content,
            sha256=sha256_hex(content),
        )

    @staticmethod
    def _require_complete_loop(detail: CapsuleDetail) -> VerificationArtifact:
        if detail.analysis is None:
            raise HtmlReportNotReadyError("HTML 报告需要已校验的模型分析结果")
        if detail.patch is None or detail.patch_diff is None:
            raise HtmlReportNotReadyError("HTML 报告需要已通过安全检查的 Patch")
        verification = detail.verification
        if (
            verification is None
            or verification.run.status not in {"passed", "failed"}
            or verification.run.before is None
            or verification.run.after is None
            or detail.verification_before_log is None
            or detail.verification_after_log is None
        ):
            raise HtmlReportNotReadyError("HTML 报告需要完整的修复前后验证结果")
        return verification
