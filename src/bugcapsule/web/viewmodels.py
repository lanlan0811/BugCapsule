"""Presentation-only transformations over authoritative capsule facts."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bugcapsule.capsule.schema import EvidenceItem, EvidenceKind
from bugcapsule.index import CapsuleDetail

KIND_LABELS = {
    EvidenceKind.TRACE: "请求 Trace",
    EvidenceKind.SPAN: "子 Span",
    EvidenceKind.LOG: "运行日志",
    EvidenceKind.STACKTRACE: "Stack Trace",
    EvidenceKind.SOURCE: "候选源码",
    EvidenceKind.GIT: "Git 上下文",
    EvidenceKind.ENVIRONMENT: "运行环境",
    EvidenceKind.TEST: "测试结果",
}
RELATION_LABELS = {
    "request_root": "请求根节点",
    "child_of": "父 Span",
    "observed_on": "关联 Span",
    "exception_from": "异常日志",
    "points_to": "指向 Stack Trace",
    "version_context": "版本上下文",
    "runtime_context": "运行上下文",
    "verifies": "验证证据",
    "context_for": "请求上下文",
}


def format_datetime(value: datetime, timezone_name: str) -> str:
    """Format an aware timestamp in the configured display timezone."""
    return value.astimezone(ZoneInfo(timezone_name)).strftime("%Y-%m-%d %H:%M:%S %Z")


def format_bytes(value: int) -> str:
    """Format an exact byte count without hiding the source value."""
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / (1024 * 1024):.1f} MiB"


def short_identifier(value: str, length: int = 8) -> str:
    """Collapse a long technical identifier for dense views."""
    return value if len(value) <= length else f"{value[:length]}…"


def evidence_title(item: EvidenceItem) -> str:
    """Select a concise title from captured content without inventing facts."""
    for key in ("name", "message", "fault", "path", "platform", "branch"):
        value = item.content.get(key)
        if isinstance(value, str) and value:
            return value
    if item.kind is EvidenceKind.STACKTRACE:
        stacktrace = item.content.get("stacktrace")
        if isinstance(stacktrace, str):
            lines = [line.strip() for line in stacktrace.splitlines() if line.strip()]
            if lines:
                return lines[-1]
    return item.source


def build_detail_view(detail: CapsuleDetail) -> dict[str, Any]:
    """Build the common Web view from the same facts serialized by CLI."""
    timeline = []
    for entry in detail.evidence.timeline:
        item = entry.evidence
        timeline.append(
            {
                "sequence": entry.sequence,
                "evidence": item,
                "kind_label": KIND_LABELS[item.kind],
                "title": evidence_title(item),
                "relation": entry.relation,
                "relation_label": RELATION_LABELS[entry.relation],
                "related_evidence_id": entry.related_evidence_id,
                "content_json": json.dumps(
                    item.content,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
                "is_error": (
                    item.content.get("level") in {"ERROR", "CRITICAL"}
                    or item.content.get("status") == "ERROR"
                ),
            }
        )

    logs = []
    for item in detail.evidence.items:
        if item.kind is not EvidenceKind.LOG:
            continue
        level = item.content.get("level")
        message = item.content.get("message")
        logs.append(
            {
                "evidence": item,
                "evidence_id": item.evidence_id,
                "captured_at": item.captured_at,
                "level": level if isinstance(level, str) else "INFO",
                "trace_id": item.trace_id or "—",
                "span_id": item.span_id or "—",
                "message": message if isinstance(message, str) else evidence_title(item),
            }
        )
    logs.sort(key=lambda row: (row["captured_at"], row["evidence_id"]))

    sources = []
    for item in detail.evidence.candidate_sources:
        raw_text = item.content.get("text")
        start_line = item.content.get("start_line")
        focus_line = item.content.get("line")
        first_line = start_line if isinstance(start_line, int) else 1
        lines = str(raw_text or "").splitlines()
        sources.append(
            {
                "evidence": item,
                "path": str(item.content.get("path") or item.source),
                "focus_line": focus_line if isinstance(focus_line, int) else None,
                "lines": [
                    {
                        "number": first_line + offset,
                        "text": line,
                        "is_focus": first_line + offset == focus_line,
                    }
                    for offset, line in enumerate(lines)
                ],
            }
        )

    return {
        "detail": detail,
        "timeline": timeline,
        "logs": logs,
        "sources": sources,
        "flow_steps": _flow_steps(detail),
    }


def _flow_steps(detail: CapsuleDetail) -> tuple[dict[str, str], ...]:
    analysis = detail.summary.analysis_status
    verification = detail.summary.verification_status
    return (
        {"label": "捕获", "state": "completed", "anchor": "summary", "note": "胶囊已校验"},
        {
            "label": "分析",
            "state": "completed" if analysis == "completed" else "current",
            "anchor": "analysis",
            "note": "已完成" if analysis == "completed" else "未调用模型",
        },
        {
            "label": "建议",
            "state": "completed" if detail.patch else "pending",
            "anchor": "patch",
            "note": "安全检查通过" if detail.patch else "未开始",
        },
        {"label": "确认", "state": "pending", "anchor": "patch", "note": "未开始"},
        {
            "label": "验证",
            "state": "completed" if verification == "passed" else "pending",
            "anchor": "verification",
            "note": "验证通过" if verification == "passed" else "未开始",
        },
    )
