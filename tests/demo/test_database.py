"""Deterministic tests for the intentionally leaking request path."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.pool import QueuePool

from bugcapsule.demo.database import (
    InjectedRequestError,
    LeakedSessionRegistry,
    build_session_factory,
    execute_leaking_request,
)


def test_two_leaks_exhaust_pool_until_registry_reset() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.01,
        connect_args={"check_same_thread": False},
    )
    factory = build_session_factory(engine)
    registry = LeakedSessionRegistry()

    with pytest.raises(InjectedRequestError):
        execute_leaking_request(factory, registry)
    with pytest.raises(InjectedRequestError):
        execute_leaking_request(factory, registry)
    with pytest.raises(PoolTimeoutError):
        execute_leaking_request(factory, registry)

    assert registry.active_count == 2
    assert registry.reset() == 2
    assert registry.active_count == 0

    with pytest.raises(InjectedRequestError):
        execute_leaking_request(factory, registry)

    registry.reset()
    engine.dispose()
