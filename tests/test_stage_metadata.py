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


def test_extract_metadata_new_fields(db):
    """Metadata extraction populates x_mailer, mail_server, precedence, feedback_id."""
    import json
    from tests.conftest import insert_message

    msg = {
        "message_id": "msg_new_fields",
        "thread_id": "thread_nf",
        "date": "Mon, 15 Jan 2024 10:30:00 +0000",
        "from_address": "test@newfields.com",
        "from_name": "Test",
        "reply_to": None,
        "to_addresses": json.dumps([]),
        "cc_addresses": json.dumps([]),
        "subject": "Test new fields",
        "headers_raw": json.dumps({
            "from": ["Test <test@newfields.com>"],
            "x-mailer": ["MailChimp Mailer 2.0"],
            "received": [
                "by 2002:a17:90a:c34c with SMTP id local",
                "from mail-outbound.newfields.com [10.0.0.1] by mx.google.com",
            ],
            "precedence": ["bulk"],
            "feedback-id": ["123456:campaign_789:newfields"],
        }),
        "body_html": None,
        "body_text": "Test body",
        "labels": json.dumps(["INBOX"]),
        "snippet": "Test body",
        "size_estimate": 100,
        "is_sent": False,
    }
    insert_message(db, msg)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)

    row = db.execute(
        "SELECT * FROM parsed_metadata WHERE message_id = 'msg_new_fields'"
    ).fetchone()

    assert row is not None
    assert row["x_mailer"] == "MailChimp Mailer 2.0"
    assert row["mail_server"] == "mail-outbound.newfields.com"
    assert row["precedence"] == "bulk"
    assert row["feedback_id"] == "123456:campaign_789:newfields"


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
