"""Tests for thread metrics computation in profile stage."""

from __future__ import annotations

import sqlite3

import pytest

from gemsieve.database import init_db
from gemsieve.stages.profile import _compute_thread_metrics, build_profiles


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def _insert_thread(db, thread_id, user_participated=False):
    db.execute(
        "INSERT INTO threads (thread_id, user_participated) VALUES (?, ?)",
        (thread_id, user_participated),
    )


def _insert_message(db, msg_id, thread_id, from_addr, date, is_sent=False):
    db.execute(
        """INSERT INTO messages (message_id, thread_id, from_address, date, is_sent)
           VALUES (?, ?, ?, ?, ?)""",
        (msg_id, thread_id, from_addr, date, is_sent),
    )
    # Also insert parsed_metadata for domain linkage
    domain = from_addr.split("@")[1] if "@" in from_addr else ""
    db.execute(
        "INSERT OR IGNORE INTO parsed_metadata (message_id, sender_domain) VALUES (?, ?)",
        (msg_id, domain),
    )


class TestComputeThreadMetrics:
    def test_user_initiated_threads(self, db):
        """When the user sent the first message, initiation_ratio should be 1.0."""
        _insert_thread(db, "t1", user_participated=True)
        _insert_message(db, "m1", "t1", "me@mycompany.com", "2024-01-01T10:00:00Z", is_sent=True)
        _insert_message(db, "m2", "t1", "them@vendor.com", "2024-01-01T11:00:00Z", is_sent=False)
        db.commit()

        ratio, reply_rate = _compute_thread_metrics(db, "vendor.com")
        assert ratio == 1.0  # user initiated
        assert reply_rate == 1.0  # user participated

    def test_they_initiated_threads(self, db):
        """When they sent the first message, initiation_ratio should be 0.0."""
        _insert_thread(db, "t1", user_participated=True)
        _insert_message(db, "m1", "t1", "them@prospect.com", "2024-01-01T10:00:00Z", is_sent=False)
        _insert_message(db, "m2", "t1", "me@mycompany.com", "2024-01-01T11:00:00Z", is_sent=True)
        db.commit()

        ratio, reply_rate = _compute_thread_metrics(db, "prospect.com")
        assert ratio == 0.0  # they initiated
        assert reply_rate == 1.0  # user participated

    def test_mixed_initiation(self, db):
        """Mixed: one user-initiated, one they-initiated."""
        _insert_thread(db, "t1", user_participated=True)
        _insert_message(db, "m1", "t1", "me@mycompany.com", "2024-01-01T10:00:00Z", is_sent=True)
        _insert_message(db, "m2", "t1", "them@company.com", "2024-01-01T11:00:00Z", is_sent=False)

        _insert_thread(db, "t2", user_participated=False)
        _insert_message(db, "m3", "t2", "them@company.com", "2024-01-02T10:00:00Z", is_sent=False)
        db.commit()

        ratio, reply_rate = _compute_thread_metrics(db, "company.com")
        assert ratio == 0.5  # 1 of 2 threads user-initiated
        assert reply_rate == 0.5  # 1 of 2 threads user participated

    def test_no_threads_returns_none(self, db):
        """No threads for domain returns None, None."""
        ratio, reply_rate = _compute_thread_metrics(db, "unknown.com")
        assert ratio is None
        assert reply_rate is None

    def test_profile_stores_metrics(self, db):
        """build_profiles() stores thread metrics in sender_profiles."""
        _insert_thread(db, "t1", user_participated=True)
        _insert_message(db, "m1", "t1", "them@example.com", "Mon, 01 Jan 2024 12:00:00 +0000", is_sent=False)
        _insert_message(db, "m2", "t1", "me@mycompany.com", "Mon, 01 Jan 2024 13:00:00 +0000", is_sent=True)
        db.commit()

        build_profiles(db)

        profile = db.execute(
            "SELECT thread_initiation_ratio, user_reply_rate FROM sender_profiles WHERE sender_domain = 'example.com'"
        ).fetchone()
        assert profile is not None
        assert profile["thread_initiation_ratio"] == 0.0  # they initiated
        assert profile["user_reply_rate"] == 1.0  # user participated
