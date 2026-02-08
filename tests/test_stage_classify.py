"""Tests for Stage 4: AI classification (mocked)."""

import json
import os
from unittest.mock import MagicMock, patch

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content
from gemsieve.stages.metadata import extract_metadata


def test_classify_with_mock_provider(db, sample_marketing_message):
    """Classification stores results using a mocked AI provider."""
    insert_message(db, sample_marketing_message)

    esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
    extract_metadata(db, esp_rules_path=esp_rules_path)
    parse_content(db)

    mock_response = {
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

    mock_provider = MagicMock()
    mock_provider.complete.return_value = mock_response

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
