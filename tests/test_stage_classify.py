"""Tests for Stage 4: AI classification (mocked)."""

import json
import os
from unittest.mock import MagicMock, patch

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content
from gemsieve.stages.metadata import extract_metadata
from gemsieve.stages.classify import _build_few_shot_examples, _get_message_overrides


def _setup_classifiable(db, msg):
    """Insert a message ready for classification."""
    insert_message(db, msg)
    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)
    parse_content(db)


MOCK_RESPONSE = {
    "industry": "SaaS",
    "company_size_estimate": "small",
    "marketing_sophistication": 6,
    "sender_intent": "promotional",
    "product_type": "SaaS subscription",
    "product_description": "AI-powered analytics dashboard",
    "pain_points_addressed": ["data analysis", "reporting"],
    "target_audience": "B2B companies",
    "partner_program_detected": True,
    "renewal_signal_detected": False,
    "confidence": 0.85,
}


def test_classify_with_mock_provider(db, sample_marketing_message):
    """Classification stores results using a mocked AI provider."""
    _setup_classifiable(db, sample_marketing_message)

    mock_provider = MagicMock()
    mock_provider.complete.return_value = MOCK_RESPONSE

    with patch("gemsieve.ai.get_provider") as mock_get:
        mock_get.return_value = (mock_provider, "test-model")

        from gemsieve.stages.classify import classify_messages
        count = classify_messages(db, model_spec="test:model")

    assert count == 1

    row = db.execute(
        "SELECT * FROM ai_classification WHERE message_id = ?",
        (sample_marketing_message["message_id"],),
    ).fetchone()

    assert row is not None
    assert row["industry"] == "SaaS"
    assert row["marketing_sophistication"] == 6
    assert row["partner_program_detected"] == 1


# --- Wave 5: Classification Feedback Loop Tests ---


def test_build_few_shot_examples_empty(db):
    """No overrides returns empty string."""
    result = _build_few_shot_examples(db)
    assert result == ""


def test_build_few_shot_examples_with_overrides(db, sample_marketing_message):
    """Few-shot examples are built from classification overrides."""
    _setup_classifiable(db, sample_marketing_message)

    # Insert some overrides
    db.execute(
        """INSERT INTO classification_overrides
           (message_id, sender_domain, field_name, original_value, corrected_value, override_scope)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (sample_marketing_message["message_id"], "coolsaas.io",
         "industry", "SaaS", "Developer Tools", "sender"),
    )
    db.execute(
        """INSERT INTO classification_overrides
           (sender_domain, field_name, original_value, corrected_value, override_scope)
           VALUES (?, ?, ?, ?, ?)""",
        ("other.com", "company_size_estimate", "small", "medium", "sender"),
    )
    db.commit()

    result = _build_few_shot_examples(db)
    assert "CORRECTION:" in result
    assert "coolsaas.io" in result
    assert "Developer Tools" in result
    assert "Previous classification corrections" in result


def test_classify_retrain_appends_few_shot(db, sample_marketing_message):
    """With retrain=True, few-shot examples are appended to prompt."""
    _setup_classifiable(db, sample_marketing_message)

    # Insert an override
    db.execute(
        """INSERT INTO classification_overrides
           (sender_domain, field_name, original_value, corrected_value, override_scope)
           VALUES (?, ?, ?, ?, ?)""",
        ("example.com", "industry", "Other", "SaaS", "sender"),
    )
    db.commit()

    mock_provider = MagicMock()
    mock_provider.complete.return_value = MOCK_RESPONSE
    captured_prompts = []

    def capture_complete(prompt, model, system="", response_format=None):
        captured_prompts.append(prompt)
        return MOCK_RESPONSE

    mock_provider.complete.side_effect = capture_complete

    with patch("gemsieve.ai.get_provider") as mock_get:
        mock_get.return_value = (mock_provider, "test-model")

        from gemsieve.stages.classify import classify_messages
        classify_messages(db, model_spec="test:model", retrain=True)

    # The prompt should contain the few-shot correction
    assert len(captured_prompts) > 0
    assert "CORRECTION:" in captured_prompts[0]
    assert "SaaS" in captured_prompts[0]


def test_classify_retrain_false_no_few_shot(db, sample_marketing_message):
    """With retrain=False, no few-shot examples are appended."""
    _setup_classifiable(db, sample_marketing_message)

    # Insert an override
    db.execute(
        """INSERT INTO classification_overrides
           (sender_domain, field_name, original_value, corrected_value, override_scope)
           VALUES (?, ?, ?, ?, ?)""",
        ("example.com", "industry", "Other", "SaaS", "sender"),
    )
    db.commit()

    mock_provider = MagicMock()
    mock_provider.complete.return_value = MOCK_RESPONSE
    captured_prompts = []

    def capture_complete(prompt, model, system="", response_format=None):
        captured_prompts.append(prompt)
        return MOCK_RESPONSE

    mock_provider.complete.side_effect = capture_complete

    with patch("gemsieve.ai.get_provider") as mock_get:
        mock_get.return_value = (mock_provider, "test-model")

        from gemsieve.stages.classify import classify_messages
        classify_messages(db, model_spec="test:model", retrain=False)

    assert len(captured_prompts) > 0
    assert "CORRECTION:" not in captured_prompts[0]


def test_message_scoped_override_applied(db, sample_marketing_message):
    """Message-scoped overrides are applied on top of sender-scoped AI result."""
    _setup_classifiable(db, sample_marketing_message)

    # Insert a message-scoped override
    db.execute(
        """INSERT INTO classification_overrides
           (message_id, field_name, original_value, corrected_value, override_scope)
           VALUES (?, ?, ?, ?, ?)""",
        (sample_marketing_message["message_id"], "sender_intent",
         "promotional", "newsletter", "message"),
    )
    db.commit()

    mock_provider = MagicMock()
    mock_provider.complete.return_value = dict(MOCK_RESPONSE)

    with patch("gemsieve.ai.get_provider") as mock_get:
        mock_get.return_value = (mock_provider, "test-model")

        from gemsieve.stages.classify import classify_messages
        classify_messages(db, model_spec="test:model")

    row = db.execute(
        "SELECT * FROM ai_classification WHERE message_id = ?",
        (sample_marketing_message["message_id"],),
    ).fetchone()

    # Message-scoped override should have changed sender_intent
    assert row["sender_intent"] == "newsletter"
    assert row["has_override"] == 1
    # Other fields should still be from AI
    assert row["industry"] == "SaaS"


def test_get_message_overrides(db, sample_marketing_message):
    """_get_message_overrides returns message-scoped overrides."""
    insert_message(db, sample_marketing_message)

    db.execute(
        """INSERT INTO classification_overrides
           (message_id, field_name, original_value, corrected_value, override_scope)
           VALUES (?, ?, ?, ?, ?)""",
        ("msg_002", "industry", "SaaS", "E-commerce", "message"),
    )
    db.commit()

    result = _get_message_overrides(db, "msg_002")
    assert result == {"industry": "E-commerce"}

    # Non-existent message returns empty
    result = _get_message_overrides(db, "msg_nonexistent")
    assert result == {}
