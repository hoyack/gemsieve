"""Functional / cross-stage integration tests for GemSieve Phase 2 pipeline."""

from __future__ import annotations

import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import insert_message, setup_full_pipeline

ESP_RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "esp_rules.yaml")


# ---------------------------------------------------------------------------
# Group 1 — Full Pipeline Flow
# ---------------------------------------------------------------------------


class TestFullPipelineFlow:
    """End-to-end tests that run a message through the complete pipeline."""

    def test_full_pipeline_b2b_inquiry(self, db, sample_message):
        """B2B inquiry message flows through all stages to engagement draft."""
        # Run stages 0-5
        setup_full_pipeline(db, sample_message)

        # Verify metadata
        meta = db.execute(
            "SELECT * FROM parsed_metadata WHERE message_id = ?",
            (sample_message["message_id"],),
        ).fetchone()
        assert meta is not None
        assert meta["spf_result"] == "pass"
        assert meta["dmarc_result"] == "pass"

        # Verify content
        content = db.execute(
            "SELECT * FROM parsed_content WHERE message_id = ?",
            (sample_message["message_id"],),
        ).fetchone()
        assert content is not None
        assert content["body_clean"]
        # Signature should be stripped
        assert "Best regards" not in content["body_clean"]

        # Verify profile
        domain = sample_message["from_address"].split("@")[1]
        profile = db.execute(
            "SELECT * FROM sender_profiles WHERE sender_domain = ?", (domain,)
        ).fetchone()
        assert profile is not None
        assert profile["industry"] == "SaaS"
        # known_contacts depends on entity extraction (spaCy) which we skip;
        # verify the field is valid JSON instead
        contacts = json.loads(profile["known_contacts"]) if profile["known_contacts"] else []
        assert isinstance(contacts, list)
        assert profile["marketing_sophistication_avg"] > 0

        # Verify gems exist
        gems = db.execute("SELECT * FROM gems").fetchall()
        assert len(gems) > 0
        for gem in gems:
            explanation = json.loads(gem["explanation"])
            assert "estimated_value" in explanation
            assert "urgency" in explanation

        # Stage 7: Engagement (mocked AI)
        mock_provider = MagicMock()
        mock_provider.complete.return_value = {
            "subject_line": "Quick API audit",
            "body": "Hi Sarah, I noticed your API pricing page is missing tiers...",
        }
        with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
            from gemsieve.stages.engage import generate_engagement

            count = generate_engagement(db, gem_id=gems[0]["id"])
        assert count >= 1
        draft = db.execute("SELECT * FROM engagement_drafts").fetchone()
        assert draft is not None
        assert draft["body_text"]

    def test_full_pipeline_marketing_email(self, db, sample_marketing_message):
        """Marketing email correctly identifies ESP, tracking pixels, UTM, and creates gems."""
        setup_full_pipeline(
            db,
            sample_marketing_message,
            classification_kwargs={
                "sender_intent": "promotional",
                "partner_program_detected": True,
                "target_audience": "B2B companies",
            },
        )

        meta = db.execute(
            "SELECT * FROM parsed_metadata WHERE message_id = ?",
            (sample_marketing_message["message_id"],),
        ).fetchone()
        # SendGrid ESP
        assert meta["esp_identified"] is not None
        assert meta["is_bulk"]
        assert meta["precedence"] == "bulk"

        content = db.execute(
            "SELECT * FROM parsed_content WHERE message_id = ?",
            (sample_marketing_message["message_id"],),
        ).fetchone()
        assert content["tracking_pixel_count"] >= 1
        utm_campaigns = json.loads(content["utm_campaigns"])
        assert len(utm_campaigns) > 0

        # Should have gems (partner_program at minimum due to classification override)
        gems = db.execute("SELECT * FROM gems").fetchall()
        gem_types = {g["gem_type"] for g in gems}
        assert "partner_program" in gem_types

        # Segments should be assigned after segment stage
        from gemsieve.stages.segment import assign_segments, score_gems

        assign_segments(db)
        score_gems(db)
        segments = db.execute("SELECT * FROM sender_segments").fetchall()
        assert len(segments) > 0

    def test_new_metadata_fields_extracted(self, db):
        """All 4 new metadata fields (x_mailer, feedback_id, precedence, mail_server) are extracted."""
        msg = {
            "message_id": "msg_meta_fields",
            "thread_id": "thread_meta_fields",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "from_address": "test@newfields.com",
            "from_name": "Test Sender",
            "reply_to": "test@newfields.com",
            "to_addresses": json.dumps([{"name": "Me", "email": "me@example.com"}]),
            "cc_addresses": json.dumps([]),
            "subject": "Metadata test",
            "headers_raw": json.dumps({
                "from": ["Test Sender <test@newfields.com>"],
                "to": ["me@example.com"],
                "x-mailer": ["Thunderbird 91.0"],
                "feedback-id": ["campaign123:newfields:t1"],
                "precedence": ["bulk"],
                "received": ["from smtp.newfields.com [10.0.0.1] by mx.example.com"],
                "authentication-results": ["spf=pass; dmarc=pass"],
            }),
            "body_html": None,
            "body_text": "Test body",
            "labels": json.dumps(["INBOX"]),
            "snippet": "Test",
            "size_estimate": 500,
            "is_sent": False,
        }
        insert_message(db, msg)

        from gemsieve.stages.metadata import extract_metadata

        extract_metadata(db, esp_rules_path=ESP_RULES_PATH)

        meta = db.execute(
            "SELECT * FROM parsed_metadata WHERE message_id = ?",
            (msg["message_id"],),
        ).fetchone()
        assert meta["x_mailer"] == "Thunderbird 91.0"
        assert meta["feedback_id"] == "campaign123:newfields:t1"
        assert meta["precedence"] == "bulk"
        assert meta["mail_server"] is not None

    def test_footer_stripping_cleans_body(self, db):
        """Marketing footer is stripped from body_clean."""
        msg = {
            "message_id": "msg_footer",
            "thread_id": "thread_footer",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "from_address": "news@footertest.com",
            "from_name": "Footer Test",
            "reply_to": "news@footertest.com",
            "to_addresses": json.dumps([{"name": "Me", "email": "me@example.com"}]),
            "cc_addresses": json.dumps([]),
            "subject": "Newsletter with footer",
            "headers_raw": json.dumps({
                "from": ["Footer Test <news@footertest.com>"],
                "to": ["me@example.com"],
            }),
            "body_html": None,
            "body_text": (
                "Great news about our product launch!\n"
                "We have exciting features coming.\n"
                "Check out our roadmap for details.\n\n"
                "You are receiving this email because you signed up for our newsletter.\n"
                "To unsubscribe click here.\n"
                "123 Main Street, San Francisco, CA 94105"
            ),
            "labels": json.dumps(["INBOX"]),
            "snippet": "Great news",
            "size_estimate": 500,
            "is_sent": False,
        }
        insert_message(db, msg)

        from gemsieve.stages.content import parse_content

        parse_content(db)

        content = db.execute(
            "SELECT * FROM parsed_content WHERE message_id = ?",
            (msg["message_id"],),
        ).fetchone()
        assert "You are receiving this email" not in content["body_clean"]
        assert "Great news about our product launch" in content["body_clean"]


# ---------------------------------------------------------------------------
# Group 2 — Warm Signal Detection
# ---------------------------------------------------------------------------


class TestWarmSignalDetection:
    """Tests for dormant warm thread gem detection."""

    def test_dormant_warm_thread_gem_created(self, db, sample_dormant_thread_message):
        """Dormant thread with pricing + budget + meeting signals creates a gem."""
        setup_full_pipeline(db, sample_dormant_thread_message)

        # Simulate dormant state
        db.execute(
            "UPDATE threads SET days_dormant = 25, awaiting_response_from = 'user' WHERE thread_id = ?",
            (sample_dormant_thread_message["thread_id"],),
        )
        db.commit()

        # Re-detect gems with updated thread state
        from gemsieve.stages.profile import detect_gems

        detect_gems(db)

        gems = db.execute(
            "SELECT * FROM gems WHERE gem_type = 'dormant_warm_thread'"
        ).fetchall()
        assert len(gems) >= 1

        explanation = json.loads(gems[0]["explanation"])
        assert explanation["estimated_value"] in ("low", "medium", "high")
        assert explanation["urgency"] in ("low", "medium", "high")
        # Should have warm signal evidence
        signal_types = [s["signal"] for s in explanation.get("signals", [])]
        assert any("warm_" in s for s in signal_types)

    def test_dormant_no_warm_signals_no_gem(self, db):
        """Minimal dormant thread with no warm content should NOT create a gem."""
        msg = {
            "message_id": "msg_no_warm",
            "thread_id": "thread_no_warm",
            "date": "Mon, 01 Sep 2024 08:00:00 +0000",
            "from_address": "bob@neutral.com",
            "from_name": "Bob",
            "reply_to": "bob@neutral.com",
            "to_addresses": json.dumps([{"name": "Me", "email": "me@example.com"}]),
            "cc_addresses": json.dumps([]),
            "subject": "Re: Quick update",
            "headers_raw": json.dumps({
                "from": ["Bob <bob@neutral.com>"],
                "to": ["me@example.com"],
                "authentication-results": ["spf=pass; dmarc=pass"],
            }),
            "body_html": None,
            "body_text": "Thanks for the update. Looks good.",
            "labels": json.dumps(["INBOX"]),
            "snippet": "Thanks for the update",
            "size_estimate": 500,
            "is_sent": False,
        }
        setup_full_pipeline(db, msg)

        db.execute(
            "UPDATE threads SET days_dormant = 30, awaiting_response_from = 'user' WHERE thread_id = ?",
            (msg["thread_id"],),
        )
        db.commit()

        from gemsieve.stages.profile import detect_gems

        detect_gems(db)

        gems = db.execute(
            "SELECT * FROM gems WHERE gem_type = 'dormant_warm_thread'"
        ).fetchall()
        assert len(gems) == 0

    def test_dormant_transactional_filtered(self, db, sample_dormant_thread_message):
        """Dormant thread with transactional intent should NOT create a gem."""
        setup_full_pipeline(
            db,
            sample_dormant_thread_message,
            classification_kwargs={"sender_intent": "transactional"},
        )

        db.execute(
            "UPDATE threads SET days_dormant = 25, awaiting_response_from = 'user' WHERE thread_id = ?",
            (sample_dormant_thread_message["thread_id"],),
        )
        db.commit()

        from gemsieve.stages.profile import detect_gems

        detect_gems(db)

        gems = db.execute(
            "SELECT * FROM gems WHERE gem_type = 'dormant_warm_thread'"
        ).fetchall()
        assert len(gems) == 0


# ---------------------------------------------------------------------------
# Group 3 — Co-Marketing Detection
# ---------------------------------------------------------------------------


class TestCoMarketingDetection:
    """Tests for co-marketing gem detection."""

    def test_co_marketing_with_audience_overlap(self, db, sample_marketing_message):
        """Co-marketing gem created when audience overlaps with user's audience."""
        from gemsieve.config import EngagementConfig

        config = EngagementConfig(your_audience="B2B SaaS companies")
        setup_full_pipeline(
            db,
            sample_marketing_message,
            classification_kwargs={
                "sender_intent": "promotional",
                "target_audience": "B2B companies worldwide",
                "industry": "SaaS",
                "company_size_estimate": "medium",
            },
            engagement_config=config,
        )

        gems = db.execute(
            "SELECT * FROM gems WHERE gem_type = 'co_marketing'"
        ).fetchall()
        assert len(gems) >= 1

        explanation = json.loads(gems[0]["explanation"])
        assert explanation["estimated_value"] == "medium"
        assert explanation["urgency"] == "low"
        signal_types = [s["signal"] for s in explanation.get("signals", [])]
        assert "audience_overlap" in signal_types

    def test_co_marketing_no_audience_config(self, db, sample_marketing_message):
        """No co-marketing gem when your_audience is empty."""
        from gemsieve.config import EngagementConfig

        config = EngagementConfig(your_audience="")
        setup_full_pipeline(
            db,
            sample_marketing_message,
            classification_kwargs={
                "sender_intent": "promotional",
                "target_audience": "B2B companies",
                "industry": "SaaS",
                "company_size_estimate": "medium",
            },
            engagement_config=config,
        )

        gems = db.execute(
            "SELECT * FROM gems WHERE gem_type = 'co_marketing'"
        ).fetchall()
        assert len(gems) == 0


# ---------------------------------------------------------------------------
# Group 4 — Strategy-Gem Mapping
# ---------------------------------------------------------------------------


class TestStrategyGemMapping:
    """Tests for the strategy prompt mapping completeness."""

    def test_all_gem_types_have_strategy_and_prompt(self):
        """Every key in GEM_STRATEGY_MAP has a corresponding STRATEGY_PROMPTS entry."""
        from gemsieve.stages.engage import GEM_STRATEGY_MAP
        from gemsieve.ai.prompts import STRATEGY_PROMPTS, DEFAULT_ENGAGEMENT_PROMPT

        strategies_used = set(GEM_STRATEGY_MAP.values())
        for strategy in strategies_used:
            assert strategy in STRATEGY_PROMPTS, (
                f"Strategy '{strategy}' is used in GEM_STRATEGY_MAP but missing from STRATEGY_PROMPTS"
            )

    def test_different_strategies_produce_different_prompts(self, db, sample_marketing_message):
        """Different gem types produce different strategy prompts."""
        setup_full_pipeline(
            db,
            sample_marketing_message,
            classification_kwargs={
                "sender_intent": "promotional",
                "partner_program_detected": True,
                "company_size_estimate": "small",
                "marketing_sophistication": 2,
            },
        )

        gems = db.execute("SELECT * FROM gems").fetchall()
        gem_types = {g["gem_type"] for g in gems}
        # Should have at least weak_marketing_lead and partner_program
        assert "weak_marketing_lead" in gem_types
        assert "partner_program" in gem_types

        # Capture prompts sent to AI
        captured_prompts = []
        mock_provider = MagicMock()
        mock_provider.complete.side_effect = lambda prompt, model, **kw: (
            captured_prompts.append(prompt),
            {"subject_line": "test", "body": "test body"},
        )[1]

        with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
            from gemsieve.stages.engage import generate_engagement

            generate_engagement(db)

        assert len(captured_prompts) >= 2
        # Verify audit prompt vs partner prompt differ
        prompt_texts = "\n".join(captured_prompts)
        assert "I Audited Your Funnel" in prompt_texts
        assert "partner program application" in prompt_texts


# ---------------------------------------------------------------------------
# Group 5 — Classification Feedback Loop
# ---------------------------------------------------------------------------


class TestClassificationFeedback:
    """Tests for the retrain/few-shot correction system."""

    def _setup_for_classify(self, db, sample_message):
        """Insert message + metadata + content so classify has unprocessed rows."""
        insert_message(db, sample_message)
        from gemsieve.stages.metadata import extract_metadata
        from gemsieve.stages.content import parse_content

        extract_metadata(db, esp_rules_path=ESP_RULES_PATH)
        parse_content(db)

    def test_retrain_includes_few_shot_corrections(self, db, sample_message):
        """retrain=True appends CORRECTION examples from overrides to the prompt."""
        self._setup_for_classify(db, sample_message)

        # Insert an override
        db.execute(
            """INSERT INTO classification_overrides
               (message_id, sender_domain, field_name, original_value, corrected_value, override_scope)
               VALUES (?, ?, 'industry', 'SaaS', 'E-commerce', 'sender')""",
            (sample_message["message_id"], "acme.com"),
        )
        db.commit()

        captured = []
        mock_provider = MagicMock()
        mock_provider.complete.side_effect = lambda prompt, model, **kw: (
            captured.append(prompt),
            {
                "industry": "E-commerce",
                "company_size_estimate": "small",
                "marketing_sophistication": 4,
                "sender_intent": "cold_outreach",
                "product_type": "SaaS subscription",
                "product_description": "API tools",
                "pain_points_addressed": [],
                "target_audience": "developers",
                "partner_program_detected": False,
                "renewal_signal_detected": False,
                "confidence": 0.8,
            },
        )[1]

        with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
            from gemsieve.stages.classify import classify_messages

            classify_messages(db, retrain=True)

        assert len(captured) == 1
        assert "CORRECTION:" in captured[0]
        assert "Previous classification corrections" in captured[0]

    def test_message_override_beats_sender_override(self, db, sample_message):
        """Message-scoped override takes precedence over sender-scoped override."""
        self._setup_for_classify(db, sample_message)

        domain = sample_message["from_address"].split("@")[1]

        # Sender-scoped override
        db.execute(
            """INSERT INTO classification_overrides
               (message_id, sender_domain, field_name, original_value, corrected_value, override_scope)
               VALUES (NULL, ?, 'industry', 'SaaS', 'DevTools', 'sender')""",
            (domain,),
        )
        # Message-scoped override (should win)
        db.execute(
            """INSERT INTO classification_overrides
               (message_id, sender_domain, field_name, original_value, corrected_value, override_scope)
               VALUES (?, ?, 'industry', 'SaaS', 'E-commerce', 'message')""",
            (sample_message["message_id"], domain),
        )
        db.commit()

        mock_provider = MagicMock()
        mock_provider.complete.return_value = {
            "industry": "SaaS",
            "company_size_estimate": "small",
            "marketing_sophistication": 4,
            "sender_intent": "cold_outreach",
            "product_type": "SaaS subscription",
            "product_description": "API tools",
            "pain_points_addressed": [],
            "target_audience": "developers",
            "partner_program_detected": False,
            "renewal_signal_detected": False,
            "confidence": 0.8,
        }

        with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
            from gemsieve.stages.classify import classify_messages

            classify_messages(db)

        classification = db.execute(
            "SELECT * FROM ai_classification WHERE message_id = ?",
            (sample_message["message_id"],),
        ).fetchone()
        assert classification["industry"] == "E-commerce"
        assert classification["has_override"]

    def test_retrain_false_skips_few_shot(self, db, sample_message):
        """retrain=False does NOT include correction examples in the prompt."""
        self._setup_for_classify(db, sample_message)

        db.execute(
            """INSERT INTO classification_overrides
               (message_id, sender_domain, field_name, original_value, corrected_value, override_scope)
               VALUES (?, ?, 'industry', 'SaaS', 'E-commerce', 'sender')""",
            (sample_message["message_id"], "acme.com"),
        )
        db.commit()

        captured = []
        mock_provider = MagicMock()
        mock_provider.complete.side_effect = lambda prompt, model, **kw: (
            captured.append(prompt),
            {
                "industry": "SaaS",
                "company_size_estimate": "small",
                "marketing_sophistication": 4,
                "sender_intent": "cold_outreach",
                "product_type": "SaaS subscription",
                "product_description": "API tools",
                "pain_points_addressed": [],
                "target_audience": "developers",
                "partner_program_detected": False,
                "renewal_signal_detected": False,
                "confidence": 0.8,
            },
        )[1]

        with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
            from gemsieve.stages.classify import classify_messages

            classify_messages(db, retrain=False)

        assert len(captured) == 1
        assert "CORRECTION:" not in captured[0]


# ---------------------------------------------------------------------------
# Group 6 — Config Enforcement
# ---------------------------------------------------------------------------


def _spacy_available() -> bool:
    """Check if spaCy and en_core_web_sm are available."""
    try:
        import spacy
        spacy.load("en_core_web_sm")
        return True
    except Exception:
        return False


class TestConfigEnforcement:
    """Tests for engagement config limits and entity config toggles."""

    def test_preferred_strategies_and_daily_limit(self, db, sample_marketing_message):
        """preferred_strategies filters gems; max_outreach_per_day enforces daily cap."""
        from gemsieve.config import EngagementConfig

        setup_full_pipeline(
            db,
            sample_marketing_message,
            classification_kwargs={
                "sender_intent": "promotional",
                "partner_program_detected": True,
                "company_size_estimate": "small",
                "marketing_sophistication": 2,
            },
        )

        gems = db.execute("SELECT * FROM gems").fetchall()
        gem_types = {g["gem_type"] for g in gems}
        assert "weak_marketing_lead" in gem_types
        assert "partner_program" in gem_types

        mock_provider = MagicMock()
        mock_provider.complete.return_value = {
            "subject_line": "Test",
            "body": "Test body",
        }

        config = EngagementConfig(
            preferred_strategies=["audit"],
            max_outreach_per_day=1,
        )

        with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
            from gemsieve.stages.engage import generate_engagement

            count1 = generate_engagement(db, engagement_config=config)
        assert count1 == 1

        # Verify only audit strategy was used
        drafts = db.execute("SELECT * FROM engagement_drafts").fetchall()
        assert len(drafts) == 1
        assert drafts[0]["strategy"] == "audit"

        # Second call should hit daily limit
        with patch("gemsieve.ai.get_provider", return_value=(mock_provider, "test")):
            from gemsieve.stages.engage import generate_engagement

            count2 = generate_engagement(db, engagement_config=config)
        assert count2 == 0

    @pytest.mark.skipif(
        not _spacy_available(),
        reason="spaCy en_core_web_sm not installed",
    )
    def test_entity_config_disables_extraction(self, db, sample_message):
        """extract_monetary=False and extract_dates=False disables those extractions."""
        from gemsieve.config import EntityConfig
        from gemsieve.stages.entities import extract_entities

        insert_message(db, sample_message)
        from gemsieve.stages.metadata import extract_metadata
        from gemsieve.stages.content import parse_content

        extract_metadata(db, esp_rules_path=ESP_RULES_PATH)
        parse_content(db)

        config = EntityConfig(extract_monetary=False, extract_dates=False)
        extract_entities(db, entity_config=config)

        money_ents = db.execute(
            "SELECT * FROM extracted_entities WHERE entity_type = 'money' AND message_id = ?",
            (sample_message["message_id"],),
        ).fetchall()
        date_ents = db.execute(
            "SELECT * FROM extracted_entities WHERE entity_type = 'date' AND message_id = ?",
            (sample_message["message_id"],),
        ).fetchall()
        person_ents = db.execute(
            "SELECT * FROM extracted_entities WHERE entity_type = 'person' AND message_id = ?",
            (sample_message["message_id"],),
        ).fetchall()

        assert len(money_ents) == 0
        assert len(date_ents) == 0
        assert len(person_ents) > 0


# ---------------------------------------------------------------------------
# Group 7 — Segmentation Refinements
# ---------------------------------------------------------------------------


class TestSegmentationRefinements:
    """Tests for sub-segment classification logic."""

    def test_churned_vendor_subsegment(self, db):
        """Profile with last_contact > 180 days ago gets churned_vendor sub-segment."""
        msg = {
            "message_id": "msg_churned",
            "thread_id": "thread_churned",
            "date": "Mon, 01 Jan 2024 12:00:00 +0000",
            "from_address": "billing@oldvendor.com",
            "from_name": "Old Vendor",
            "reply_to": "billing@oldvendor.com",
            "to_addresses": json.dumps([{"name": "Me", "email": "me@example.com"}]),
            "cc_addresses": json.dumps([]),
            "subject": "Your subscription renewal",
            "headers_raw": json.dumps({
                "from": ["Old Vendor <billing@oldvendor.com>"],
                "to": ["me@example.com"],
                "authentication-results": ["spf=pass; dmarc=pass"],
            }),
            "body_html": None,
            "body_text": "Your subscription is coming up for renewal.",
            "labels": json.dumps(["INBOX"]),
            "snippet": "subscription renewal",
            "size_estimate": 500,
            "is_sent": False,
        }
        setup_full_pipeline(
            db,
            msg,
            classification_kwargs={
                "sender_intent": "transactional",
                "renewal_signal_detected": True,
            },
        )

        from gemsieve.stages.segment import assign_segments

        assign_segments(db)

        segments = db.execute(
            "SELECT * FROM sender_segments WHERE sender_domain = 'oldvendor.com' AND segment = 'spend_map'"
        ).fetchall()
        assert len(segments) >= 1
        sub_segments = {s["sub_segment"] for s in segments}
        assert "churned_vendor" in sub_segments

    def test_procurement_subsegment_from_entities(self, db, sample_procurement_message):
        """Procurement signal entities produce security_compliance and/or formal_rfp sub-segments."""
        setup_full_pipeline(
            db,
            sample_procurement_message,
            classification_kwargs={
                "sender_intent": "procurement",
            },
        )

        domain = "bigcorp.com"

        # Manually insert procurement_signal entities (simulating entity extraction)
        db.execute(
            """INSERT INTO extracted_entities
               (message_id, entity_type, entity_value, entity_normalized, context, confidence, source)
               VALUES (?, 'procurement_signal', 'SOC 2', 'security_review', 'security_review', 0.75, 'body')""",
            (sample_procurement_message["message_id"],),
        )
        db.execute(
            """INSERT INTO extracted_entities
               (message_id, entity_type, entity_value, entity_normalized, context, confidence, source)
               VALUES (?, 'procurement_signal', 'RFP', 'active_buying', 'active_buying', 0.75, 'body')""",
            (sample_procurement_message["message_id"],),
        )
        db.commit()

        # Re-build profile to include procurement in economic_segments
        from gemsieve.stages.profile import build_profiles, detect_gems

        build_profiles(db)
        detect_gems(db)

        # Verify procurement_map is in economic_segments
        profile = db.execute(
            "SELECT * FROM sender_profiles WHERE sender_domain = ?", (domain,)
        ).fetchone()
        segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
        assert "procurement_map" in segments

        from gemsieve.stages.segment import assign_segments

        assign_segments(db)

        proc_segments = db.execute(
            "SELECT * FROM sender_segments WHERE sender_domain = ? AND segment = 'procurement_map'",
            (domain,),
        ).fetchall()
        assert len(proc_segments) >= 1
        sub_segments = {s["sub_segment"] for s in proc_segments}
        assert "security_compliance" in sub_segments or "formal_rfp" in sub_segments
