"""HTTP integration tests for the server-rendered local Web interface."""

import asyncio
from pathlib import Path
from typing import Literal, cast

import httpx
from fastapi import FastAPI

from bugcapsule.app import create_app
from bugcapsule.config import Settings
from bugcapsule.demo.controller import DemoControlError, DemoController, DemoRunResult
from bugcapsule.index import CapsuleIndex
from tests.capsule.factories import make_stage_three_capsule


def make_web_app(
    tmp_path: Path,
    *,
    model_mode: Literal["live", "replay", "off"] = "off",
    max_import_bytes: int = 4096,
) -> tuple[FastAPI, CapsuleIndex]:
    data_dir = tmp_path / "data"
    settings = Settings(
        data_dir=data_dir,
        demo_telemetry_dir=data_dir / "demo",
        source_root=tmp_path,
        display_timezone="UTC",
        model_mode=model_mode,
        max_import_bytes=max_import_bytes,
    )
    index = CapsuleIndex(data_dir / "index.sqlite3", data_dir / "capsules")
    return create_app(settings, index), index


def test_capsule_list_and_htmx_fragment_use_local_assets_and_shared_facts(tmp_path: Path) -> None:
    application, index = make_web_app(tmp_path)
    make_stage_three_capsule(index.capsules_dir)

    async def request_pages() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            root = await client.get("/", follow_redirects=False)
            page = await client.get("/capsules")
            fragment = await client.get(
                "/capsules?query=demo-order-api",
                headers={"HX-Request": "true"},
            )
        return root, page, fragment

    root, page, fragment = asyncio.run(request_pages())

    assert root.status_code == 307
    assert root.headers["location"] == "/capsules"
    assert page.status_code == 200
    assert "cap_stage3_0001" in page.text
    assert "database_pool_exhausted" in page.text
    assert "https://" not in page.text
    assert "/static/vendor/htmx-2.0.10.min.js" in page.text
    assert "off · 未调用模型" in page.text
    assert fragment.status_code == 200
    assert "<html" not in fragment.text
    assert "cap_stage3_0001" in fragment.text
    assert 'hx-swap-oob="true"' in fragment.text


def test_capsule_detail_renders_evidence_and_downloads_exact_archive(tmp_path: Path) -> None:
    application, index = make_web_app(tmp_path, model_mode="replay")
    source, items = make_stage_three_capsule(index.capsules_dir)

    async def request_detail() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            detail = await client.get("/capsules/cap_stage3_0001")
            download = await client.get("/capsules/cap_stage3_0001/download")
            missing = await client.get("/capsules/cap_missing")
        return detail, download, missing

    detail, download, missing = asyncio.run(request_detail())

    assert detail.status_code == 200
    assert "replay · 回放" in detail.text
    assert "证据链时间线" in detail.text
    assert "src/bugcapsule/demo/database.py" in detail.text
    assert "session.execute(statement)" in detail.text
    assert all(item.evidence_id in detail.text for item in items)
    assert download.status_code == 200
    assert download.content == source.read_bytes()
    assert download.headers["content-type"].startswith("application/vnd.bugcapsule+zip")
    assert missing.status_code == 404
    assert "胶囊不存在" in missing.text


def test_capsule_import_validates_deduplicates_and_rejects_conflict(tmp_path: Path) -> None:
    application, index = make_web_app(tmp_path, max_import_bytes=1024 * 1024)
    first, _ = make_stage_three_capsule(tmp_path / "uploads" / "first")
    conflicting, _ = make_stage_three_capsule(
        tmp_path / "uploads" / "second",
        service_name="different-service",
    )

    async def upload_archives() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first_response = await client.post(
                "/capsules/import",
                files={"capsule": ("first.bugcapsule", first.read_bytes())},
                headers={"Origin": "http://testserver"},
                follow_redirects=False,
            )
            duplicate_response = await client.post(
                "/capsules/import",
                files={"capsule": ("first-again.bugcapsule", first.read_bytes())},
                headers={"HX-Request": "true", "Origin": "http://testserver"},
            )
            conflict_response = await client.post(
                "/capsules/import",
                files={"capsule": ("conflict.bugcapsule", conflicting.read_bytes())},
                headers={"Origin": "http://testserver"},
            )
        return first_response, duplicate_response, conflict_response

    first_response, duplicate_response, conflict_response = asyncio.run(upload_archives())

    destination = index.capsules_dir / "cap_stage3_0001.bugcapsule"
    assert first_response.status_code == 303
    assert first_response.headers["location"] == "/capsules/cap_stage3_0001"
    assert destination.read_bytes() == first.read_bytes()
    assert duplicate_response.status_code == 204
    assert duplicate_response.headers["hx-redirect"] == "/capsules/cap_stage3_0001"
    assert conflict_response.status_code == 400
    assert "未覆盖原文件" in conflict_response.text
    assert destination.read_bytes() == first.read_bytes()


def test_capsule_import_rejects_cross_site_invalid_and_oversized_uploads(tmp_path: Path) -> None:
    application, index = make_web_app(tmp_path, max_import_bytes=1024)

    async def upload_invalid_values() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            cross_site = await client.post(
                "/capsules/import",
                files={"capsule": ("bad.bugcapsule", b"bad")},
                headers={"Origin": "https://attacker.example"},
            )
            wrong_port = await client.post(
                "/capsules/import",
                files={"capsule": ("bad.bugcapsule", b"bad")},
                headers={"Origin": "http://testserver:9999"},
            )
            invalid = await client.post(
                "/capsules/import",
                files={"capsule": ("bad.bugcapsule", b"bad")},
                headers={"Origin": "http://testserver"},
            )
            oversized = await client.post(
                "/capsules/import",
                files={"capsule": ("large.bugcapsule", b"x" * 1025)},
                headers={"Origin": "http://testserver"},
            )
        assert wrong_port.status_code == 403
        return cross_site, invalid, oversized

    cross_site, invalid, oversized = asyncio.run(upload_invalid_values())

    assert cross_site.status_code == 403
    assert invalid.status_code == 400
    assert "胶囊校验失败" in invalid.text
    assert oversized.status_code == 400
    assert "大小上限" in oversized.text
    assert list(index.capsules_dir.glob(".upload-*.bugcapsule")) == []


def test_static_assets_are_packaged_and_untrusted_host_is_rejected(tmp_path: Path) -> None:
    application, _ = make_web_app(tmp_path)

    async def request_assets() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            css = await client.get("/static/app.css")
            htmx = await client.get("/static/vendor/htmx-2.0.10.min.js")
        async with httpx.AsyncClient(transport=transport, base_url="http://evil.example") as client:
            rejected = await client.get("/healthz")
        return css, htmx, rejected

    css, htmx, rejected = asyncio.run(request_assets())

    assert css.status_code == 200
    assert "--primary-600:#2a52a0" in css.text
    assert htmx.status_code == 200
    assert len(htmx.content) == 51238
    assert rejected.status_code == 400


def test_demo_controls_return_htmx_status_and_report_controller_errors(tmp_path: Path) -> None:
    class FakeDemoController:
        def __init__(self) -> None:
            self.fail = False
            self.actions: list[str] = []

        def run(self) -> DemoRunResult:
            self.actions.append("run")
            if self.fail:
                raise DemoControlError("Docker unavailable")
            return DemoRunResult(500, 500, 503, "database_pool_exhausted")

        def reset(self) -> dict[str, object]:
            self.actions.append("reset")
            return {"state": "ready"}

    _, index = make_web_app(tmp_path)
    settings = Settings(data_dir=tmp_path / "data", display_timezone="UTC")
    controller = FakeDemoController()
    application = create_app(settings, index, cast(DemoController, controller))

    async def request_controls() -> tuple[httpx.Response, ...]:
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            page = await client.get("/demo")
            run = await client.post("/demo/run", headers={"Origin": "http://testserver"})
            reset = await client.post("/demo/reset", headers={"Origin": "http://testserver"})
            rejected = await client.post(
                "/demo/reset",
                headers={"Origin": "https://attacker.example"},
            )
            controller.fail = True
            failed = await client.post("/demo/run", headers={"Origin": "http://testserver"})
        return page, run, reset, rejected, failed

    page, run, reset, rejected, failed = asyncio.run(request_controls())

    assert page.status_code == 200
    assert 'hx-post="/demo/run"' in page.text
    assert run.status_code == 200
    assert "500 → 500 → 503" in run.text
    assert reset.status_code == 200
    assert "连接池恢复为 ready" in reset.text
    assert rejected.status_code == 403
    assert failed.status_code == 503
    assert "Docker unavailable" in failed.text
    assert controller.actions == ["run", "reset", "run"]
