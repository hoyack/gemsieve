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


def test_footer_stripping():
    """Footer stripping removes marketing footer patterns."""
    from gemsieve.stages.content import _strip_footer

    text = (
        "Hello,\n\n"
        "This is the main content of the email.\n"
        "It has multiple lines of real content.\n\n"
        "Thanks for reading!\n\n"
        "You are receiving this email because you subscribed to our list.\n"
        "Click here to unsubscribe.\n"
        "© 2024 Acme Inc. All rights reserved."
    )

    clean, footer = _strip_footer(text)

    assert "main content" in clean
    assert "Thanks for reading" in clean
    assert "receiving this email" not in clean
    assert footer is not None
    assert "receiving this email" in footer


def test_footer_stripping_no_footer():
    """Footer stripping returns original text when no footer patterns found."""
    from gemsieve.stages.content import _strip_footer

    text = "Hello,\n\nThis is a normal email.\n\nBest,\nJohn"

    clean, footer = _strip_footer(text)

    assert clean == text
    assert footer is None


def test_footer_stripping_copyright():
    """Footer stripping detects copyright lines as footer start."""
    from gemsieve.stages.content import _strip_footer

    text = (
        "Great product update!\n\n"
        "New features include:\n"
        "- Feature A\n"
        "- Feature B\n\n"
        "© 2024 CoolSaaS Inc.\n"
        "123 Main St, SF, CA 94105"
    )

    clean, footer = _strip_footer(text)

    assert "Feature A" in clean
    assert "© 2024" not in clean


def test_footer_stripping_powered_by():
    """Footer stripping detects 'powered by' pattern."""
    from gemsieve.stages.content import _strip_footer

    text = (
        "Welcome to our newsletter!\n\n"
        "Here are today's top stories.\n\n"
        "Powered by Mailchimp\n"
        "Unsubscribe from this list"
    )

    clean, footer = _strip_footer(text)

    assert "newsletter" in clean
    assert "Powered by" not in clean


def test_parse_content_idempotent(db, sample_message):
    """Running content parsing twice doesn't reprocess."""
    insert_message(db, sample_message)

    count1 = parse_content(db)
    count2 = parse_content(db)

    assert count1 == 1
    assert count2 == 0
