"""SQLAlchemy engine and session factory for the web admin."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def _get_database_url() -> str:
    """Read DATABASE_URL from env, defaulting to SQLite."""
    return os.getenv("DATABASE_URL", "sqlite:///gemsieve.db")


def _make_engine(url: str | None = None):
    """Create a SQLAlchemy engine with appropriate settings."""
    url = url or _get_database_url()
    kwargs: dict = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    # Enable WAL and foreign keys for SQLite
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine)
