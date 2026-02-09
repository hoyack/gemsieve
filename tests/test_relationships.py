"""Tests for relationship detection engine."""

from __future__ import annotations

import json
import sqlite3
import tempfile

import pytest
import yaml

from gemsieve.database import init_db
from gemsieve.stages.relationships import (
    _classify_relationship,
    detect_relationships,
    import_relationships,
    list_relationships,
    scan_completion_signals,
    set_relationship,
)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def _insert_profile(db, domain, **kwargs):
    """Helper to insert a sender profile with defaults."""
    defaults = {
        "company_name": domain.split(".")[0].title(),
        "primary_email": f"info@{domain}",
        "total_messages": 5,
        "industry": "SaaS",
        "company_size": "small",
        "marketing_sophistication_avg": 5.0,
        "economic_segments": "[]",
        "thread_initiation_ratio": None,
        "user_reply_rate": None,
    }
    defaults.update(kwargs)
    db.execute(
        """INSERT OR REPLACE INTO sender_profiles
           (sender_domain, company_name, primary_email, total_messages,
            industry, company_size, marketing_sophistication_avg,
            economic_segments, thread_initiation_ratio, user_reply_rate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            domain, defaults["company_name"], defaults["primary_email"],
            defaults["total_messages"], defaults["industry"], defaults["company_size"],
            defaults["marketing_sophistication_avg"], defaults["economic_segments"],
            defaults["thread_initiation_ratio"], defaults["user_reply_rate"],
        ),
    )
    db.commit()


def _insert_content(db, domain, text, is_sent=False):
    """Helper to insert a message with content for a domain."""
    import uuid
    msg_id = str(uuid.uuid4())[:8]
    thread_id = f"t_{msg_id}"
    db.execute("INSERT INTO threads (thread_id) VALUES (?)", (thread_id,))
    db.execute(
        """INSERT INTO messages (message_id, thread_id, from_address, date, is_sent)
           VALUES (?, ?, ?, '2024-01-01T10:00:00Z', ?)""",
        (msg_id, thread_id, f"user@{domain}", is_sent),
    )
    db.execute(
        "INSERT INTO parsed_metadata (message_id, sender_domain) VALUES (?, ?)",
        (msg_id, domain),
    )
    db.execute(
        "INSERT INTO parsed_content (message_id, body_clean) VALUES (?, ?)",
        (msg_id, text),
    )
    db.commit()
    return msg_id


class TestClassifyRelationship:
    def test_known_entity_infrastructure(self, db):
        _insert_profile(db, "stripe.com")
        profile = db.execute("SELECT * FROM sender_profiles WHERE sender_domain = 'stripe.com'").fetchone()
        entities = {"infrastructure": ["stripe.com"]}

        rel_type, conf, signals = _classify_relationship(db, profile, entities)
        assert rel_type == "my_infrastructure"
        assert conf == 0.9

    def test_known_entity_institutional(self, db):
        _insert_profile(db, "intuit.com")
        profile = db.execute("SELECT * FROM sender_profiles WHERE sender_domain = 'intuit.com'").fetchone()
        entities = {"institutional": ["intuit.com"]}

        rel_type, conf, signals = _classify_relationship(db, profile, entities)
        assert rel_type == "institutional"
        assert conf == 0.9

    def test_existing_manual_override(self, db):
        """Manual relationship entries take priority."""
        _insert_profile(db, "example.com")
        set_relationship(db, "example.com", "warm_contact", source="manual")

        profile = db.execute("SELECT * FROM sender_profiles WHERE sender_domain = 'example.com'").fetchone()
        rel_type, conf, signals = _classify_relationship(db, profile, {})
        assert rel_type == "warm_contact"
        assert conf == 1.0

    def test_vendor_signals_from_content(self, db):
        _insert_profile(db, "vendor.com", thread_initiation_ratio=0.8, economic_segments='["spend_map"]')
        _insert_content(db, "vendor.com", "Your invoice for subscription renewal is ready")
        _insert_content(db, "vendor.com", "Payment receipt for your account")
        _insert_content(db, "vendor.com", "Your billing statement is available")

        profile = db.execute("SELECT * FROM sender_profiles WHERE sender_domain = 'vendor.com'").fetchone()
        rel_type, conf, signals = _classify_relationship(db, profile, {})
        assert rel_type == "my_vendor"
        assert conf >= 0.6

    def test_selling_to_me_signals(self, db):
        _insert_profile(db, "sales.com", user_reply_rate=0.0, total_messages=10)
        _insert_content(db, "sales.com", "I wanted to reach out about our product. Book a demo today!")

        # Also add cold_outreach classification
        msg = db.execute("SELECT message_id FROM parsed_metadata WHERE sender_domain = 'sales.com' LIMIT 1").fetchone()
        db.execute(
            "INSERT INTO ai_classification (message_id, sender_intent) VALUES (?, 'cold_outreach')",
            (msg["message_id"],),
        )
        db.commit()

        profile = db.execute("SELECT * FROM sender_profiles WHERE sender_domain = 'sales.com'").fetchone()
        rel_type, conf, signals = _classify_relationship(db, profile, {})
        assert rel_type == "selling_to_me"
        assert conf >= 0.5

    def test_unknown_low_confidence(self, db):
        _insert_profile(db, "mystery.com")
        profile = db.execute("SELECT * FROM sender_profiles WHERE sender_domain = 'mystery.com'").fetchone()
        rel_type, conf, signals = _classify_relationship(db, profile, {})
        assert rel_type == "unknown"
        assert conf < 0.5

    def test_community_via_distribution_segment(self, db):
        _insert_profile(db, "newsletter.com", economic_segments='["distribution_map"]')
        profile = db.execute("SELECT * FROM sender_profiles WHERE sender_domain = 'newsletter.com'").fetchone()
        rel_type, conf, signals = _classify_relationship(db, profile, {})
        assert rel_type == "community"


class TestSetListRelationships:
    def test_set_and_list(self, db):
        set_relationship(db, "example.com", "my_vendor", note="Test vendor")
        items = list_relationships(db)
        assert len(items) == 1
        assert items[0]["sender_domain"] == "example.com"
        assert items[0]["relationship_type"] == "my_vendor"

    def test_list_with_filter(self, db):
        set_relationship(db, "vendor1.com", "my_vendor")
        set_relationship(db, "vendor2.com", "my_vendor")
        set_relationship(db, "prospect.com", "inbound_prospect")

        vendors = list_relationships(db, type_filter="my_vendor")
        assert len(vendors) == 2

        prospects = list_relationships(db, type_filter="inbound_prospect")
        assert len(prospects) == 1

    def test_set_overwrites(self, db):
        set_relationship(db, "example.com", "unknown")
        set_relationship(db, "example.com", "my_vendor", note="Updated")
        items = list_relationships(db)
        assert len(items) == 1
        assert items[0]["relationship_type"] == "my_vendor"


class TestImportRelationships:
    def test_import_from_yaml(self, db, tmp_path):
        data = {
            "my_vendor": ["stripe.com", "heroku.com"],
            "institutional": ["rippling.com"],
        }
        f = tmp_path / "import.yaml"
        f.write_text(yaml.dump(data))

        count = import_relationships(db, str(f))
        assert count == 3

        items = list_relationships(db)
        assert len(items) == 3

    def test_import_missing_file(self, db):
        count = import_relationships(db, "/nonexistent/file.yaml")
        assert count == 0


class TestDetectRelationships:
    def test_auto_detect_applies(self, db):
        _insert_profile(db, "stripe.com")
        entities = {"infrastructure": ["stripe.com"]}

        proposals = detect_relationships(db, known_entities=entities, apply=True)
        assert len(proposals) == 1
        assert proposals[0]["proposed_type"] == "my_infrastructure"

        # Check it was written to DB
        items = list_relationships(db)
        assert len(items) == 1
        assert items[0]["suppress_gems"] == 1  # infrastructure gets suppressed

    def test_auto_detect_no_overwrite_manual(self, db):
        """Auto-detect should not overwrite manual entries."""
        _insert_profile(db, "stripe.com")
        set_relationship(db, "stripe.com", "warm_contact", source="manual")

        entities = {"infrastructure": ["stripe.com"]}
        detect_relationships(db, known_entities=entities, apply=True)

        items = list_relationships(db)
        assert len(items) == 1
        assert items[0]["relationship_type"] == "warm_contact"  # manual preserved


class TestCompletionSignals:
    def test_detects_completion(self, db):
        db.execute("INSERT INTO threads (thread_id) VALUES ('t1')")
        db.execute(
            """INSERT INTO messages (message_id, thread_id, from_address, date, body_text)
               VALUES ('m1', 't1', 'them@example.com', '2024-01-01', 'Great working with you on this project')"""
        )
        db.commit()

        signals = scan_completion_signals(db, "t1")
        assert len(signals) >= 1

    def test_no_completion_signals(self, db):
        db.execute("INSERT INTO threads (thread_id) VALUES ('t1')")
        db.execute(
            """INSERT INTO messages (message_id, thread_id, from_address, date, body_text)
               VALUES ('m1', 't1', 'them@example.com', '2024-01-01', 'Hey can we schedule a call next week?')"""
        )
        db.commit()

        signals = scan_completion_signals(db, "t1")
        assert len(signals) == 0
