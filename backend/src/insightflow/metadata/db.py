"""Metadata database engine and session helpers (SQLite locally, PostgreSQL later)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from insightflow.metadata.models import Base


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn: Any, _record: Any) -> None:
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")  # SQLite ignores FKs unless asked
            cur.execute("PRAGMA journal_mode=WAL")  # readers don't block the pipeline writer
            cur.execute("PRAGMA busy_timeout=5000")  # wait instead of 'database is locked'
            cur.close()

        return engine
    return create_engine(url, pool_pre_ping=True)


def create_schema(engine: Engine) -> None:
    """Create tables directly from models (tests only; real databases use migrations)."""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """One unit of work: commit on success, roll back on any error."""
    session = Session(engine, expire_on_commit=False)
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
