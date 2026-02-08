"""Tests for CrewAI multi-agent integration."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content
from gemsieve.stages.metadata import extract_metadata


# Check if crewai is available
try:
    import crewai
    _crewai_available = True
except ImportError:
    _crewai_available = False


class TestCrewSchemas:
    """Test Pydantic output schemas (no crewai dependency needed)."""

    def test_sender_classification_schema(self):
        from gemsieve.ai.crews import SenderClassification

        data = SenderClassification(
            industry="SaaS",
            company_size_estimate="small",
            marketing_sophistication=7,
            sender_intent="promotional",
            confidence=0.85,
        )
        assert data.industry == "SaaS"
        assert data.marketing_sophistication == 7
        assert data.confidence == 0.85
        assert data.pain_points_addressed == []
        assert data.partner_program_detected is False

    def test_sender_classification_validation(self):
        from gemsieve.ai.crews import SenderClassification
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            SenderClassification(
                industry="SaaS",
                company_size_estimate="small",
                marketing_sophistication=15,  # > 10
                sender_intent="promotional",
                confidence=0.85,
            )

    def test_engagement_message_schema(self):
        from gemsieve.ai.crews import EngagementMessage

        msg = EngagementMessage(
            subject_line="Quick question about your ESP setup",
            body="I noticed you're using SendGrid...",
        )
        assert msg.subject_line == "Quick question about your ESP setup"
        assert "SendGrid" in msg.body

    def test_classification_to_dict(self):
        from gemsieve.ai.crews import SenderClassification

        data = SenderClassification(
            industry="E-commerce",
            company_size_estimate="medium",
            marketing_sophistication=5,
            sender_intent="newsletter",
            confidence=0.7,
        )
        d = data.model_dump()
        assert isinstance(d, dict)
        assert d["industry"] == "E-commerce"
        assert d["confidence"] == 0.7


class TestCrewClassifyIntegration:
    """Test classification with CrewAI using mocked crew execution."""

    def test_classify_with_crew_flag(self, db, sample_marketing_message):
        """classify_messages with use_crew=True calls crew_classify."""
        insert_message(db, sample_marketing_message)

        esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
        extract_metadata(db, esp_rules_path=esp_rules_path)
        parse_content(db)

        mock_result = {
            "industry": "SaaS",
            "company_size_estimate": "small",
            "marketing_sophistication": 6,
            "sender_intent": "promotional",
            "product_type": "SaaS subscription",
            "product_description": "AI-powered analytics dashboard",
            "pain_points_addressed": ["data analysis"],
            "target_audience": "B2B companies",
            "partner_program_detected": True,
            "renewal_signal_detected": False,
            "confidence": 0.85,
        }

        with patch("gemsieve.ai.crews.crew_classify", return_value=mock_result) as mock_crew:
            from gemsieve.stages.classify import classify_messages
            count = classify_messages(db, model_spec="ollama:test-model", use_crew=True)

        assert count == 1
        mock_crew.assert_called_once()

        # Verify the sender_data dict was passed correctly
        call_kwargs = mock_crew.call_args
        sender_data = call_kwargs[0][0]
        assert sender_data["from_address"] == "marketing@coolsaas.io"
        assert sender_data["from_name"] == "CoolSaaS"

        row = db.execute(
            "SELECT * FROM ai_classification WHERE message_id = ?",
            (sample_marketing_message["message_id"],),
        ).fetchone()
        assert row is not None
        assert row["industry"] == "SaaS"
        assert row["marketing_sophistication"] == 6

    def test_classify_standard_mode_unaffected(self, db, sample_marketing_message):
        """Without use_crew, the standard path is used (not crew_classify)."""
        insert_message(db, sample_marketing_message)

        esp_rules_path = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")
        extract_metadata(db, esp_rules_path=esp_rules_path)
        parse_content(db)

        mock_provider = MagicMock()
        mock_provider.complete.return_value = {
            "industry": "Marketing",
            "company_size_estimate": "medium",
            "marketing_sophistication": 8,
            "sender_intent": "cold_outreach",
            "product_type": "Digital product",
            "product_description": "Marketing platform",
            "pain_points_addressed": [],
            "target_audience": "Marketers",
            "partner_program_detected": False,
            "renewal_signal_detected": False,
            "confidence": 0.9,
        }

        with patch("gemsieve.ai.get_provider") as mock_get:
            mock_get.return_value = (mock_provider, "test-model")
            from gemsieve.stages.classify import classify_messages
            count = classify_messages(db, model_spec="test:model", use_crew=False)

        assert count == 1
        mock_provider.complete.assert_called_once()


class TestCrewEngageIntegration:
    """Test engagement generation with CrewAI using mocked crew execution."""

    def _insert_gem_and_profile(self, db):
        """Insert a gem and sender profile for engagement generation."""
        db.execute(
            """INSERT INTO sender_profiles
               (sender_domain, company_name, industry, company_size,
                marketing_sophistication_avg, esp_used, product_description,
                pain_points, known_contacts, total_messages)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "acme.com", "Acme Corp", "SaaS", "small",
                5.0, "SendGrid", "Project management tool",
                json.dumps(["team coordination", "deadline tracking"]),
                json.dumps([{"name": "Jane Smith", "role": "VP Marketing"}]),
                12,
            ),
        )
        db.execute(
            """INSERT INTO gems
               (gem_type, sender_domain, score, explanation,
                recommended_actions, status)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                "weak_marketing_lead", "acme.com", 75,
                json.dumps({"summary": "Low marketing sophistication with relevant industry"}),
                json.dumps(["Offer marketing audit"]),
                "new",
            ),
        )
        db.commit()
        return db.execute("SELECT last_insert_rowid()").fetchone()[0]

    def test_engage_with_crew_flag(self, db):
        """generate_engagement with use_crew=True calls crew_engage."""
        gem_id = self._insert_gem_and_profile(db)

        mock_result = {
            "subject_line": "Your SendGrid setup is leaving money on the table",
            "body": "Jane, I noticed Acme Corp is using SendGrid with a sophistication score of 5/10...",
        }

        with patch("gemsieve.ai.crews.crew_engage", return_value=mock_result) as mock_crew:
            from gemsieve.stages.engage import generate_engagement
            count = generate_engagement(
                db, model_spec="ollama:test-model",
                gem_id=gem_id, use_crew=True,
            )

        assert count == 1
        mock_crew.assert_called_once()

        row = db.execute(
            "SELECT * FROM engagement_drafts WHERE gem_id = ?",
            (gem_id,),
        ).fetchone()
        assert row is not None
        assert "SendGrid" in row["subject_line"]
        assert row["strategy"] == "audit"
        assert row["status"] == "draft"

    def test_engage_standard_mode_unaffected(self, db):
        """Without use_crew, the standard path is used."""
        gem_id = self._insert_gem_and_profile(db)

        mock_provider = MagicMock()
        mock_provider.complete.return_value = {
            "subject_line": "Test subject",
            "body": "Test body",
        }

        with patch("gemsieve.ai.get_provider") as mock_get:
            mock_get.return_value = (mock_provider, "test-model")
            from gemsieve.stages.engage import generate_engagement
            count = generate_engagement(
                db, model_spec="test:model",
                gem_id=gem_id, use_crew=False,
            )

        assert count == 1
        mock_provider.complete.assert_called_once()


@pytest.mark.skipif(not _crewai_available, reason="crewai not installed")
class TestCrewAILive:
    """Tests that require crewai to be installed (but mock the LLM)."""

    def test_make_llm_ollama(self):
        from gemsieve.ai.crews import _make_llm
        llm = _make_llm("ollama:mistral-nemo", {"ollama_base_url": "http://localhost:11434"})
        assert llm.model == "ollama/mistral-nemo"

    def test_make_llm_anthropic(self):
        from gemsieve.ai.crews import _make_llm
        llm = _make_llm("anthropic:claude-sonnet-4-5-20250514")
        assert llm.model == "anthropic/claude-sonnet-4-5-20250514"

    def test_make_llm_unknown_provider(self):
        from gemsieve.ai.crews import _make_llm
        with pytest.raises(ValueError, match="Unknown provider"):
            _make_llm("openai:gpt-4")
