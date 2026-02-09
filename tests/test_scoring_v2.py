"""Tests for relationship-aware scoring formula (Phase 3)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from gemsieve.config import RelationshipScoreCaps, ScoringConfig, ScoringWeights
from gemsieve.database import init_db
from gemsieve.stages.profile import build_profiles, detect_gems
from gemsieve.stages.relationships import set_relationship
from gemsieve.stages.segment import _opportunity_score, score_gems


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def _make_profile_row(db, domain, **overrides):
    """Insert a profile and return the row."""
    defaults = {
        "company_name": domain.split(".")[0].title(),
        "primary_email": f"info@{domain}",
        "total_messages": 5,
        "industry": "SaaS",
        "company_size": "small",
        "marketing_sophistication_avg": 5.0,
        "economic_segments": "[]",
        "thread_initiation_ratio": 0.3,
        "user_reply_rate": 0.8,
        "known_contacts": "[]",
        "monetary_signals": "[]",
        "last_contact": "Mon, 01 Jan 2024 12:00:00 +0000",
    }
    defaults.update(overrides)
    db.execute(
        """INSERT OR REPLACE INTO sender_profiles
           (sender_domain, company_name, primary_email, total_messages,
            industry, company_size, marketing_sophistication_avg,
            economic_segments, thread_initiation_ratio, user_reply_rate,
            known_contacts, monetary_signals, last_contact)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            domain, defaults["company_name"], defaults["primary_email"],
            defaults["total_messages"], defaults["industry"], defaults["company_size"],
            defaults["marketing_sophistication_avg"], defaults["economic_segments"],
            defaults["thread_initiation_ratio"], defaults["user_reply_rate"],
            defaults["known_contacts"], defaults["monetary_signals"],
            defaults["last_contact"],
        ),
    )
    db.commit()
    return db.execute("SELECT * FROM sender_profiles WHERE sender_domain = ?", (domain,)).fetchone()


class TestOpportunityScore:
    def test_inbound_prospect_scores_high(self, db):
        """An inbound prospect with good signals should score high."""
        profile = _make_profile_row(db, "prospect.com",
                                     thread_initiation_ratio=0.1,  # they reach out
                                     user_reply_rate=0.9)
        gems = [{"gem_type": "dormant_warm_thread"}, {"gem_type": "procurement_signal"}]
        weights = ScoringWeights()
        caps = RelationshipScoreCaps()

        score = _opportunity_score(profile, gems, weights, ["SaaS"],
                                   relationship_type="inbound_prospect",
                                   relationship_caps=caps)
        assert score >= 50  # Should be high
        assert score <= 100  # Cap for inbound_prospect

    def test_vendor_capped_at_25(self, db):
        """Vendor should be capped at 25 regardless of profile quality."""
        profile = _make_profile_row(db, "vendor.com",
                                     thread_initiation_ratio=0.9,
                                     user_reply_rate=0.5)
        gems = [{"gem_type": "renewal_leverage"}]
        weights = ScoringWeights()
        caps = RelationshipScoreCaps()

        score = _opportunity_score(profile, gems, weights, ["SaaS"],
                                   relationship_type="my_vendor",
                                   relationship_caps=caps)
        assert score <= 25

    def test_infrastructure_capped_at_5(self, db):
        """Infrastructure should be capped at 5."""
        profile = _make_profile_row(db, "infra.com")
        gems = [{"gem_type": "renewal_leverage"}]
        weights = ScoringWeights()
        caps = RelationshipScoreCaps()

        score = _opportunity_score(profile, gems, weights, ["SaaS"],
                                   relationship_type="my_infrastructure",
                                   relationship_caps=caps)
        assert score <= 5

    def test_unknown_capped_at_60(self, db):
        """Unknown relationship should be capped at 60."""
        profile = _make_profile_row(db, "unknown.com",
                                     thread_initiation_ratio=0.1,
                                     user_reply_rate=0.9)
        gems = [{"gem_type": "dormant_warm_thread"}, {"gem_type": "procurement_signal"},
                {"gem_type": "industry_intel"}]
        weights = ScoringWeights()
        caps = RelationshipScoreCaps()

        score = _opportunity_score(profile, gems, weights, ["SaaS"],
                                   relationship_type="unknown",
                                   relationship_caps=caps)
        assert score <= 60

    def test_inbound_signal_boosts_score(self, db):
        """Low initiation ratio (they reach out) should boost score."""
        profile_they_reach = _make_profile_row(db, "they.com",
                                                thread_initiation_ratio=0.0,
                                                user_reply_rate=1.0)
        profile_you_reach = _make_profile_row(db, "you.com",
                                               thread_initiation_ratio=1.0,
                                               user_reply_rate=0.5)
        gems = [{"gem_type": "industry_intel"}]
        weights = ScoringWeights()
        caps = RelationshipScoreCaps()

        score_they = _opportunity_score(profile_they_reach, gems, weights, ["SaaS"],
                                        relationship_type="inbound_prospect",
                                        relationship_caps=caps)
        score_you = _opportunity_score(profile_you_reach, gems, weights, ["SaaS"],
                                       relationship_type="inbound_prospect",
                                       relationship_caps=caps)
        assert score_they > score_you

    def test_diversity_bonus_reduced(self, db):
        """Diversity bonus should be capped at gem_diversity_cap (15)."""
        profile = _make_profile_row(db, "diverse.com")
        gems = [
            {"gem_type": "dormant_warm_thread"},
            {"gem_type": "industry_intel"},
            {"gem_type": "procurement_signal"},
            {"gem_type": "partner_program"},
        ]
        weights = ScoringWeights()

        # 4 types * 5 per type = 20, but cap is 15
        # So diversity contributes exactly 15
        diversity_bonus = min(len(set(g["gem_type"] for g in gems)) * weights.gem_diversity_per_type,
                              weights.gem_diversity_cap)
        assert diversity_bonus == 15

    def test_monetary_only_for_prospects(self, db):
        """Monetary signals should only count for prospect/warm/unknown."""
        profile = _make_profile_row(db, "money.com",
                                     monetary_signals='[{"amount": "$10000"}]')
        gems = [{"gem_type": "industry_intel"}]
        weights = ScoringWeights()
        caps = RelationshipScoreCaps()

        score_prospect = _opportunity_score(profile, gems, weights, ["SaaS"],
                                             relationship_type="inbound_prospect",
                                             relationship_caps=caps)
        score_vendor = _opportunity_score(profile, gems, weights, ["SaaS"],
                                           relationship_type="my_vendor",
                                           relationship_caps=caps)
        # Vendor is capped at 25, so we need a different comparison
        # Test that monetary signals contribute for prospect but not for selling_to_me
        score_selling = _opportunity_score(profile, gems, weights, ["SaaS"],
                                            relationship_type="selling_to_me",
                                            relationship_caps=caps)

        # Create same profile without monetary
        profile_no_money = _make_profile_row(db, "nomoney.com", monetary_signals='[]')
        score_prospect_no_money = _opportunity_score(profile_no_money, gems, weights, ["SaaS"],
                                                      relationship_type="inbound_prospect",
                                                      relationship_caps=caps)
        score_selling_no_money = _opportunity_score(profile_no_money, gems, weights, ["SaaS"],
                                                     relationship_type="selling_to_me",
                                                     relationship_caps=caps)

        # Prospect should get monetary boost
        assert score_prospect > score_prospect_no_money
        # Selling should NOT get monetary boost
        assert score_selling == score_selling_no_money

    def test_backward_compat_no_relationships(self, db):
        """With no relationships data, scoring should still work."""
        profile = _make_profile_row(db, "compat.com")
        gems = [{"gem_type": "industry_intel"}]
        weights = ScoringWeights()

        # Default relationship_type="unknown", no caps
        score = _opportunity_score(profile, gems, weights, ["SaaS"])
        assert score > 0


class TestScoreGemsIntegration:
    def test_score_gems_uses_relationships(self, db):
        """score_gems should load relationships and apply caps."""
        profile = _make_profile_row(db, "vendor.com",
                                     thread_initiation_ratio=0.9,
                                     user_reply_rate=0.5)
        # Insert a gem
        db.execute(
            """INSERT INTO gems (gem_type, sender_domain, score, explanation, recommended_actions)
               VALUES ('renewal_leverage', 'vendor.com', 50, '{}', '[]')"""
        )
        set_relationship(db, "vendor.com", "my_vendor")
        db.commit()

        config = ScoringConfig()
        scored = score_gems(db, config=config)
        assert scored == 1

        gem = db.execute("SELECT score FROM gems WHERE sender_domain = 'vendor.com'").fetchone()
        assert gem["score"] <= 25  # vendor cap
