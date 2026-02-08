"""Tests for Stage 5: Sender profiling and gem detection."""

import json
import os
from unittest.mock import MagicMock, patch

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content
from gemsieve.stages.metadata import extract_metadata
from gemsieve.stages.profile import build_profiles, detect_gems


def _setup_classified_message(db, msg):
    """Insert a message and run through metadata + content + classification."""
    insert_message(db, msg)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)
    parse_content(db)

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
