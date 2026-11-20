"""Engine/session helpers tuned for SQLite (WAL, single file, no server)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def _sqlite_pragmas(dbapi_connection: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
    except sqlite3.DatabaseError:
        # in-memory databases do not support WAL - safe to ignore
        pass
    finally:
        cursor.close()


def make_engine(db_url: str) -> Engine:
    is_sqlite = db_url.startswith("sqlite")
    in_memory = db_url in {"sqlite://", "sqlite:///:memory:"} or ":memory:" in db_url

    if is_sqlite and not in_memory:
        path = db_url.split("///", 1)[-1]
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)

    kwargs: dict[str, object] = {}
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
    if in_memory:
        kwargs["poolclass"] = StaticPool

    engine = create_engine(db_url, **kwargs)
    if is_sqlite:
        event.listen(engine, "connect", _sqlite_pragmas)
    return engine


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    # expire_on_commit=False keeps loaded attributes readable after the block
    with Session(engine, expire_on_commit=False) as session:
        yield session
        session.commit()
