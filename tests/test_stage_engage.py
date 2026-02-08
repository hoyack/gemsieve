"""Tests for Stage 7: Engagement draft generation."""

import json
import os
from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content
from gemsieve.stages.metadata import extract_metadata
from gemsieve.stages.profile import build_profiles, detect_gems
from gemsieve.stages.engage import (
    _build_strategy_context,
    generate_engagement,
    GEM_STRATEGY_MAP,
)
from gemsieve.ai.prompts import STRATEGY_PROMPTS, DEFAULT_ENGAGEMENT_PROMPT
from gemsieve.config import EngagementConfig


def _setup_gem_pipeline(db, msg):
    """Insert message through full pipeline up to gem detection."""
    insert_message(db, msg)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)
    parse_content(db)

    # Ensure test domain is not treated as bulk for gem detection tests
    db.execute("UPDATE parsed_metadata SET is_bulk = 0 WHERE message_id = ?", (msg["message_id"],))

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

    build_profiles(db)

    # Ensure profile has enough messages for weak_marketing_lead detection
    domain = msg["from_address"].split("@")[1]
    db.execute("UPDATE sender_profiles SET total_messages = 3 WHERE sender_domain = ?", (domain,))
    db.commit()

    detect_gems(db)


def test_build_strategy_context_audit(db, sample_marketing_message):
    """Audit strategy context includes user_audience."""
    _setup_gem_pipeline(db, sample_marketing_message)

    gem = db.execute("SELECT * FROM gems WHERE gem_type = 'weak_marketing_lead'").fetchone()
    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = ?",
        (gem["sender_domain"],),
    ).fetchone()

    config = EngagementConfig(
        your_service="email marketing consulting",
        your_audience="B2B SaaS companies",
    )

    ctx = _build_strategy_context("audit", dict(gem), dict(profile), config)

    assert ctx["strategy_name"] == "audit"
    assert ctx["gem_type"] == "weak_marketing_lead"
    assert ctx["user_audience"] == "B2B SaaS companies"
    assert ctx["user_service_description"] == "email marketing consulting"
    assert "gem_explanation_json" in ctx


def test_build_strategy_context_revival(db, sample_marketing_message):
    """Revival strategy context includes thread_subject and dormancy_days."""
    _setup_gem_pipeline(db, sample_marketing_message)

    # Create a fake revival gem
    gem = {
        "gem_type": "dormant_warm_thread",
        "thread_id": "thread_002",
        "explanation": json.dumps({
            "summary": "Thread 'API Pricing' has been dormant for 45 days.",
            "signals": [{"signal": "warm_pricing", "evidence": "pricing"}],
        }),
        "sender_domain": "coolsaas.io",
    }
    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'coolsaas.io'"
    ).fetchone()

    config = EngagementConfig()
    ctx = _build_strategy_context("revival", gem, dict(profile), config)

    assert ctx["strategy_name"] == "revival"
    assert "thread_subject" in ctx
    assert "dormancy_days" in ctx


def test_build_strategy_context_renewal_negotiation(db, sample_marketing_message):
    """Renewal negotiation context includes renewal_dates and monetary_signals."""
    _setup_gem_pipeline(db, sample_marketing_message)

    gem = {
        "gem_type": "renewal_leverage",
        "explanation": json.dumps({"summary": "Renewal window approaching."}),
        "sender_domain": "coolsaas.io",
    }
    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'coolsaas.io'"
    ).fetchone()

    config = EngagementConfig()
    ctx = _build_strategy_context("renewal_negotiation", gem, dict(profile), config)

    assert "renewal_dates" in ctx
    assert "monetary_signals" in ctx


def test_build_strategy_context_partner(db, sample_marketing_message):
    """Partner strategy context includes partner_urls."""
    _setup_gem_pipeline(db, sample_marketing_message)

    gem = {
        "gem_type": "partner_program",
        "explanation": json.dumps({"summary": "Partner program detected."}),
        "sender_domain": "coolsaas.io",
    }
    profile = db.execute(
        "SELECT * FROM sender_profiles WHERE sender_domain = 'coolsaas.io'"
    ).fetchone()

    config = EngagementConfig(your_audience="B2B companies")
    ctx = _build_strategy_context("partner", gem, dict(profile), config)

    assert "partner_urls" in ctx
    assert ctx["user_audience"] == "B2B companies"


def test_strategy_prompt_selection():
    """Each strategy has a corresponding prompt in STRATEGY_PROMPTS."""
    for strategy in ["audit", "revival", "partner", "renewal_negotiation",
                     "industry_report", "mirror", "distribution_pitch"]:
        assert strategy in STRATEGY_PROMPTS, f"Missing prompt for strategy: {strategy}"


def test_strategy_prompt_fallback():
    """Unknown strategy falls back to DEFAULT_ENGAGEMENT_PROMPT."""
    prompt = STRATEGY_PROMPTS.get("nonexistent_strategy", DEFAULT_ENGAGEMENT_PROMPT)
    assert prompt == DEFAULT_ENGAGEMENT_PROMPT


def test_preferred_strategies_filter(db, sample_marketing_message):
    """preferred_strategies filters out gems with non-preferred strategies."""
    _setup_gem_pipeline(db, sample_marketing_message)

    # Mock AI provider
    mock_provider = MagicMock()
    mock_provider.complete.return_value = {"subject_line": "Test", "body": "Test body"}

    config = EngagementConfig(
        preferred_strategies=["revival"],  # Only revival, not audit/partner
    )

    with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
        count = generate_engagement(
            db, model_spec="test:model",
            engagement_config=config,
            ai_config={},
        )

    # No gems should match because weak_marketing_lead maps to "audit"
    # and partner_program maps to "partner" — neither is in preferred_strategies
    assert count == 0


def test_preferred_strategies_bypass_for_gem_id(db, sample_marketing_message):
    """preferred_strategies filter is bypassed when gem_id is specified."""
    _setup_gem_pipeline(db, sample_marketing_message)

    gem = db.execute("SELECT * FROM gems LIMIT 1").fetchone()

    mock_provider = MagicMock()
    mock_provider.complete.return_value = {"subject_line": "Test", "body": "Test body"}

    config = EngagementConfig(
        preferred_strategies=["revival"],  # Won't match this gem
    )

    with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
        count = generate_engagement(
            db, model_spec="test:model",
            gem_id=gem["id"],
            engagement_config=config,
            ai_config={},
        )

    # Should still generate because gem_id bypasses preferred_strategies filter
    assert count == 1


def test_max_outreach_per_day(db, sample_marketing_message):
    """Daily limit prevents generating more than max_outreach_per_day drafts."""
    _setup_gem_pipeline(db, sample_marketing_message)

    # Get an actual gem_id from the pipeline
    gem = db.execute("SELECT id, sender_domain FROM gems LIMIT 1").fetchone()
    gem_id = gem["id"]
    gem_domain = gem["sender_domain"]

    # Insert fake drafts to fill up the daily limit
    for i in range(5):
        db.execute(
            """INSERT INTO engagement_drafts
               (gem_id, sender_domain, strategy, channel, subject_line, body_text, status)
               VALUES (?, ?, 'audit', 'email', 'Test', 'Body', 'draft')""",
            (gem_id, gem_domain),
        )
    db.commit()

    mock_provider = MagicMock()
    mock_provider.complete.return_value = {"subject_line": "Test", "body": "Test body"}

    config = EngagementConfig(max_outreach_per_day=5)

    with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
        count = generate_engagement(
            db, model_spec="test:model",
            engagement_config=config,
            ai_config={},
        )

    # Should not generate any more since we're at the limit
    assert count == 0
