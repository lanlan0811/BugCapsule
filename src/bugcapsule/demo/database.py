"""Database engine and session lifecycle for the controlled fault scenario."""

from collections.abc import Iterator
from threading import Lock

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from sqlalchemy.orm import Session, sessionmaker

from bugcapsule.demo.config import DemoSettings


class InjectedRequestError(RuntimeError):
    """Expected exception raised after a connection has intentionally leaked."""


class LeakedSessionRegistry:
    """Retain intentionally leaked sessions until an explicit demo reset."""

    def __init__(self) -> None:
        self._sessions: list[Session] = []
        self._lock = Lock()

    @property
    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def retain(self, session: Session) -> None:
        with self._lock:
            self._sessions.append(session)

    def reset(self) -> int:
        with self._lock:
            sessions, self._sessions = self._sessions, []
        for session in sessions:
            session.close()
        return len(sessions)


def build_engine(settings: DemoSettings) -> Engine:
    """Create the deliberately constrained SQLAlchemy connection pool."""
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        pool_pre_ping=True,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create sessions with explicit transaction and expiry behavior."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Yield a session that is always released for normal requests."""
    with factory() as session:
        yield session


def execute_leaking_request(
    factory: sessionmaker[Session],
    registry: LeakedSessionRegistry,
) -> None:
    """Check out a connection, retain its session, then raise the injected failure."""
    session = factory()
    try:
        session.execute(text("SELECT 1"))
    except PoolTimeoutError:
        session.close()
        raise

    registry.retain(session)
    raise InjectedRequestError("injected failure retained a checked-out database session")
