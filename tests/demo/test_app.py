"""API tests for the controlled database pool fault scenario."""

import asyncio
from pathlib import Path

import httpx

from bugcapsule.demo.app import create_demo_app
from bugcapsule.demo.config import DemoSettings


def test_demo_api_reproduces_and_resets_pool_exhaustion(tmp_path: Path) -> None:
    database_path = (tmp_path / "demo.db").as_posix()
    settings = DemoSettings(
        database_url=f"sqlite+pysqlite:///{database_path}",
        pool_timeout_seconds=0.01,
    )
    application = create_demo_app(settings)

    async def run_scenario() -> None:
        transport = httpx.ASGITransport(app=application)
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                health = await client.get("/healthz")
                order = await client.post(
                    "/orders",
                    json={"product_sku": "SKU-001", "quantity": 2},
                )
                first_leak = await client.post("/demo/leak")
                second_leak = await client.post("/demo/leak")
                exhausted = await client.post("/demo/leak")
                exhausted_status = await client.get("/demo/status")
                reset = await client.post("/demo/reset")

        assert health.json() == {"status": "ok", "service": "demo-order-api"}
        assert order.status_code == 201
        assert order.json()["product_sku"] == "SKU-001"
        assert first_leak.status_code == 500
        assert second_leak.json()["detail"]["leaked_sessions"] == 2
        assert exhausted.status_code == 503
        assert exhausted.json()["detail"]["fault"] == "database_pool_exhausted"
        assert exhausted_status.json()["state"] == "exhausted"
        assert reset.json() == {
            "leaked_sessions": 0,
            "pool_size": 2,
            "max_overflow": 0,
            "state": "ready",
        }

    asyncio.run(run_scenario())
