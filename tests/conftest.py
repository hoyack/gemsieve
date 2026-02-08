"""Shared test fixtures."""

from __future__ import annotations

import json
import os
import sqlite3

import pytest

from gemsieve.database import init_db


@pytest.fixture
def db():
    """In-memory SQLite database with schema initialized."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def sample_message():
    """A realistic sample message dict."""
    return {
        "message_id": "msg_001",
        "thread_id": "thread_001",
        "date": "Mon, 15 Jan 2024 10:30:00 +0000",
        "from_address": "sarah@acme.com",
        "from_name": "Sarah Chen",
        "reply_to": "sarah@acme.com",
        "to_addresses": json.dumps([{"name": "Brandon", "email": "brandon@example.com"}]),
        "cc_addresses": json.dumps([]),
        "subject": "Quick question about your API pricing",
        "headers_raw": json.dumps({
            "from": ["Sarah Chen <sarah@acme.com>"],
            "to": ["brandon@example.com"],
            "subject": ["Quick question about your API pricing"],
            "date": ["Mon, 15 Jan 2024 10:30:00 +0000"],
            "return-path": ["<bounce@em.acme.com>"],
            "dkim-signature": ["v=1; d=acme.com; s=selector;"],
            "authentication-results": ["spf=pass; dmarc=pass"],
            "received": ["from mail.acme.com [192.168.1.1] by mx.google.com"],
        }),
        "body_html": """<html><body>
            <h1>API Pricing Question</h1>
            <p>Hi Brandon,</p>
            <p>We're evaluating solutions for our team of 30 engineers.
            Could you share your API pricing tiers?</p>
            <p>We're currently spending about $500/mo on our current solution
            and looking for something that scales better.</p>
            <a href="https://acme.com/pricing" class="button" style="background-color: blue;">View Plans</a>
            <p>Best regards,<br/>
            Sarah Chen<br/>
            VP Engineering, Acme Corp<br/>
            sarah@acme.com</p>
        </body></html>""",
        "body_text": (
            "Hi Brandon,\n\n"
            "We're evaluating solutions for our team of 30 engineers.\n"
            "Could you share your API pricing tiers?\n\n"
            "We're currently spending about $500/mo on our current solution\n"
            "and looking for something that scales better.\n\n"
            "Best regards,\n"
            "Sarah Chen\n"
            "VP Engineering, Acme Corp\n"
            "sarah@acme.com"
        ),
        "labels": json.dumps(["INBOX"]),
        "snippet": "We're evaluating solutions for our team of 30 engineers.",
        "size_estimate": 5000,
        "is_sent": False,
    }


@pytest.fixture
def sample_marketing_message():
    """A marketing/promotional email sample."""
    return {
        "message_id": "msg_002",
        "thread_id": "thread_002",
        "date": "Wed, 20 Mar 2024 14:00:00 +0000",
        "from_address": "marketing@coolsaas.io",
        "from_name": "CoolSaaS",
        "reply_to": "marketing@coolsaas.io",
        "to_addresses": json.dumps([{"name": "Brandon", "email": "brandon@example.com"}]),
        "cc_addresses": json.dumps([]),
        "subject": "🚀 Just launched: AI-powered analytics dashboard",
        "headers_raw": json.dumps({
            "from": ["CoolSaaS <marketing@coolsaas.io>"],
            "to": ["brandon@example.com"],
            "return-path": ["<bounce-123@sendgrid.net>"],
            "dkim-signature": ["v=1; d=sendgrid.net; s=s1;"],
            "x-sg-eid": ["abc123"],
            "list-unsubscribe": ["<https://coolsaas.io/unsub?id=123>"],
            "precedence": ["bulk"],
            "authentication-results": ["spf=pass; dmarc=pass"],
        }),
        "body_html": """<html><body>
            <table><tr><td>
            <h1>Introducing: AI Analytics</h1>
            <p>Trusted by 500+ companies worldwide.</p>
            <p>Start your 14-day free trial today!</p>
            <p>Use promo code LAUNCH25 for 25% off your first year.</p>
            <a href="https://coolsaas.io/signup?utm_source=email&utm_medium=newsletter&utm_campaign=launch2024"
               class="btn" style="background-color: #007bff;">Start Free Trial</a>
            <a href="https://coolsaas.io/partners">Become a Partner</a>
            <img src="https://tracking.sendgrid.net/pixel.gif" width="1" height="1" />
            <p>123 Main Street, San Francisco, CA 94105</p>
            <p><a href="https://twitter.com/coolsaas">Twitter</a> |
               <a href="https://linkedin.com/company/coolsaas">LinkedIn</a></p>
            </td></tr></table>
        </body></html>""",
        "body_text": (
            "Introducing: AI Analytics\n\n"
            "Trusted by 500+ companies.\n"
            "Start your 14-day free trial today!\n"
            "Use promo code LAUNCH25 for 25% off.\n"
        ),
        "labels": json.dumps(["INBOX", "CATEGORY_PROMOTIONS"]),
        "snippet": "Introducing AI Analytics — start your free trial",
        "size_estimate": 15000,
        "is_sent": False,
    }


def insert_message(db: sqlite3.Connection, msg: dict) -> None:
    """Insert a test message into the database."""
    # Insert thread first
    db.execute(
        """INSERT OR IGNORE INTO threads (thread_id, subject, message_count)
           VALUES (?, ?, 1)""",
        (msg["thread_id"], msg["subject"]),
    )

    db.execute(
        """INSERT OR IGNORE INTO messages
           (message_id, thread_id, date, from_address, from_name, reply_to,
            to_addresses, cc_addresses, subject, headers_raw, body_html, body_text,
            labels, snippet, size_estimate, is_sent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg["message_id"], msg["thread_id"], msg["date"],
            msg["from_address"], msg["from_name"], msg["reply_to"],
            msg["to_addresses"], msg["cc_addresses"], msg["subject"],
            msg["headers_raw"], msg["body_html"], msg["body_text"],
            msg["labels"], msg["snippet"], msg["size_estimate"],
            msg["is_sent"],
        ),
    )
    db.commit()


@pytest.fixture
def sample_dormant_thread_message():
    """A B2B message from a human sender (Director title) with warm signal content."""
    return {
        "message_id": "msg_dormant_001",
        "thread_id": "thread_dormant_001",
        "date": "Thu, 10 Oct 2024 09:00:00 +0000",
        "from_address": "jessica@bigclient.com",
        "from_name": "Jessica Park",
        "reply_to": "jessica@bigclient.com",
        "to_addresses": json.dumps([{"name": "Brandon", "email": "brandon@example.com"}]),
        "cc_addresses": json.dumps([]),
        "subject": "Re: API integration pricing discussion",
        "headers_raw": json.dumps({
            "from": ["Jessica Park <jessica@bigclient.com>"],
            "to": ["brandon@example.com"],
            "date": ["Thu, 10 Oct 2024 09:00:00 +0000"],
            "authentication-results": ["spf=pass; dmarc=pass"],
            "dkim-signature": ["v=1; d=bigclient.com; s=selector;"],
        }),
        "body_html": None,
        "body_text": (
            "Hi Brandon,\n\n"
            "Following up on our pricing discussion. We have a $50,000 budget "
            "allocated for this quarter and would like to schedule a call to finalize.\n\n"
            "Could you share your API pricing tiers so our Director of Engineering "
            "can evaluate? We're interested in the enterprise plan.\n\n"
            "Best regards,\n"
            "Jessica Park\n"
            "Director of Partnerships, BigClient Inc"
        ),
        "labels": json.dumps(["INBOX"]),
        "snippet": "Following up on our pricing discussion",
        "size_estimate": 3000,
        "is_sent": False,
    }


@pytest.fixture
def sample_procurement_message():
    """A message containing RFP, SOC 2 compliance, and proof-of-concept keywords."""
    return {
        "message_id": "msg_procurement_001",
        "thread_id": "thread_procurement_001",
        "date": "Fri, 15 Nov 2024 11:00:00 +0000",
        "from_address": "procurement@bigcorp.com",
        "from_name": "BigCorp Procurement",
        "reply_to": "procurement@bigcorp.com",
        "to_addresses": json.dumps([{"name": "Brandon", "email": "brandon@example.com"}]),
        "cc_addresses": json.dumps([]),
        "subject": "RFP: Enterprise platform vendor assessment",
        "headers_raw": json.dumps({
            "from": ["BigCorp Procurement <procurement@bigcorp.com>"],
            "to": ["brandon@example.com"],
            "date": ["Fri, 15 Nov 2024 11:00:00 +0000"],
            "authentication-results": ["spf=pass; dmarc=pass"],
            "dkim-signature": ["v=1; d=bigcorp.com; s=selector;"],
        }),
        "body_html": None,
        "body_text": (
            "Hello,\n\n"
            "We are issuing an RFP for enterprise platform solutions. "
            "As part of our vendor risk assessment, we require SOC 2 compliance "
            "documentation and a proof of concept deployment.\n\n"
            "Please respond with your security questionnaire by the deadline.\n\n"
            "BigCorp Procurement Team"
        ),
        "labels": json.dumps(["INBOX"]),
        "snippet": "We are issuing an RFP for enterprise platform solutions",
        "size_estimate": 2000,
        "is_sent": False,
    }


def setup_full_pipeline(
    db: sqlite3.Connection,
    msg: dict,
    classification_kwargs: dict | None = None,
    engagement_config=None,
    scoring_config=None,
) -> None:
    """Run a message through stages 0-5 (insert → metadata → content → mock classify → profile → detect_gems).

    Args:
        db: Database connection.
        msg: Message dict (from fixture).
        classification_kwargs: Override fields for the mock AI classification.
        engagement_config: Optional EngagementConfig for gem detection.
        scoring_config: Optional ScoringConfig for gem detection.
    """
    # Stage 0: Insert
    insert_message(db, msg)

    # Stage 1: Metadata
    from gemsieve.stages.metadata import extract_metadata
    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)

    # Stage 2: Content
    from gemsieve.stages.content import parse_content
    parse_content(db)

    # Stage 3: Mock classification (insert directly to avoid AI call)
    defaults = {
        "industry": "SaaS",
        "company_size_estimate": "small",
        "marketing_sophistication": 3,
        "sender_intent": "cold_outreach",
        "product_type": "SaaS subscription",
        "product_description": "A software product",
        "pain_points": json.dumps(["scaling"]),
        "target_audience": "B2B companies",
        "partner_program_detected": False,
        "renewal_signal_detected": False,
        "ai_confidence": 0.8,
        "model_used": "test",
        "has_override": False,
    }
    if classification_kwargs:
        defaults.update(classification_kwargs)

    db.execute(
        """INSERT OR REPLACE INTO ai_classification
           (message_id, industry, company_size_estimate, marketing_sophistication,
            sender_intent, product_type, product_description, pain_points,
            target_audience, partner_program_detected, renewal_signal_detected,
            ai_confidence, model_used, has_override)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg["message_id"],
            defaults["industry"],
            defaults["company_size_estimate"],
            defaults["marketing_sophistication"],
            defaults["sender_intent"],
            defaults["product_type"],
            defaults["product_description"],
            defaults["pain_points"],
            defaults["target_audience"],
            defaults["partner_program_detected"],
            defaults["renewal_signal_detected"],
            defaults["ai_confidence"],
            defaults["model_used"],
            defaults["has_override"],
        ),
    )
    db.commit()

    # Stage 4: Profile
    from gemsieve.stages.profile import build_profiles, detect_gems
    build_profiles(db)

    # Ensure test profiles have enough messages for gem detection filters
    domain = msg["from_address"].split("@")[1]
    db.execute("UPDATE sender_profiles SET total_messages = 3 WHERE sender_domain = ?", (domain,))
    db.commit()

    # Stage 5: Detect gems
    detect_gems(db, engagement_config=engagement_config, scoring_config=scoring_config)
