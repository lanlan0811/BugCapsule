"""Tests for the local FastAPI application."""

import asyncio

import httpx

from bugcapsule import __version__
from bugcapsule.app import create_app


def test_healthcheck_reports_version() -> None:
    async def request_healthcheck() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/healthz")

    response = asyncio.run(request_healthcheck())

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}
