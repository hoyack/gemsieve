"""Tests for Stage 1: Metadata extraction."""

import json
import os

from tests.conftest import insert_message
from gemsieve.stages.metadata import extract_metadata


def test_extract_metadata_basic(db, sample_message):
    """Metadata extraction parses sender domain and auth results."""
    insert_message(db, sample_message)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    count = extract_metadata(db, esp_rules_path=esp_rules_path)

    assert count == 1

    row = db.execute(
        "SELECT * FROM parsed_metadata WHERE message_id = ?",
        (sample_message["message_id"],),
    ).fetchone()

    assert row is not None
    assert row["sender_domain"] == "acme.com"
    assert row["spf_result"] == "pass"
    assert row["dmarc_result"] == "pass"


def test_extract_metadata_esp_detection(db, sample_marketing_message):
    """ESP fingerprinting detects SendGrid from headers."""
    insert_message(db, sample_marketing_message)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    count = extract_metadata(db, esp_rules_path=esp_rules_path)

    assert count == 1

    row = db.execute(
        "SELECT * FROM parsed_metadata WHERE message_id = ?",
        (sample_marketing_message["message_id"],),
    ).fetchone()

    assert row is not None
    assert row["esp_identified"] == "sendgrid"
    assert row["is_bulk"] == 1  # has List-Unsubscribe


def test_extract_metadata_idempotent(db, sample_message):
    """Running metadata extraction twice doesn't process already-parsed messages."""
    insert_message(db, sample_message)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    count1 = extract_metadata(db, esp_rules_path=esp_rules_path)
    count2 = extract_metadata(db, esp_rules_path=esp_rules_path)

    assert count1 == 1
    assert count2 == 0  # already processed


def test_sender_temporal(db, sample_message):
    """Temporal patterns are computed for sender domains."""
    insert_message(db, sample_message)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)

    row = db.execute(
        "SELECT * FROM sender_temporal WHERE sender_domain = 'acme.com'"
    ).fetchone()

    assert row is not None
    assert row["total_messages"] == 1
