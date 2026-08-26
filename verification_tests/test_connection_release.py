"""This fixed-outcome regression fails before the leak fix and passes after it."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

from bugcapsule.demo.database import (
    InjectedRequestError,
    LeakedSessionRegistry,
    build_session_factory,
    execute_leaking_request,
)


def test_injected_failure_releases_checked_out_connection() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=0.01,
        connect_args={"check_same_thread": False},
    )
    registry = LeakedSessionRegistry()
    factory = build_session_factory(engine)

    for _ in range(3):
        with pytest.raises(InjectedRequestError):
            execute_leaking_request(factory, registry)
        assert registry.active_count == 0

    engine.dispose()
