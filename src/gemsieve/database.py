"""SQLite database connection and schema management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gemsieve.config import Config, load_config

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_db(config: Config | None = None, db_path: str | None = None) -> sqlite3.Connection:
    """Return a configured SQLite connection.

    Uses WAL mode and row_factory=sqlite3.Row for dict-like access.
    """
    if db_path is None:
        if config is None:
            config = load_config()
        db_path = config.storage.sqlite_path

    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables from schema.sql."""
    schema = _SCHEMA_PATH.read_text()
    conn.executescript(schema)


def reset_db(config: Config | None = None) -> sqlite3.Connection:
    """Drop and recreate the database. Returns a fresh connection."""
    if config is None:
        config = load_config()

    db_path = Path(config.storage.sqlite_path)
    if db_path.exists():
        db_path.unlink()

    conn = get_db(config)
    init_db(conn)
    return conn


def migrate_db(conn: sqlite3.Connection) -> list[str]:
    """Run schema migrations for columns that may be missing from older databases.

    Uses PRAGMA table_info to detect missing columns and ALTER TABLE to add them.
    Returns list of migration actions taken.
    """
    migrations: list[str] = []

    # Define expected columns per table: (table, column, type)
    expected_columns = [
        ("parsed_metadata", "x_mailer", "TEXT"),
        ("parsed_metadata", "mail_server", "TEXT"),
        ("parsed_metadata", "precedence", "TEXT"),
        ("parsed_metadata", "feedback_id", "TEXT"),
        ("parsed_metadata", "sender_subdomain", "TEXT"),
        ("sender_profiles", "thread_initiation_ratio", "REAL"),
        ("sender_profiles", "user_reply_rate", "REAL"),
    ]

    for table, column, col_type in expected_columns:
        existing = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing_names = {row["name"] for row in existing}
        if column not in existing_names:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            migrations.append(f"Added {table}.{column} ({col_type})")

    # Ensure new tables exist (for databases created before schema update)
    new_tables = [
        """CREATE TABLE IF NOT EXISTS domain_exclusions (
            domain TEXT PRIMARY KEY,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS sender_relationships (
            sender_domain TEXT PRIMARY KEY,
            relationship_type TEXT NOT NULL,
            relationship_note TEXT,
            suppress_gems BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source TEXT DEFAULT 'manual'
        )""",
    ]
    for ddl in new_tables:
        conn.execute(ddl)
        # Check if we actually created it (won't show in migrations if it existed)

    if migrations:
        conn.commit()

    return migrations


def db_stats(conn: sqlite3.Connection) -> dict[str, int]:
    """Return row counts for all tables."""
    tables = [
        "sync_state", "threads", "messages", "attachments",
        "parsed_metadata", "sender_temporal", "parsed_content",
        "extracted_entities", "ai_classification", "classification_overrides",
        "domain_exclusions", "sender_relationships",
        "sender_profiles", "gems", "sender_segments", "engagement_drafts",
        "pipeline_runs", "ai_audit_log",
    ]
    stats = {}
    for table in tables:
        try:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"]
        except sqlite3.OperationalError:
            stats[table] = -1  # table doesn't exist
    return stats
