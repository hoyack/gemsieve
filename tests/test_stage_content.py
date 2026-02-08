"""Tests for Stage 2: Content parsing."""

import json

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content


def test_parse_content_basic(db, sample_message):
    """Content parsing extracts clean body text."""
    insert_message(db, sample_message)

    count = parse_content(db)
    assert count == 1

    row = db.execute(
        "SELECT * FROM parsed_content WHERE message_id = ?",
        (sample_message["message_id"],),
    ).fetchone()

    assert row is not None
    assert "evaluating solutions" in row["body_clean"].lower()
    # Signature should be stripped into signature_block
    assert row["signature_block"] is not None


def test_parse_content_marketing(db, sample_marketing_message):
    """Marketing email parsing detects offers, CTAs, tracking pixels."""
    insert_message(db, sample_marketing_message)

    count = parse_content(db)
    assert count == 1

    row = db.execute(
        "SELECT * FROM parsed_content WHERE message_id = ?",
        (sample_marketing_message["message_id"],),
    ).fetchone()

    assert row is not None

    # Offer detection
    offer_types = json.loads(row["offer_types"])
    assert "free_trial" in offer_types
    assert "discount" in offer_types
    assert "social_proof" in offer_types
    assert "product_launch" in offer_types

    # Tracking pixel
    assert row["tracking_pixel_count"] >= 1

    # CTA extraction
    cta_texts = json.loads(row["cta_texts"])
    assert any("Free Trial" in cta for cta in cta_texts)

    # Link intents
    link_intents = json.loads(row["link_intents"])
    assert "partner_program" in link_intents

    # UTM campaigns
    utm = json.loads(row["utm_campaigns"])
    assert len(utm) >= 1
    assert utm[0].get("utm_campaign") == "launch2024"

    # Social links
    social = json.loads(row["social_links"])
    assert "twitter" in social or "linkedin" in social

    # Physical address
    assert row["has_physical_address"] == 1

    # Headline
    assert row["primary_headline"] is not None


def test_parse_content_idempotent(db, sample_message):
    """Running content parsing twice doesn't reprocess."""
    insert_message(db, sample_message)

    count1 = parse_content(db)
    count2 = parse_content(db)

    assert count1 == 1
    assert count2 == 0
