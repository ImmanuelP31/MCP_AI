import time
from collections.abc import Generator
from typing import Any

from mcp_ops_common.config import Settings
from mcp_ops_observability.metrics import observe_database_latency
from sqlalchemy import URL, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def build_database_url(settings: Settings) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=settings.postgres_user,
        password=settings.postgres_password,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


def create_database_engine(
    settings: Settings,
    *,
    echo: bool = False,
    connect_timeout_seconds: int | None = None,
) -> Engine:
    connect_args = (
        {"connect_timeout": connect_timeout_seconds}
        if connect_timeout_seconds is not None
        else {}
    )
    engine = create_engine(
        build_database_url(settings),
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    _attach_database_latency_metrics(engine)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def session_scope(session_factory: sessionmaker[Session]) -> Generator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _attach_database_latency_metrics(engine: Engine) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        del conn, cursor, statement, parameters, executemany
        context._mcp_ops_query_started_at = time.perf_counter()

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        del conn, cursor, statement, parameters, executemany
        started_at = getattr(context, "_mcp_ops_query_started_at", None)
        if isinstance(started_at, int | float):
            observe_database_latency("sqlalchemy", time.perf_counter() - float(started_at))
