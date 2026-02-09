"""Tests for subdomain collapsing and metadata stage integration."""

from __future__ import annotations

import json
import sqlite3

import pytest

from gemsieve.stages.metadata import collapse_subdomain


class TestCollapseSubdomain:
    """Test the collapse_subdomain function."""

    def test_simple_subdomain(self):
        assert collapse_subdomain("mail.example.com") == "example.com"

    def test_nested_subdomain(self):
        assert collapse_subdomain("mail.service.thehartford.com") == "thehartford.com"

    def test_notification_subdomain(self):
        assert collapse_subdomain("notification.intuit.com") == "intuit.com"

    def test_root_domain_unchanged(self):
        assert collapse_subdomain("example.com") == "example.com"

    def test_co_uk_tld(self):
        assert collapse_subdomain("mail.example.co.uk") == "example.co.uk"

    def test_empty_string(self):
        assert collapse_subdomain("") == ""

    def test_bare_tld(self):
        # Edge case: just a TLD with no registered domain
        result = collapse_subdomain("com")
        assert isinstance(result, str)

    def test_complex_subdomain(self):
        assert collapse_subdomain("bounce.email.marketing.stripe.com") == "stripe.com"


class TestMetadataSubdomainIntegration:
    """Test that metadata stage stores collapsed domain + original subdomain."""

    @pytest.fixture
    def db(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        from gemsieve.database import init_db
        init_db(conn)
        return conn

    def test_subdomain_collapsed_in_metadata(self, db):
        """When a message comes from a subdomain, sender_domain should be collapsed."""
        db.execute(
            "INSERT INTO threads (thread_id) VALUES ('thread1')"
        )
        db.execute(
            """INSERT INTO messages (message_id, thread_id, from_address, date, headers_raw)
               VALUES ('msg1', 'thread1', 'noreply@notification.intuit.com',
                       'Mon, 01 Jan 2024 12:00:00 +0000', '{}')"""
        )
        db.commit()

        from gemsieve.stages.metadata import extract_metadata
        count = extract_metadata(db)
        assert count == 1

        row = db.execute(
            "SELECT sender_domain, sender_subdomain FROM parsed_metadata WHERE message_id = 'msg1'"
        ).fetchone()
        assert row["sender_domain"] == "intuit.com"
        assert row["sender_subdomain"] == "notification.intuit.com"

    def test_root_domain_no_subdomain(self, db):
        """When sender is already a root domain, sender_subdomain should be NULL."""
        db.execute(
            "INSERT INTO threads (thread_id) VALUES ('thread2')"
        )
        db.execute(
            """INSERT INTO messages (message_id, thread_id, from_address, date, headers_raw)
               VALUES ('msg2', 'thread2', 'hello@example.com',
                       'Mon, 01 Jan 2024 12:00:00 +0000', '{}')"""
        )
        db.commit()

        from gemsieve.stages.metadata import extract_metadata
        count = extract_metadata(db)
        assert count == 1

        row = db.execute(
            "SELECT sender_domain, sender_subdomain FROM parsed_metadata WHERE message_id = 'msg2'"
        ).fetchone()
        assert row["sender_domain"] == "example.com"
        assert row["sender_subdomain"] is None


class TestMigration:
    """Test that migration adds the new columns."""

    def test_migrate_adds_new_columns(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")

        # Create tables WITHOUT the new columns (simulating old schema)
        conn.execute("""CREATE TABLE IF NOT EXISTS parsed_metadata (
            message_id TEXT PRIMARY KEY,
            sender_domain TEXT,
            envelope_sender TEXT,
            esp_identified TEXT,
            esp_confidence TEXT,
            dkim_domain TEXT,
            spf_result TEXT,
            dmarc_result TEXT,
            sending_ip TEXT,
            list_unsubscribe_url TEXT,
            list_unsubscribe_email TEXT,
            is_bulk BOOLEAN,
            x_mailer TEXT,
            mail_server TEXT,
            precedence TEXT,
            feedback_id TEXT,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS sender_profiles (
            sender_domain TEXT PRIMARY KEY,
            company_name TEXT,
            profiled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        # Create other needed tables for migrate_db to work
        conn.execute("""CREATE TABLE IF NOT EXISTS sender_temporal (
            sender_domain TEXT PRIMARY KEY
        )""")
        conn.commit()

        from gemsieve.database import migrate_db
        actions = migrate_db(conn)

        # Should have added sender_subdomain, thread_initiation_ratio, user_reply_rate
        action_text = " ".join(actions)
        assert "sender_subdomain" in action_text
        assert "thread_initiation_ratio" in action_text
        assert "user_reply_rate" in action_text

        # Verify sender_relationships table was created
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sender_relationships'"
        ).fetchall()
        assert len(tables) == 1

        conn.close()
