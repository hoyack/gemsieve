"""Tests for database module."""

import sqlite3

from gemsieve.database import db_stats, init_db, migrate_db


def test_init_db_creates_all_tables(db):
    """Schema creates all 14 expected tables."""
    stats = db_stats(db)
    expected_tables = [
        "sync_state", "threads", "messages", "attachments",
        "parsed_metadata", "sender_temporal", "parsed_content",
        "extracted_entities", "ai_classification", "classification_overrides",
        "sender_profiles", "gems", "sender_segments", "engagement_drafts",
    ]
    for table in expected_tables:
        assert table in stats, f"Missing table: {table}"
        assert stats[table] >= 0, f"Table {table} not created properly"


def test_db_stats_empty(db):
    """All tables start with 0 rows."""
    stats = db_stats(db)
    for table, count in stats.items():
        assert count == 0, f"Table {table} should be empty, has {count} rows"


def test_insert_and_query_message(db):
    """Can insert and query a message."""
    db.execute(
        "INSERT INTO threads (thread_id, subject) VALUES ('t1', 'Test')"
    )
    db.execute(
        """INSERT INTO messages (message_id, thread_id, subject, from_address)
           VALUES ('m1', 't1', 'Test', 'test@example.com')"""
    )
    db.commit()

    row = db.execute("SELECT * FROM messages WHERE message_id = 'm1'").fetchone()
    assert row is not None
    assert row["from_address"] == "test@example.com"
    assert row["subject"] == "Test"


def test_foreign_key_thread(db):
    """Messages reference threads via foreign key."""
    db.execute(
        "INSERT INTO threads (thread_id, subject) VALUES ('t1', 'Test')"
    )
    db.execute(
        """INSERT INTO messages (message_id, thread_id, subject)
           VALUES ('m1', 't1', 'Test')"""
    )
    db.commit()

    stats = db_stats(db)
    assert stats["threads"] == 1
    assert stats["messages"] == 1


def test_migrate_db_adds_missing_columns():
    """migrate_db() adds missing columns to a pre-existing schema."""
    # Create a DB with the old schema (no x_mailer, mail_server, etc.)
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(
        """CREATE TABLE parsed_metadata (
            message_id TEXT PRIMARY KEY,
            sender_domain TEXT,
            is_bulk BOOLEAN
        )"""
    )
    conn.commit()

    actions = migrate_db(conn)

    assert len(actions) == 4
    assert any("x_mailer" in a for a in actions)
    assert any("mail_server" in a for a in actions)
    assert any("precedence" in a for a in actions)
    assert any("feedback_id" in a for a in actions)

    # Verify columns actually exist
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(parsed_metadata)").fetchall()}
    assert "x_mailer" in cols
    assert "mail_server" in cols
    assert "precedence" in cols
    assert "feedback_id" in cols
    conn.close()


def test_migrate_db_noop_on_fresh_schema(db):
    """migrate_db() does nothing on a fresh schema that already has all columns."""
    actions = migrate_db(db)
    assert len(actions) == 0
