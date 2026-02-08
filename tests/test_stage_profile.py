"""Tests for Stage 5: Sender profiling and gem detection."""

import json
import os
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content
from gemsieve.stages.metadata import extract_metadata
from gemsieve.stages.profile import (
    build_profiles,
    compute_sophistication_score,
    detect_gems,
    _scan_warm_signals,
    _detect_co_marketing,
    _detect_dormant_warm_thread,
)


def _setup_classified_message(db, msg):
    """Insert a message and run through metadata + content + classification."""
    insert_message(db, msg)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)
    parse_content(db)

    # Ensure test domain is not treated as bulk for gem detection tests
    db.execute("UPDATE parsed_metadata SET is_bulk = 0 WHERE message_id = ?", (msg["message_id"],))

    # Insert mock classification directly
    db.execute(
        """INSERT INTO ai_classification
           (message_id, industry, company_size_estimate, marketing_sophistication,
            sender_intent, product_type, product_description, pain_points,
            target_audience, partner_program_detected, renewal_signal_detected,
            ai_confidence, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            msg["message_id"], "SaaS", "small", 4,
            "promotional", "SaaS subscription", "Analytics tool",
            json.dumps(["reporting"]), "B2B companies",
            True, False, 0.85, "test:model",
        ),
    )
    db.commit()


def test_build_profiles(db, sample_marketing_message):
    """Profile building aggregates message data per sender domain."""
    _setup_classified_message(db, sample_marketing_message)

    count = build_profiles(db)
    assert count >= 1

    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'coolsaas.io'"
    ).fetchone()

    assert profile is not None
    assert profile["industry"] == "SaaS"
    assert profile["company_size"] == "small"
    assert profile["total_messages"] == 1
    assert profile["has_partner_program"] == 1


def test_detect_gems(db, sample_marketing_message):
    """Gem detection finds weak marketing leads."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)

    # Ensure profile has enough messages for weak_marketing_lead detection
    db.execute("UPDATE sender_profiles SET total_messages = 3 WHERE sender_domain = 'coolsaas.io'")
    db.commit()

    count = detect_gems(db)
    assert count > 0

    gems = db.execute("SELECT * FROM gems").fetchall()
    gem_types = [g["gem_type"] for g in gems]

    # Should detect weak marketing lead (sophistication=4, size=small)
    assert "weak_marketing_lead" in gem_types


def test_detect_gems_idempotent(db, sample_marketing_message):
    """Running gem detection twice gives same results."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)

    count1 = detect_gems(db)
    count2 = detect_gems(db)

    # Same count since gems table is cleared and re-detected
    assert count1 == count2


# --- Wave 3 Tests ---


def test_scan_warm_signals(db, sample_message):
    """_scan_warm_signals finds pricing, decision_maker, and budget signals."""
    insert_message(db, sample_message)
    parse_content(db)

    signals, score_boost = _scan_warm_signals(db, "thread_001")

    # sample_message body mentions "pricing", "evaluating", "VP Engineering", "$500"
    signal_types = [s["signal"] for s in signals]
    assert any("pricing" in s for s in signal_types)
    assert score_boost > 0
    assert score_boost <= 30  # capped at 30


def test_scan_warm_signals_empty_thread(db):
    """Empty thread returns no warm signals."""
    signals, score_boost = _scan_warm_signals(db, "nonexistent_thread")
    assert signals == []
    assert score_boost == 0


def test_compute_sophistication_score_enterprise_esp():
    """Enterprise ESP with all features scores high."""
    score = compute_sophistication_score(
        esp="HubSpot",
        has_personalization=True,
        has_utm=True,
        template_complexity=80,
        spf="pass",
        dkim="hubspot.com",
        dmarc="pass",
        has_unsubscribe=True,
        unique_campaign_count=5,
    )
    assert score == 10  # 3+2+1+1+1+1+1 = 10


def test_compute_sophistication_score_basic():
    """Basic setup without features scores low."""
    score = compute_sophistication_score(
        esp=None,
        has_personalization=False,
        has_utm=False,
        template_complexity=10,
        spf=None,
        dkim=None,
        dmarc=None,
        has_unsubscribe=False,
        unique_campaign_count=0,
    )
    assert score == 1  # Only base ESP tier (unknown = 1)


def test_compute_sophistication_score_mid_tier():
    """Mid-tier ESP with some features."""
    score = compute_sophistication_score(
        esp="SendGrid",
        has_personalization=True,
        has_utm=True,
        template_complexity=30,
        spf="pass",
        dkim=None,
        dmarc="fail",
        has_unsubscribe=True,
        unique_campaign_count=1,
    )
    # ESP=2, personalization=2, utm=1, template=0, segmentation=0, auth=0, unsub=1
    assert score == 6


def test_detect_co_marketing_with_overlap(db, sample_marketing_message):
    """Co-marketing detection finds audience overlap."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)

    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'coolsaas.io'"
    ).fetchone()

    @dataclass
    class MockEngagementConfig:
        your_audience: str = "B2B companies SaaS developers"

    gems = _detect_co_marketing(db, profile, engagement_config=MockEngagementConfig())
    assert len(gems) == 1
    assert gems[0]["gem_type"] == "co_marketing"
    explanation = gems[0]["explanation"]
    assert "audience_overlap" in [s["signal"] for s in explanation["signals"]]
    assert explanation["estimated_value"] == "medium"
    assert explanation["urgency"] == "low"


def test_detect_co_marketing_no_config(db, sample_marketing_message):
    """Co-marketing returns empty without engagement_config."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)

    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'coolsaas.io'"
    ).fetchone()

    gems = _detect_co_marketing(db, profile, engagement_config=None)
    assert gems == []


def test_detect_co_marketing_no_overlap(db, sample_marketing_message):
    """Co-marketing returns empty when audiences don't overlap."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)

    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'coolsaas.io'"
    ).fetchone()

    @dataclass
    class MockEngagementConfig:
        your_audience: str = "healthcare hospitals physicians"

    gems = _detect_co_marketing(db, profile, engagement_config=MockEngagementConfig())
    assert gems == []


def test_explanation_enrichment_weak_marketing_lead(db, sample_marketing_message):
    """Weak marketing lead gems include estimated_value and urgency."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)

    # Ensure profile has enough messages for weak_marketing_lead detection
    db.execute("UPDATE sender_profiles SET total_messages = 3 WHERE sender_domain = 'coolsaas.io'")
    db.commit()

    detect_gems(db)

    gems = db.execute(
        "SELECT * FROM gems WHERE gem_type = 'weak_marketing_lead'"
    ).fetchall()
    assert len(gems) > 0

    explanation = json.loads(gems[0]["explanation"])
    assert "estimated_value" in explanation
    assert "urgency" in explanation
    assert explanation["urgency"] == "low"
    assert "confidence" in explanation


def test_explanation_enrichment_partner_program(db, sample_marketing_message):
    """Partner program gems include estimated_value and urgency."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)
    detect_gems(db)

    gems = db.execute(
        "SELECT * FROM gems WHERE gem_type = 'partner_program'"
    ).fetchall()
    assert len(gems) > 0

    explanation = json.loads(gems[0]["explanation"])
    assert explanation["estimated_value"] == "medium"
    assert explanation["urgency"] == "low"


def test_detect_gems_new_signature(db, sample_marketing_message):
    """detect_gems accepts engagement_config and scoring_config."""
    _setup_classified_message(db, sample_marketing_message)
    build_profiles(db)

    # Ensure profile has enough messages for weak_marketing_lead detection
    db.execute("UPDATE sender_profiles SET total_messages = 3 WHERE sender_domain = 'coolsaas.io'")
    db.commit()

    @dataclass
    class MockEngagementConfig:
        your_audience: str = "B2B companies SaaS developers"

    @dataclass
    class MockDormantConfig:
        min_dormancy_days: int = 14
        max_dormancy_days: int = 365
        require_human_sender: bool = True

    @dataclass
    class MockScoringConfig:
        dormant_thread: MockDormantConfig = None

        def __post_init__(self):
            if self.dormant_thread is None:
                self.dormant_thread = MockDormantConfig()

    count = detect_gems(
        db,
        engagement_config=MockEngagementConfig(),
        scoring_config=MockScoringConfig(),
    )
    assert count > 0

    gems = db.execute("SELECT * FROM gems").fetchall()
    gem_types = [g["gem_type"] for g in gems]
    # With audience overlap, should detect co_marketing too
    assert "co_marketing" in gem_types
    assert "weak_marketing_lead" in gem_types


def test_detect_dormant_warm_thread_filters_transactional(db):
    """Dormant warm thread detection filters out transactional intents."""
    # Create a thread with transactional intent
    msg = {
        "message_id": "msg_trans_001",
        "thread_id": "thread_trans_001",
        "date": "Mon, 15 Jan 2024 10:30:00 +0000",
        "from_address": "billing@vendor.com",
        "from_name": "Vendor Billing",
        "reply_to": "billing@vendor.com",
        "to_addresses": json.dumps([{"name": "Brandon", "email": "brandon@example.com"}]),
        "cc_addresses": json.dumps([]),
        "subject": "Invoice for pricing tier upgrade",
        "headers_raw": json.dumps({
            "from": ["Vendor Billing <billing@vendor.com>"],
            "authentication-results": ["spf=pass; dmarc=pass"],
        }),
        "body_html": "<p>Please review the pricing for your renewal.</p>",
        "body_text": "Please review the pricing for your renewal.",
        "labels": json.dumps(["INBOX"]),
        "snippet": "Invoice for pricing tier",
        "size_estimate": 1000,
        "is_sent": False,
    }
    insert_message(db, msg)

    # Set thread as dormant awaiting user response
    db.execute(
        """UPDATE threads SET awaiting_response_from = 'user',
           days_dormant = 30, last_sender = 'billing@vendor.com',
           user_participated = 1, message_count = 2
           WHERE thread_id = 'thread_trans_001'"""
    )

    # Add parsed_metadata for domain
    db.execute(
        """INSERT INTO parsed_metadata (message_id, sender_domain) VALUES (?, ?)""",
        ("msg_trans_001", "vendor.com"),
    )

    # Add transactional classification
    db.execute(
        """INSERT INTO ai_classification
           (message_id, industry, company_size_estimate, marketing_sophistication,
            sender_intent, product_type, product_description, pain_points,
            target_audience, partner_program_detected, renewal_signal_detected,
            ai_confidence, model_used)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("msg_trans_001", "SaaS", "small", 5, "transactional",
         "SaaS", "Tool", json.dumps([]), "B2B", False, False, 0.9, "test:model"),
    )
    db.commit()

    parse_content(db)
    build_profiles(db)

    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'vendor.com'"
    ).fetchone()

    gems = _detect_dormant_warm_thread(db, profile)
    # Should be empty because transactional intent is filtered out
    assert len(gems) == 0
