"""Build the competition project introduction PDF from repository facts."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 42
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN

PRIMARY_50 = HexColor("#eef4fb")
PRIMARY_100 = HexColor("#dbe7f6")
PRIMARY_300 = HexColor("#8ba9dd")
PRIMARY = HexColor("#2a52a0")
PRIMARY_700 = HexColor("#21417f")
PRIMARY_900 = HexColor("#15294a")
NEUTRAL_50 = HexColor("#f6f7f9")
NEUTRAL_100 = HexColor("#eceef2")
NEUTRAL_200 = HexColor("#d8dce3")
NEUTRAL_300 = HexColor("#b9bfca")
NEUTRAL_400 = HexColor("#8c93a3")
NEUTRAL_500 = HexColor("#6b7280")
NEUTRAL_700 = HexColor("#3a3f4b")
NEUTRAL_900 = HexColor("#15181e")
SUCCESS_50 = HexColor("#ecf9f1")
SUCCESS = HexColor("#1f7a3e")
WARNING_50 = HexColor("#fef8eb")
WARNING = HexColor("#95640a")
ERROR_50 = HexColor("#fdecec")
ERROR = HexColor("#9e2424")
INFO_50 = HexColor("#e8f6fb")
INFO = HexColor("#07607a")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "output" / "pdf" / "BugCapsule_0.1_项目介绍.pdf"


def _resolve_font(candidates: Sequence[Path]) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"No usable offline font found: {', '.join(map(str, candidates))}")


def register_fonts() -> None:
    """Register offline Chinese sans and technical monospace fonts."""

    sans = _resolve_font(
        (
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/Deng.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        )
    )
    sans_bold = _resolve_font(
        (
            Path("C:/Windows/Fonts/msyhbd.ttc"),
            Path("C:/Windows/Fonts/Dengb.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
        )
    )
    mono = _resolve_font(
        (
            Path("C:/Windows/Fonts/consola.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        )
    )
    mono_bold = _resolve_font(
        (
            Path("C:/Windows/Fonts/consolab.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
        )
    )
    pdfmetrics.registerFont(TTFont("BCSans", sans, subfontIndex=0))
    pdfmetrics.registerFont(TTFont("BCSans-Bold", sans_bold, subfontIndex=0))
    pdfmetrics.registerFont(TTFont("BCMono", mono))
    pdfmetrics.registerFont(TTFont("BCMono-Bold", mono_bold))
    pdfmetrics.registerFontFamily(
        "BCSans", normal="BCSans", bold="BCSans-Bold", italic="BCSans", boldItalic="BCSans-Bold"
    )
    pdfmetrics.registerFontFamily(
        "BCMono", normal="BCMono", bold="BCMono-Bold", italic="BCMono", boldItalic="BCMono-Bold"
    )


def draw_paragraph(
    canvas: Canvas,
    text: str,
    x: float,
    top: float,
    width: float,
    *,
    size: float = 10,
    leading: float | None = None,
    color: Color = NEUTRAL_700,
    font: str = "BCSans",
    align: int = TA_LEFT,
    max_height: float = PAGE_HEIGHT,
    space_after: float = 0,
) -> float:
    style = ParagraphStyle(
        name="inline",
        fontName=font,
        fontSize=size,
        leading=leading or size * 1.5,
        textColor=color,
        alignment=align,
        wordWrap="CJK",
        allowWidows=0,
        allowOrphans=0,
        spaceAfter=space_after,
    )
    paragraph = Paragraph(text, style)
    _, height = paragraph.wrap(width, max_height)
    paragraph.drawOn(canvas, x, top - height)
    return height


def draw_card(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    fill: Color = white,
    stroke: Color = NEUTRAL_200,
    radius: float = 6,
) -> None:
    canvas.saveState()
    canvas.setFillColor(fill)
    canvas.setStrokeColor(stroke)
    canvas.setLineWidth(0.8)
    canvas.roundRect(x, y, width, height, radius, fill=1, stroke=1)
    canvas.restoreState()


def draw_badge(
    canvas: Canvas,
    text: str,
    x: float,
    y: float,
    *,
    variant: str = "verified",
    width: float | None = None,
) -> float:
    calculated = max(52, pdfmetrics.stringWidth(text, "BCSans-Bold", 8) + 20)
    badge_width = width or calculated
    canvas.saveState()
    if variant == "verified":
        canvas.setFillColor(PRIMARY)
        canvas.setStrokeColor(PRIMARY)
        text_color = white
    elif variant == "partial":
        canvas.setFillColor(WARNING_50)
        canvas.setStrokeColor(WARNING)
        text_color = WARNING
    else:
        canvas.setFillColor(white)
        canvas.setStrokeColor(NEUTRAL_500)
        canvas.setDash(3, 2)
        text_color = NEUTRAL_700
    canvas.roundRect(x, y, badge_width, 18, 9, fill=1, stroke=1)
    canvas.setDash()
    canvas.setFont("BCSans-Bold", 8)
    canvas.setFillColor(text_color)
    canvas.drawCentredString(x + badge_width / 2, y + 5.1, text)
    canvas.restoreState()
    return badge_width


def draw_logo(canvas: Canvas, x: float, y: float, size: float, *, color: Color = PRIMARY) -> None:
    """Draw the capsule mark as an offline vector shape."""

    canvas.saveState()
    canvas.setStrokeColor(color)
    canvas.setLineWidth(max(1.2, size * 0.08))
    canvas.roundRect(x, y, size * 1.6, size * 0.78, size * 0.39, fill=0, stroke=1)
    canvas.line(x + size * 0.56, y + size * 0.06, x + size * 1.04, y + size * 0.72)
    canvas.restoreState()


def draw_arrow(canvas: Canvas, x1: float, y1: float, x2: float, y2: float) -> None:
    canvas.saveState()
    canvas.setStrokeColor(PRIMARY_300)
    canvas.setFillColor(PRIMARY_300)
    canvas.setLineWidth(1.2)
    canvas.line(x1, y1, x2, y2)
    direction = 1 if x2 >= x1 else -1
    canvas.line(x2, y2, x2 - direction * 6, y2 + 3)
    canvas.line(x2, y2, x2 - direction * 6, y2 - 3)
    canvas.restoreState()


def draw_page_header(canvas: Canvas, section: str, title: str, page: int) -> None:
    canvas.setFillColor(NEUTRAL_50)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    draw_logo(canvas, MARGIN, PAGE_HEIGHT - 53, 13)
    canvas.setFillColor(PRIMARY_900)
    canvas.setFont("BCSans-Bold", 9)
    canvas.drawString(MARGIN + 27, PAGE_HEIGHT - 47, "BugCapsule 0.1")
    canvas.setFillColor(NEUTRAL_500)
    canvas.setFont("BCMono", 7.5)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 47, section.upper())
    canvas.setStrokeColor(NEUTRAL_200)
    canvas.line(MARGIN, PAGE_HEIGHT - 62, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 62)
    draw_paragraph(
        canvas,
        title,
        MARGIN,
        PAGE_HEIGHT - 85,
        CONTENT_WIDTH,
        size=22,
        leading=27,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    canvas.setStrokeColor(PRIMARY)
    canvas.setLineWidth(2)
    canvas.line(MARGIN, PAGE_HEIGHT - 102, MARGIN + 42, PAGE_HEIGHT - 102)
    draw_footer(canvas, page)


def draw_footer(canvas: Canvas, page: int) -> None:
    canvas.saveState()
    canvas.setStrokeColor(NEUTRAL_200)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, 34, PAGE_WIDTH - MARGIN, 34)
    canvas.setFillColor(NEUTRAL_500)
    canvas.setFont("BCSans", 7.5)
    canvas.drawString(MARGIN, 21, "以运行时证据为核心、能够验证修复结果的 AI 调试工具")
    canvas.setFont("BCMono", 7.5)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 21, f"{page:02d} / 08")
    canvas.restoreState()


def draw_metric_card(
    canvas: Canvas,
    x: float,
    y: float,
    width: float,
    value: str,
    label: str,
    *,
    tone: Color = PRIMARY,
    value_size: float = 22,
) -> None:
    draw_card(canvas, x, y, width, 78)
    canvas.setFillColor(tone)
    canvas.rect(x, y, 3, 78, fill=1, stroke=0)
    draw_paragraph(
        canvas,
        value,
        x + 14,
        y + 62,
        width - 26,
        size=value_size,
        leading=value_size + 2,
        color=NEUTRAL_900,
        font="BCMono-Bold",
    )
    draw_paragraph(canvas, label, x + 14, y + 30, width - 26, size=8.5, color=NEUTRAL_500)


def page_cover(canvas: Canvas) -> None:
    canvas.setFillColor(NEUTRAL_50)
    canvas.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    canvas.setFillColor(PRIMARY_900)
    canvas.rect(0, PAGE_HEIGHT - 220, PAGE_WIDTH, 220, fill=1, stroke=0)
    draw_logo(canvas, MARGIN, PAGE_HEIGHT - 84, 26, color=white)
    canvas.setFillColor(white)
    canvas.setFont("BCSans-Bold", 13)
    canvas.drawString(MARGIN + 52, PAGE_HEIGHT - 68, "BugCapsule")
    canvas.setFillColor(PRIMARY_100)
    canvas.setFont("BCMono", 8)
    canvas.drawString(MARGIN + 52, PAGE_HEIGHT - 84, "OPEN EVIDENCE DEBUGGING")
    draw_paragraph(
        canvas,
        "以运行时证据为核心，<br/>能够验证修复结果的 AI 调试工具",
        MARGIN,
        PAGE_HEIGHT - 122,
        CONTENT_WIDTH,
        size=28,
        leading=36,
        color=white,
        font="BCSans-Bold",
    )
    draw_badge(canvas, "0.1.0 开发版", MARGIN, PAGE_HEIGHT - 203, variant="pending", width=86)
    canvas.setFillColor(PRIMARY_100)
    canvas.setFont("BCSans", 9)
    canvas.drawString(MARGIN + 101, PAGE_HEIGHT - 198, "上海开源软件应用创新大赛项目介绍")

    draw_paragraph(
        canvas,
        "把 Trace、日志、源码、Git、模型结论、Patch 与回归结果封装为一个可移植、"
        "可校验、默认脱敏的故障胶囊。模型提出建议，确定性代码约束证据与边界，"
        "人类批准后才进入隔离验证。",
        MARGIN,
        572,
        CONTENT_WIDTH,
        size=12,
        leading=20,
        color=NEUTRAL_700,
    )

    steps = ("故障注入", "证据捕获", "胶囊归档", "根因与 Patch", "人工确认", "隔离回归")
    step_width = (CONTENT_WIDTH - 5 * 10) / 6
    y = 443
    for index, step in enumerate(steps, start=1):
        x = MARGIN + (index - 1) * (step_width + 10)
        draw_card(canvas, x, y, step_width, 86, fill=white)
        canvas.setFillColor(PRIMARY_50)
        canvas.circle(x + 17, y + 66, 10, fill=1, stroke=0)
        canvas.setFillColor(PRIMARY)
        canvas.setFont("BCMono-Bold", 8)
        canvas.drawCentredString(x + 17, y + 63.2, f"{index:02d}")
        draw_paragraph(
            canvas,
            step,
            x + 8,
            y + 46,
            step_width - 16,
            size=9,
            leading=13,
            color=NEUTRAL_900,
            font="BCSans-Bold",
            align=TA_CENTER,
        )
        if index < len(steps):
            draw_arrow(canvas, x + step_width + 1, y + 43, x + step_width + 9, y + 43)

    draw_card(canvas, MARGIN, 280, CONTENT_WIDTH, 116, fill=PRIMARY_50, stroke=PRIMARY_100)
    draw_paragraph(
        canvas,
        "Trace → Code → Patch → Test",
        MARGIN + 20,
        371,
        CONTENT_WIDTH - 40,
        size=18,
        leading=22,
        color=PRIMARY_900,
        font="BCMono-Bold",
        align=TA_CENTER,
    )
    draw_paragraph(
        canvas,
        "每个结论可回溯，每个文件有 SHA-256，每个 Patch 受路径与证据约束，"
        "每次验证保留修复前后事实。",
        MARGIN + 30,
        333,
        CONTENT_WIDTH - 60,
        size=10,
        leading=16,
        color=PRIMARY_700,
        align=TA_CENTER,
    )

    canvas.setFillColor(NEUTRAL_500)
    canvas.setFont("BCSans", 8.5)
    canvas.drawString(MARGIN, 78, "主仓库")
    canvas.setFillColor(NEUTRAL_900)
    canvas.setFont("BCMono", 9)
    canvas.drawString(MARGIN, 59, "https://gitee.com/lan0811/bug-capsule")
    canvas.setFillColor(NEUTRAL_500)
    canvas.setFont("BCSans", 8.5)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 78, "文档快照")
    canvas.setFillColor(NEUTRAL_900)
    canvas.setFont("BCMono", 9)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 59, "2026-08-26")


def page_problem(canvas: Canvas) -> None:
    draw_page_header(canvas, "01 / Problem", "调试的真正缺口：结论无法形成可验证链路", 2)
    top = 710
    draw_paragraph(
        canvas,
        "现有工具能看到指标、日志或模型回答，但事故复盘常停在“可能是这里”。"
        "BugCapsule 把分散信息转成一个有边界、有引用、有批准、有回归的工程对象。",
        MARGIN,
        top,
        CONTENT_WIDTH,
        size=10.5,
        leading=17,
        color=NEUTRAL_700,
    )

    gap = 14
    card_width = (CONTENT_WIDTH - 2 * gap) / 3
    pain_points = (
        (
            "01",
            "证据分散",
            "Trace、日志、Stack Trace、源码和 Git 版本分属不同工具，复现时上下文已经丢失。",
            ERROR_50,
            ERROR,
        ),
        (
            "02",
            "结论难追溯",
            "模型可以给出流畅解释，但未知 Evidence ID、漏引证据和原始响应很难被程序拒绝。",
            WARNING_50,
            WARNING,
        ),
        (
            "03",
            "修复难信任",
            "生成 Diff 不等于修复成立；路径越界、确认后替换和只测修复后都会制造假阳性。",
            INFO_50,
            INFO,
        ),
    )
    y = 520
    for position, (index, title, body, fill, tone) in enumerate(pain_points):
        x = MARGIN + position * (card_width + gap)
        draw_card(canvas, x, y, card_width, 142, fill=white)
        canvas.setFillColor(fill)
        canvas.circle(x + 25, y + 112, 14, fill=1, stroke=0)
        canvas.setFillColor(tone)
        canvas.setFont("BCMono-Bold", 8)
        canvas.drawCentredString(x + 25, y + 109, index)
        draw_paragraph(
            canvas,
            title,
            x + 47,
            y + 124,
            card_width - 59,
            size=11,
            color=NEUTRAL_900,
            font="BCSans-Bold",
        )
        draw_paragraph(canvas, body, x + 14, y + 84, card_width - 28, size=8.8, leading=14)

    draw_card(canvas, MARGIN, 314, CONTENT_WIDTH, 164, fill=PRIMARY_900, stroke=PRIMARY_900)
    draw_paragraph(
        canvas,
        "BugCapsule 的回答",
        MARGIN + 20,
        452,
        160,
        size=12,
        color=white,
        font="BCSans-Bold",
    )
    responses = (
        ("事实源", ".bugcapsule 保存完整性清单与证据载荷"),
        ("引用约束", "根因与 Patch 只能引用本次输入中的 Evidence ID"),
        ("人工边界", "Patch ID + SHA-256 + 明确批准三重绑定"),
        ("验证事实", "before 失败、after 通过，输出再次脱敏并归档"),
    )
    response_width = (CONTENT_WIDTH - 40 - 3 * 10) / 4
    for index, (title, body) in enumerate(responses):
        x = MARGIN + 20 + index * (response_width + 10)
        draw_card(canvas, x, 335, response_width, 86, fill=PRIMARY_700, stroke=PRIMARY_300)
        draw_paragraph(
            canvas,
            title,
            x + 10,
            405,
            response_width - 20,
            size=9,
            color=white,
            font="BCSans-Bold",
        )
        draw_paragraph(
            canvas,
            body,
            x + 10,
            383,
            response_width - 20,
            size=7.8,
            leading=11.5,
            color=PRIMARY_100,
        )

    draw_paragraph(
        canvas,
        "设计原则",
        MARGIN,
        273,
        CONTENT_WIDTH,
        size=11,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    principles = (
        "证据优先",
        "状态以文字与形态表达",
        "离线可演示",
        "模型不直接修改主仓库",
    )
    principle_width = (CONTENT_WIDTH - 3 * 10) / 4
    for index, principle in enumerate(principles):
        x = MARGIN + index * (principle_width + 10)
        draw_card(canvas, x, 186, principle_width, 54, fill=white)
        canvas.setFillColor(PRIMARY)
        canvas.rect(x, 186, 3, 54, fill=1, stroke=0)
        draw_paragraph(
            canvas,
            principle,
            x + 12,
            220,
            principle_width - 24,
            size=8.6,
            leading=13,
            color=NEUTRAL_900,
            font="BCSans-Bold",
        )


def page_architecture(canvas: Canvas) -> None:
    draw_page_header(canvas, "02 / Architecture", "一个胶囊贯穿捕获、分析、确认与验证", 3)
    draw_paragraph(
        canvas,
        "SQLite 只保存可重建元数据；所有详情视图都会重新校验胶囊、重建证据链。"
        "CLI、Web 和 HTML 报告不各自维护事实副本。",
        MARGIN,
        708,
        CONTENT_WIDTH,
        size=10,
        leading=16,
    )

    nodes = (
        ("01", "故障注入", "FastAPI + PostgreSQL", ERROR_50, ERROR),
        ("02", "运行时证据", "Trace / Log / Source / Git", INFO_50, INFO),
        ("03", "故障胶囊", "Schema + SHA-256 + 脱敏", PRIMARY_50, PRIMARY),
        ("04", "证据链", "优先级 + 因果时间线", PRIMARY_50, PRIMARY),
        ("05", "模型分析", "live / replay / off", WARNING_50, WARNING),
        ("06", "Patch 安全", "Evidence-bound unified diff", WARNING_50, WARNING),
        ("07", "人工批准", "Patch ID + SHA-256 + approve", PRIMARY_50, PRIMARY),
        ("08", "隔离验证", "before / after restricted Docker", SUCCESS_50, SUCCESS),
        ("09", "同源输出", "CLI / Web / HTML report", SUCCESS_50, SUCCESS),
    )
    node_width = (CONTENT_WIDTH - 2 * 18) / 3
    node_height = 92
    start_y = 532
    for index, (number, title, body, fill, tone) in enumerate(nodes):
        row = index // 3
        column = index % 3
        if row % 2 == 1:
            column = 2 - column
        x = MARGIN + column * (node_width + 18)
        y = start_y - row * 130
        draw_card(canvas, x, y, node_width, node_height, fill=fill, stroke=tone)
        canvas.setFillColor(tone)
        canvas.setFont("BCMono-Bold", 8)
        canvas.drawString(x + 12, y + 70, number)
        draw_paragraph(
            canvas,
            title,
            x + 12,
            y + 60,
            node_width - 24,
            size=11,
            color=NEUTRAL_900,
            font="BCSans-Bold",
        )
        draw_paragraph(
            canvas,
            body,
            x + 12,
            y + 34,
            node_width - 24,
            size=7.8,
            leading=11,
            color=NEUTRAL_700,
            font="BCSans",
        )
        if index < len(nodes) - 1:
            next_row = (index + 1) // 3
            if next_row == row:
                direction = 1 if row % 2 == 0 else -1
                if direction == 1:
                    draw_arrow(canvas, x + node_width + 3, y + 46, x + node_width + 15, y + 46)
                else:
                    draw_arrow(canvas, x - 3, y + 46, x - 15, y + 46)
            else:
                edge_x = x + (node_width if row % 2 == 0 else 0)
                canvas.setStrokeColor(PRIMARY_300)
                canvas.setLineWidth(1.2)
                canvas.line(edge_x, y - 3, edge_x, y - 20)
                canvas.line(edge_x, y - 20, edge_x + (-6 if row % 2 == 0 else 6), y - 14)

    draw_card(canvas, MARGIN, 92, CONTENT_WIDTH, 104, fill=white)
    draw_paragraph(
        canvas,
        "信任边界",
        MARGIN + 16,
        174,
        90,
        size=10,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    boundary_text = (
        "胶囊内容视为不可信输入；模型输出视为候选；只有确定性 Schema、Evidence ID、"
        "路径与哈希校验后的结构化结果才能写回。验证器不挂载 Docker Socket、密钥或用户目录。"
    )
    draw_paragraph(
        canvas,
        boundary_text,
        MARGIN + 108,
        176,
        CONTENT_WIDTH - 124,
        size=8.7,
        leading=13,
    )
    draw_badge(canvas, "默认拒绝", MARGIN + 16, 110, variant="pending", width=70)


def page_scenario(canvas: Canvas) -> None:
    draw_page_header(canvas, "03 / Scenario", "主演示：数据库连接池耗尽，可复现、可重置", 4)
    draw_paragraph(
        canvas,
        "订单服务固定使用两个连接、零 overflow 和短超时。异常路径把 Session 留在"
        "请求注册表中；前两次请求占满连接，第三次请求稳定得到 503。",
        MARGIN,
        708,
        CONTENT_WIDTH,
        size=10,
        leading=16,
    )

    timeline_y = 570
    canvas.setStrokeColor(NEUTRAL_300)
    canvas.setLineWidth(1.2)
    canvas.line(MARGIN + 24, timeline_y + 40, PAGE_WIDTH - MARGIN - 24, timeline_y + 40)
    events = (
        ("POST 01", "500", "Session 被保留", ERROR),
        ("POST 02", "500", "第二连接被占用", ERROR),
        ("POST 03", "503", "pool exhausted", ERROR),
        ("RESET", "200", "池恢复 ready", SUCCESS),
    )
    event_width = (CONTENT_WIDTH - 3 * 18) / 4
    for index, (request, code, result, tone) in enumerate(events):
        x = MARGIN + index * (event_width + 18)
        canvas.setFillColor(white)
        canvas.setStrokeColor(tone)
        canvas.circle(x + event_width / 2, timeline_y + 40, 8, fill=1, stroke=1)
        draw_card(canvas, x, timeline_y - 62, event_width, 82, fill=white)
        draw_paragraph(
            canvas,
            request,
            x + 10,
            timeline_y,
            event_width - 20,
            size=8,
            color=NEUTRAL_500,
            font="BCMono-Bold",
            align=TA_CENTER,
        )
        draw_paragraph(
            canvas,
            code,
            x + 10,
            timeline_y - 20,
            event_width - 20,
            size=16,
            color=tone,
            font="BCMono-Bold",
            align=TA_CENTER,
        )
        draw_paragraph(
            canvas,
            result,
            x + 8,
            timeline_y - 43,
            event_width - 16,
            size=7.5,
            color=NEUTRAL_700,
            align=TA_CENTER,
        )

    left_width = 238
    draw_card(canvas, MARGIN, 290, left_width, 184, fill=white)
    draw_paragraph(
        canvas,
        "固定工程参数",
        MARGIN + 15,
        450,
        left_width - 30,
        size=11,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    facts = (
        ("pool_size", "2"),
        ("max_overflow", "0"),
        ("监听", "127.0.0.1"),
        ("容器", "non-root / read-only"),
        ("重置", "demo reset"),
    )
    row_y = 413
    for label, value in facts:
        canvas.setStrokeColor(NEUTRAL_200)
        canvas.line(MARGIN + 15, row_y - 7, MARGIN + left_width - 15, row_y - 7)
        canvas.setFillColor(NEUTRAL_500)
        canvas.setFont("BCSans", 8)
        canvas.drawString(MARGIN + 15, row_y, label)
        canvas.setFillColor(NEUTRAL_900)
        canvas.setFont("BCMono-Bold", 8)
        canvas.drawRightString(MARGIN + left_width - 15, row_y, value)
        row_y -= 28

    right_x = MARGIN + left_width + 16
    right_width = CONTENT_WIDTH - left_width - 16
    draw_card(canvas, right_x, 290, right_width, 184, fill=PRIMARY_50, stroke=PRIMARY_100)
    draw_paragraph(
        canvas,
        "仿真胶囊 BC-EVAL-001 的证据链",
        right_x + 15,
        450,
        right_width - 30,
        size=11,
        color=PRIMARY_900,
        font="BCSans-Bold",
    )
    evidence = (
        ("EV-54D6D74FFE11", "Trace", "POST /orders/leak 状态 ERROR"),
        ("EV-776F31252B0D", "Span", "SELECT orders 状态 ERROR"),
        ("EV-1C53B791D57C", "Log", "database pool exhausted"),
        ("EV-1AABEC87CBC0", "Source", "repository.py:45 Session 未关闭"),
    )
    row_y = 410
    for evidence_id, kind, summary in evidence:
        canvas.setFillColor(white)
        canvas.setStrokeColor(PRIMARY_100)
        canvas.roundRect(right_x + 15, row_y - 12, 103, 20, 3, fill=1, stroke=1)
        canvas.setFillColor(PRIMARY)
        canvas.setFont("BCMono-Bold", 6.6)
        canvas.drawCentredString(right_x + 66.5, row_y - 5, evidence_id)
        canvas.setFillColor(NEUTRAL_500)
        canvas.setFont("BCSans-Bold", 7.5)
        canvas.drawString(right_x + 127, row_y - 4, kind)
        draw_paragraph(canvas, summary, right_x + 161, row_y + 4, right_width - 176, size=7.2)
        row_y -= 32

    draw_card(canvas, MARGIN, 120, CONTENT_WIDTH, 120, fill=WARNING_50, stroke=WARNING)
    draw_badge(canvas, "部分验证", MARGIN + 16, 201, variant="partial", width=70)
    draw_paragraph(
        canvas,
        "单元测试与本机固定回归已验证状态序列；当前 Windows 开发机未安装 Docker CLI，"
        "因此 Compose 主场景和受限容器 20 次回归仍需在 GitHub Actions 或具备 Docker "
        "Engine 的环境完成。文档不把 CI 配置冒充实机结果。",
        MARGIN + 104,
        214,
        CONTENT_WIDTH - 120,
        size=8.6,
        leading=13,
        color=NEUTRAL_700,
    )


def page_model(canvas: Canvas) -> None:
    draw_page_header(
        canvas,
        "04 / Model Contract",
        "模型负责提出候选，确定性代码负责决定能否成立",
        5,
    )
    draw_paragraph(
        canvas,
        "BugCapsule 不发送整个仓库。模型输入只包含已脱敏、按优先级选择、受字节"
        "上限约束的证据；响应必须通过严格 Schema 和 Evidence ID 校验。",
        MARGIN,
        708,
        CONTENT_WIDTH,
        size=10,
        leading=16,
    )

    column_gap = 16
    column_width = (CONTENT_WIDTH - column_gap) / 2
    draw_card(canvas, MARGIN, 402, column_width, 240, fill=PRIMARY_50, stroke=PRIMARY_100)
    draw_paragraph(
        canvas,
        "模型看到什么",
        MARGIN + 16,
        619,
        column_width - 32,
        size=12,
        color=PRIMARY_900,
        font="BCSans-Bold",
    )
    model_inputs = (
        "已脱敏的排序证据，不含整个仓库",
        "固定系统指令与严格输出 Schema",
        "provider / model / API style 请求摘要",
        "胶囊内容被明确标记为不可信数据",
    )
    item_top = 580
    for index, item in enumerate(model_inputs, start=1):
        canvas.setFillColor(PRIMARY)
        canvas.circle(MARGIN + 25, item_top - 4, 8, fill=1, stroke=0)
        canvas.setFillColor(white)
        canvas.setFont("BCMono-Bold", 6.5)
        canvas.drawCentredString(MARGIN + 25, item_top - 6.3, str(index))
        draw_paragraph(canvas, item, MARGIN + 42, item_top + 4, column_width - 58, size=8.6)
        item_top -= 40
    draw_badge(canvas, "模型不能指定 Root Cause ID", MARGIN + 16, 421, variant="pending", width=154)

    right_x = MARGIN + column_width + column_gap
    draw_card(canvas, right_x, 402, column_width, 240, fill=white)
    draw_paragraph(
        canvas,
        "本地决定什么",
        right_x + 16,
        619,
        column_width - 32,
        size=12,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    local_rules = (
        ("结构", "连续排名、字段边界、重复候选"),
        ("引用", "每个 Evidence ID 必须存在于本次请求"),
        ("持久化", "只保存验证后的结构化结果"),
        ("失败", "无效响应只重试一次，随后解释性失败"),
    )
    item_top = 580
    for title, body in local_rules:
        canvas.setFillColor(NEUTRAL_900)
        canvas.setFont("BCSans-Bold", 8.4)
        canvas.drawString(right_x + 16, item_top - 3, title)
        draw_paragraph(canvas, body, right_x + 62, item_top + 4, column_width - 78, size=8.2)
        canvas.setStrokeColor(NEUTRAL_200)
        canvas.line(right_x + 16, item_top - 18, right_x + column_width - 16, item_top - 18)
        item_top -= 40
    draw_badge(canvas, "原始提示与响应不落盘", right_x + 16, 421, variant="verified", width=134)

    draw_paragraph(
        canvas,
        "三种显式模式",
        MARGIN,
        365,
        CONTENT_WIDTH,
        size=11,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    modes = (
        ("live", "调用配置的 OpenAI-compatible 提供方", "真实模型能力", "external"),
        ("replay", "按完整请求 SHA-256 读取录制结构", "离线管线复现", "verified"),
        ("off", "不访问模型、不读取回放", "纯确定性证据", "verified"),
    )
    mode_width = (CONTENT_WIDTH - 2 * 12) / 3
    for index, (name, behavior, meaning, status) in enumerate(modes):
        x = MARGIN + index * (mode_width + 12)
        draw_card(canvas, x, 236, mode_width, 100, fill=white)
        draw_paragraph(
            canvas,
            name,
            x + 12,
            319,
            mode_width - 24,
            size=12,
            color=PRIMARY,
            font="BCMono-Bold",
        )
        draw_paragraph(canvas, behavior, x + 12, 289, mode_width - 24, size=7.8, leading=11.5)
        draw_badge(
            canvas,
            meaning,
            x + 12,
            247,
            variant="pending" if status == "external" else "verified",
            width=mode_width - 24,
        )

    draw_card(canvas, MARGIN, 110, CONTENT_WIDTH, 84, fill=NEUTRAL_100, stroke=NEUTRAL_200)
    draw_paragraph(
        canvas,
        "诚实边界",
        MARGIN + 16,
        174,
        82,
        size=9.5,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    draw_paragraph(
        canvas,
        "注释 replay 的 100% 结果只证明完整分析链、引用校验和评分方法可复现；"
        "比赛采用的 Live 模型必须单独运行、单独报告，失败案例仍进入分母。",
        MARGIN + 104,
        177,
        CONTENT_WIDTH - 120,
        size=8.5,
        leading=13,
    )


def page_patch(canvas: Canvas) -> None:
    draw_page_header(canvas, "05 / Patch Safety", "Patch 先被约束，再被批准，最后才被验证", 6)
    draw_paragraph(
        canvas,
        "模型只提出 unified diff。Patch ID、Diff SHA-256、修改文件清单、安全结论和"
        "验证命令均由本地生成；模型不能覆盖测试、锁文件、CI 或 Docker 配置。",
        MARGIN,
        708,
        CONTENT_WIDTH,
        size=10,
        leading=16,
    )

    left_width = 292
    draw_card(canvas, MARGIN, 445, left_width, 196, fill=NEUTRAL_900, stroke=NEUTRAL_900)
    canvas.setFillColor(NEUTRAL_400)
    canvas.setFont("BCMono", 7)
    canvas.drawString(MARGIN + 14, 620, "verification_tests/fixtures/connection-release.diff")
    diff_lines = (
        ("@@ -42,7 +42,7 @@", NEUTRAL_400, False),
        ("  session.execute(statement)", white, False),
        ("- registry.retain(session)", HexColor("#f4a9a9"), True),
        ("+ session.close()", HexColor("#a6e1bb"), True),
        ("  return order", white, False),
    )
    y = 585
    for line, color, bold in diff_lines:
        canvas.setFillColor(color)
        canvas.setFont("BCMono-Bold" if bold else "BCMono", 8)
        canvas.drawString(MARGIN + 14, y, line)
        y -= 25
    draw_badge(canvas, "canonical unified diff", MARGIN + 14, 458, variant="pending", width=132)

    right_x = MARGIN + left_width + 16
    right_width = CONTENT_WIDTH - left_width - 16
    draw_card(canvas, right_x, 445, right_width, 196, fill=white)
    draw_paragraph(
        canvas,
        "批准前必须同时匹配",
        right_x + 16,
        618,
        right_width - 32,
        size=11,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    approvals = (
        ("01", "完整 Patch ID"),
        ("02", "完整 64 位 SHA-256"),
        ("03", "显式 approve=true"),
    )
    y = 574
    for number, label in approvals:
        canvas.setFillColor(PRIMARY_50)
        canvas.circle(right_x + 27, y + 3, 10, fill=1, stroke=0)
        canvas.setFillColor(PRIMARY)
        canvas.setFont("BCMono-Bold", 6.5)
        canvas.drawCentredString(right_x + 27, y, number)
        draw_paragraph(
            canvas,
            label,
            right_x + 46,
            y + 11,
            right_width - 62,
            size=8.8,
            color=NEUTRAL_900,
            font="BCSans-Bold",
        )
        y -= 40
    draw_badge(canvas, "任何不匹配：执行前拒绝", right_x + 16, 460, variant="verified", width=150)

    draw_paragraph(
        canvas,
        "受限验证容器",
        MARGIN,
        405,
        CONTENT_WIDTH,
        size=11,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    restrictions = (
        ("USER", "10001:10001"),
        ("NETWORK", "none"),
        ("ROOT FS", "read-only"),
        ("CAPS", "drop ALL"),
        ("SECURITY", "no-new-privileges"),
        ("LIMITS", "CPU / memory / PID / timeout"),
    )
    restriction_width = (CONTENT_WIDTH - 2 * 10) / 3
    for index, (label, value) in enumerate(restrictions):
        row = index // 3
        column = index % 3
        x = MARGIN + column * (restriction_width + 10)
        y = 302 - row * 74
        draw_card(canvas, x, y, restriction_width, 58, fill=white)
        canvas.setFillColor(NEUTRAL_500)
        canvas.setFont("BCMono-Bold", 6.8)
        canvas.drawString(x + 11, y + 38, label)
        draw_paragraph(
            canvas,
            value,
            x + 11,
            y + 29,
            restriction_width - 22,
            size=7.7,
            color=NEUTRAL_900,
            font="BCMono",
        )

    draw_card(canvas, MARGIN, 104, CONTENT_WIDTH, 84, fill=WARNING_50, stroke=WARNING)
    draw_badge(canvas, "CI 待实机", MARGIN + 16, 148, variant="partial", width=72)
    draw_paragraph(
        canvas,
        "工作流已配置修复前 20 次预期失败、应用固定 Patch 后 20 次预期通过；本机完成了"
        "固定回归逻辑检查，但因 Docker CLI 缺失，不把受限容器 20/20 配置写成已完成实测。",
        MARGIN + 106,
        166,
        CONTENT_WIDTH - 122,
        size=8.4,
        leading=12.5,
    )


def draw_latency_chart(canvas: Canvas, x: float, y: float, width: float, height: float) -> None:
    labels = ("确定性处理", "注释回放读取", "完整分析")
    p50 = (79.290, 0.751, 80.016)
    p95 = (109.752, 4.458, 110.323)
    max_value = 120.0
    chart_left = x + 88
    chart_width = width - 104
    for tick in (0, 30, 60, 90, 120):
        tick_x = chart_left + chart_width * tick / max_value
        canvas.setStrokeColor(NEUTRAL_200)
        canvas.setLineWidth(0.5)
        canvas.line(tick_x, y + 24, tick_x, y + height - 18)
        canvas.setFillColor(NEUTRAL_500)
        canvas.setFont("BCMono", 6)
        canvas.drawCentredString(tick_x, y + 12, str(tick))
    for index, label in enumerate(labels):
        row_y = y + height - 42 - index * 52
        canvas.setFillColor(NEUTRAL_700)
        canvas.setFont("BCSans", 7.5)
        canvas.drawRightString(chart_left - 9, row_y + 5, label)
        p95_width = chart_width * p95[index] / max_value
        p50_width = chart_width * p50[index] / max_value
        canvas.setFillColor(PRIMARY_100)
        canvas.roundRect(chart_left, row_y, p95_width, 13, 3, fill=1, stroke=0)
        canvas.setFillColor(PRIMARY)
        canvas.roundRect(chart_left, row_y, p50_width, 13, 3, fill=1, stroke=0)
        canvas.setFillColor(NEUTRAL_900)
        canvas.setFont("BCMono", 6.2)
        canvas.drawString(
            chart_left + p95_width + 5,
            row_y + 3,
            f"{p50[index]:.3f} / {p95[index]:.3f}",
        )
    legend_x = x + width - 120
    legend_y = y + height - 8
    canvas.setFillColor(PRIMARY)
    canvas.rect(legend_x, legend_y, 8, 4, fill=1, stroke=0)
    canvas.setFillColor(NEUTRAL_500)
    canvas.setFont("BCSans", 6.5)
    canvas.drawString(legend_x + 12, legend_y - 2, "P50")
    canvas.setFillColor(PRIMARY_100)
    canvas.rect(legend_x + 40, legend_y, 8, 4, fill=1, stroke=0)
    canvas.setFillColor(NEUTRAL_500)
    canvas.drawString(legend_x + 52, legend_y - 2, "P95 (毫秒)")


def page_metrics(canvas: Canvas) -> None:
    draw_page_header(
        canvas,
        "06 / Measured Evidence",
        "用可复现实测回答准确率、时延、质量与供应链",
        7,
    )
    draw_paragraph(
        canvas,
        "以下结果均绑定 2026-08-26 仓库快照。Replay 指标来自公开注释，只验证管线；"
        "性能为单机测量，不是服务等级承诺。",
        MARGIN,
        708,
        CONTENT_WIDTH,
        size=9.5,
        leading=15,
    )

    metric_width = (CONTENT_WIDTH - 2 * 12) / 3
    draw_metric_card(canvas, MARGIN, 548, metric_width, "100%", "Top-1 注释匹配率")
    draw_metric_card(
        canvas,
        MARGIN + metric_width + 12,
        548,
        metric_width,
        "100%",
        "Evidence 引用有效率",
        tone=INFO,
    )
    draw_metric_card(
        canvas,
        MARGIN + 2 * (metric_width + 12),
        548,
        metric_width,
        "100%",
        "必需 Trace / Log / Source 覆盖",
        tone=SUCCESS,
    )

    draw_card(canvas, MARGIN, 320, CONTENT_WIDTH, 190, fill=white)
    draw_paragraph(
        canvas,
        "12 案例分析时延 P50 / P95",
        MARGIN + 16,
        488,
        CONTENT_WIDTH - 32,
        size=10.5,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    draw_latency_chart(canvas, MARGIN + 8, 337, CONTENT_WIDTH - 16, 132)

    small_width = (CONTENT_WIDTH - 3 * 10) / 4
    quality_metrics = (
        ("154", "全量测试通过", PRIMARY),
        ("90.76%", "分支感知覆盖率", PRIMARY),
        ("3.10-3.12", "Python CI 矩阵", INFO),
        ("0", "已知漏洞 (审计 47 依赖)", SUCCESS),
    )
    for index, (value, label, tone) in enumerate(quality_metrics):
        draw_metric_card(
            canvas,
            MARGIN + index * (small_width + 10),
            205,
            small_width,
            value,
            label,
            tone=tone,
            value_size=13 if index == 2 else 22,
        )

    draw_card(canvas, MARGIN, 103, CONTENT_WIDTH, 72, fill=PRIMARY_50, stroke=PRIMARY_100)
    draw_paragraph(
        canvas,
        "供应链快照",
        MARGIN + 16,
        154,
        92,
        size=9.5,
        color=PRIMARY_900,
        font="BCSans-Bold",
    )
    draw_paragraph(
        canvas,
        "CycloneDX 1.6 SBOM：48 组件  |  pip-audit：47 生产依赖、0 已知漏洞  |  "
        "wheel + sdist + SHA256SUMS",
        MARGIN + 114,
        155,
        CONTENT_WIDTH - 130,
        size=8,
        color=PRIMARY_700,
        font="BCSans",
    )


def page_governance(canvas: Canvas) -> None:
    draw_page_header(
        canvas,
        "07 / Governance & Roadmap",
        "提交的是可持续验证的开源工程，而不是一次性演示",
        8,
    )
    draw_paragraph(
        canvas,
        "四项评分维度均有机器可读证据索引；权重合计 100%，每项声明绑定文件、"
        "复现命令和诚实状态。外部依赖未完成时保持开发版，不创建正式标签。",
        MARGIN,
        708,
        CONTENT_WIDTH,
        size=9.5,
        leading=15,
    )

    dimensions = (
        ("技术创新", "30%", "开放 Schema / Evidence ID / Patch 安全"),
        ("场景落地", "30%", "真实连接池故障 / CLI / Web / Report"),
        ("开源治理", "20%", "Apache-2.0 / SBOM / Threat Model"),
        ("长期发展", "20%", "适配接口 / 路线图 / 外部试用"),
    )
    dimension_width = (CONTENT_WIDTH - 3 * 10) / 4
    for index, (title, weight, body) in enumerate(dimensions):
        x = MARGIN + index * (dimension_width + 10)
        draw_card(canvas, x, 534, dimension_width, 112, fill=white)
        draw_paragraph(
            canvas,
            weight,
            x + 12,
            623,
            dimension_width - 24,
            size=17,
            color=PRIMARY,
            font="BCMono-Bold",
        )
        draw_paragraph(
            canvas,
            title,
            x + 12,
            587,
            dimension_width - 24,
            size=9.5,
            color=NEUTRAL_900,
            font="BCSans-Bold",
        )
        draw_paragraph(canvas, body, x + 12, 560, dimension_width - 24, size=7.2, leading=10.5)

    left_width = 250
    draw_card(canvas, MARGIN, 267, left_width, 226, fill=white)
    draw_paragraph(
        canvas,
        "已完成的开源基线",
        MARGIN + 16,
        470,
        left_width - 32,
        size=11,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    completed = (
        "Apache License 2.0 / NOTICE / Third Party",
        "中英文 README / Issue / PR / Security",
        "威胁模型与默认脱敏边界",
        "CycloneDX SBOM 与依赖审计",
        "示例胶囊与量化基准",
        "Gitee master 按功能提交",
    )
    item_top = 432
    for item in completed:
        canvas.setFillColor(SUCCESS)
        canvas.rect(MARGIN + 17, item_top - 6, 7, 7, fill=1, stroke=0)
        draw_paragraph(canvas, item, MARGIN + 34, item_top + 3, left_width - 50, size=7.8)
        item_top -= 29

    right_x = MARGIN + left_width + 16
    right_width = CONTENT_WIDTH - left_width - 16
    draw_card(canvas, right_x, 267, right_width, 226, fill=WARNING_50, stroke=WARNING)
    draw_paragraph(
        canvas,
        "正式 v0.1.0 前必须清零",
        right_x + 16,
        470,
        right_width - 126,
        size=11,
        color=NEUTRAL_900,
        font="BCSans-Bold",
    )
    draw_badge(
        canvas,
        "外部待完成",
        right_x + right_width - 98,
        450,
        variant="pending",
        width=82,
    )
    blockers = (
        ("01", "Docker Compose 主场景与受限 20/20 实机"),
        ("02", "比赛默认 Live 模型独立指标"),
        ("03", "3-5 名首次使用者匿名汇总"),
        ("04", "3-5 分钟视频与三分钟断网彩排"),
        ("05", "GitHub 镜像同步与双远端同一 Release"),
    )
    item_top = 430
    for number, item in blockers:
        canvas.setFillColor(WARNING)
        canvas.setFont("BCMono-Bold", 7)
        canvas.drawString(right_x + 16, item_top - 2, number)
        draw_paragraph(canvas, item, right_x + 42, item_top + 5, right_width - 58, size=8)
        item_top -= 34
    draw_card(canvas, MARGIN, 105, CONTENT_WIDTH, 122, fill=PRIMARY_900, stroke=PRIMARY_900)
    draw_paragraph(
        canvas,
        "评审入口",
        MARGIN + 18,
        204,
        90,
        size=11,
        color=white,
        font="BCSans-Bold",
    )
    draw_paragraph(
        canvas,
        "主仓库",
        MARGIN + 18,
        175,
        62,
        size=7.8,
        color=PRIMARY_100,
    )
    draw_paragraph(
        canvas,
        "https://gitee.com/lan0811/bug-capsule",
        MARGIN + 84,
        176,
        CONTENT_WIDTH - 102,
        size=8.5,
        color=white,
        font="BCMono",
    )
    draw_paragraph(
        canvas,
        "证据索引",
        MARGIN + 18,
        147,
        62,
        size=7.8,
        color=PRIMARY_100,
    )
    draw_paragraph(
        canvas,
        "docs/submission-evidence.md  |  examples/README.md  |  docs/supply-chain.md",
        MARGIN + 84,
        148,
        CONTENT_WIDTH - 102,
        size=7.5,
        color=white,
        font="BCMono",
    )


PAGES: tuple[Callable[[Canvas], None], ...] = (
    page_cover,
    page_problem,
    page_architecture,
    page_scenario,
    page_model,
    page_patch,
    page_metrics,
    page_governance,
)


def build_pdf(output_path: Path) -> Path:
    """Render the deterministic eight-page A4 project introduction."""

    register_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas = Canvas(
        str(output_path),
        pagesize=A4,
        pageCompression=1,
        invariant=1,
    )
    canvas.setTitle("BugCapsule 0.1 项目介绍")
    canvas.setAuthor("BugCapsule Contributors")
    canvas.setSubject("上海开源软件应用创新大赛项目提交材料")
    canvas.setCreator("BugCapsule deterministic ReportLab builder")
    for page in PAGES:
        page(canvas)
        canvas.showPage()
    canvas.save()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = build_pdf(arguments.output.resolve())
    print(output)


if __name__ == "__main__":
    main()
