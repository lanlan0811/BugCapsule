"""FastAPI application for the deterministic database pool fault scenario."""

import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session

from bugcapsule import __version__
from bugcapsule.demo.config import DemoSettings
from bugcapsule.demo.database import (
    InjectedRequestError,
    LeakedSessionRegistry,
    build_engine,
    build_session_factory,
    execute_leaking_request,
    session_scope,
)
from bugcapsule.demo.models import Base, Order
from bugcapsule.demo.observability import ObservabilityRuntime, configure_observability
from bugcapsule.demo.schemas import DemoStatus, OrderCreate, OrderRead


def create_demo_app(settings: DemoSettings) -> FastAPI:
    """Build an isolated demo application from validated settings."""
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    registry = LeakedSessionRegistry()
    runtime: ObservabilityRuntime | None = None
    logger = logging.getLogger("bugcapsule.demo")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        try:
            yield
        finally:
            registry.reset()
            engine.dispose()
            if runtime is not None:
                runtime.shutdown()

    application = FastAPI(
        title="BugCapsule Demo Order Service",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    def get_session() -> Iterator[Session]:
        yield from session_scope(factory)

    @application.get("/healthz", tags=["system"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "service": "demo-order-api"}

    @application.post(
        "/orders",
        response_model=OrderRead,
        status_code=status.HTTP_201_CREATED,
        tags=["orders"],
    )
    def create_order(
        payload: OrderCreate,
        session: Annotated[Session, Depends(get_session)],
    ) -> Order:
        order = Order(product_sku=payload.product_sku, quantity=payload.quantity)
        session.add(order)
        session.commit()
        session.refresh(order)
        logger.info("order created", extra={"order_id": order.id})
        return order

    @application.post("/demo/leak", status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    def inject_connection_leak() -> None:
        try:
            execute_leaking_request(factory, registry)
        except InjectedRequestError as exc:
            logger.exception(
                "injected database request failure",
                extra={
                    "fault": "injected_request_failure",
                    "leaked_sessions": registry.active_count,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "fault": "injected_request_failure",
                    "leaked_sessions": registry.active_count,
                },
            ) from exc
        except PoolTimeoutError as exc:
            logger.exception(
                "database connection pool exhausted",
                extra={
                    "fault": "database_pool_exhausted",
                    "leaked_sessions": registry.active_count,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "fault": "database_pool_exhausted",
                    "leaked_sessions": registry.active_count,
                },
            ) from exc

    @application.get("/demo/status", response_model=DemoStatus, tags=["demo"])
    def get_demo_status() -> DemoStatus:
        leaked = registry.active_count
        exhausted = leaked >= settings.pool_size + settings.max_overflow
        return DemoStatus(
            leaked_sessions=leaked,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            state="exhausted" if exhausted else "ready",
        )

    @application.post("/demo/reset", response_model=DemoStatus, tags=["demo"])
    def reset_demo() -> DemoStatus:
        registry.reset()
        return DemoStatus(
            leaked_sessions=0,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            state="ready",
        )

    if settings.telemetry_enabled:
        runtime = configure_observability(application, engine, settings)
    return application
