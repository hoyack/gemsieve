"""Stage 6: Segment assignment and opportunity scoring."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import yaml

from gemsieve.config import RelationshipScoreCaps, ScoringConfig


def assign_segments(db: sqlite3.Connection) -> int:
    """Assign economic segments to all sender profiles.

    Returns count of segment assignments.
    """
    # Clear existing assignments for re-run
    db.execute("DELETE FROM sender_segments")

    profiles = db.execute("SELECT * FROM sender_profiles").fetchall()
    assignments = 0

    for profile in profiles:
        domain = profile["sender_domain"]
        segments = []
        try:
            segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
        except (json.JSONDecodeError, TypeError):
            pass

        # Assign based on stored economic_segments from profile building
        segment_map = {
            "spend_map": _classify_spend_subsegment(db, profile),
            "partner_map": _classify_partner_subsegment(db, profile),
            "prospect_map": _classify_prospect_subsegment(db, profile),
            "distribution_map": _classify_distribution_subsegment(db, profile),
            "procurement_map": _classify_procurement_subsegment(db, profile),
        }

        for segment in segments:
            sub_segments = segment_map.get(segment, [("general", 0.5)])
            for sub_seg, confidence in sub_segments:
                db.execute(
                    """INSERT OR REPLACE INTO sender_segments
                       (sender_domain, segment, sub_segment, confidence)
                       VALUES (?, ?, ?, ?)""",
                    (domain, segment, sub_seg, confidence),
                )
                assignments += 1

        # Check for dormant threads (separate from profile segments)
        threads = db.execute(
            """SELECT t.thread_id FROM threads t
               JOIN messages m ON t.thread_id = m.thread_id
               JOIN parsed_metadata pm ON m.message_id = pm.message_id
               WHERE pm.sender_domain = ? AND t.days_dormant >= 14
                 AND t.awaiting_response_from = 'user'
               GROUP BY t.thread_id""",
            (domain,),
        ).fetchall()

        if threads:
            db.execute(
                """INSERT OR REPLACE INTO sender_segments
                   (sender_domain, segment, sub_segment, confidence)
                   VALUES (?, 'dormant_threads', 'unanswered', 0.9)""",
                (domain,),
            )
            assignments += 1

    db.commit()
    return assignments


def score_gems(db: sqlite3.Connection, config: ScoringConfig | None = None) -> int:
    """Apply relationship-aware opportunity scoring formula to all gems.

    Returns count of gems scored.
    """
    if config is None:
        config = ScoringConfig()

    weights = config.weights
    target_industries = config.target_industries
    caps = config.relationship_caps

    # Load sender relationships
    rel_rows = db.execute("SELECT sender_domain, relationship_type FROM sender_relationships").fetchall()
    relationships = {r["sender_domain"]: r["relationship_type"] for r in rel_rows}

    gems = db.execute("SELECT id, sender_domain FROM gems").fetchall()
    scored = 0

    for gem_row in gems:
        gem_id = gem_row["id"]
        domain = gem_row["sender_domain"]

        profile = db.execute(
            "SELECT * FROM sender_profiles WHERE sender_domain = ?", (domain,)
        ).fetchone()

        if not profile:
            continue

        # Get all gems for this sender
        sender_gems = db.execute(
            "SELECT gem_type FROM gems WHERE sender_domain = ?", (domain,)
        ).fetchall()

        rel_type = relationships.get(domain, "unknown")
        score = _opportunity_score(profile, sender_gems, weights, target_industries,
                                   relationship_type=rel_type, relationship_caps=caps)

        db.execute("UPDATE gems SET score = ? WHERE id = ?", (score, gem_id))
        scored += 1

    db.commit()
    return scored


def evaluate_custom_segments(
    db: sqlite3.Connection, segments_file: str = "segments.yaml"
) -> int:
    """Evaluate custom segment rules from YAML config.

    Returns count of custom segment assignments.
    """
    try:
        with open(segments_file) as f:
            config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return 0

    custom_segments = config.get("custom_segments", [])
    if not custom_segments:
        return 0

    profiles = db.execute("SELECT * FROM sender_profiles").fetchall()
    assigned = 0

    for seg_def in custom_segments:
        name = seg_def.get("name", "unnamed")
        rules = seg_def.get("rules", {})
        priority = seg_def.get("priority", "warm")

        for profile in profiles:
            if _matches_rules(profile, rules, db):
                db.execute(
                    """INSERT OR REPLACE INTO sender_segments
                       (sender_domain, segment, sub_segment, confidence)
                       VALUES (?, ?, ?, ?)""",
                    (profile["sender_domain"], f"custom:{name}", priority, 0.8),
                )
                assigned += 1

    db.commit()
    return assigned


def _opportunity_score(
    profile, sender_gems: list, weights, target_industries: list[str],
    relationship_type: str = "unknown",
    relationship_caps: RelationshipScoreCaps | None = None,
) -> int:
    """Compute relationship-aware opportunity score for a sender.

    New formula (Phase 3):
    1. Inbound Signal Score (max 30): based on who-initiates and user engagement
    2. Base Profile Score (max 40): reachability + relevance + recency + contacts + monetary
    3. Gem Bonus (max 30): diversity + specific bonuses
    4. Apply relationship cap
    """
    if relationship_caps is None:
        relationship_caps = RelationshipScoreCaps()

    score = 0.0

    # --- 1. Inbound Signal Score (max 30) ---
    initiation = profile["thread_initiation_ratio"]
    reply_rate = profile["user_reply_rate"]

    if initiation is not None:
        # Lower initiation = they reach out more = better prospect signal
        score += (1.0 - initiation) * weights.inbound_initiation
    if reply_rate is not None:
        score += reply_rate * weights.inbound_engagement

    # --- 2. Base Profile Score (max 40) ---
    # Reachability
    size = profile["company_size"] or ""
    if size == "small":
        score += weights.reachability
    elif size == "medium":
        score += weights.reachability * 0.67
    else:
        score += weights.reachability * 0.2

    # Relevance
    industry = profile["industry"] or ""
    if industry in target_industries:
        score += weights.relevance
    else:
        score += weights.relevance * 0.3

    # Recency
    last_contact = profile["last_contact"]
    if last_contact:
        try:
            from email.utils import parsedate_to_datetime
            last_dt = parsedate_to_datetime(last_contact)
            days = (datetime.now(timezone.utc) - last_dt).days
            if days <= 30:
                score += weights.recency
            elif days <= 90:
                score += weights.recency * 0.5
        except Exception:
            pass

    # Known contacts
    contacts = []
    try:
        contacts = json.loads(profile["known_contacts"]) if profile["known_contacts"] else []
    except (json.JSONDecodeError, TypeError):
        pass
    if contacts and any(c.get("role") for c in contacts):
        score += weights.known_contacts
    elif contacts:
        score += weights.known_contacts * 0.2

    # Monetary signals (only for prospect/warm/unknown relationships)
    monetary_eligible = {"inbound_prospect", "warm_contact", "unknown", "potential_partner"}
    if relationship_type in monetary_eligible:
        monetary = []
        try:
            monetary = json.loads(profile["monetary_signals"]) if profile["monetary_signals"] else []
        except (json.JSONDecodeError, TypeError):
            pass
        if monetary:
            score += weights.monetary_signals

    # --- 3. Gem Bonus (max 30) ---
    gem_types = set(g["gem_type"] for g in sender_gems)
    score += min(len(gem_types) * weights.gem_diversity_per_type, weights.gem_diversity_cap)

    # Specific gem bonuses
    if "dormant_warm_thread" in gem_types:
        score += weights.dormant_thread_bonus
    if "partner_program" in gem_types:
        score += weights.partner_bonus
    if "procurement_signal" in gem_types:
        score += weights.procurement_bonus

    # --- 4. Apply relationship cap ---
    cap = getattr(relationship_caps, relationship_type, 100)
    return min(int(score), cap, 100)


def decompose_opportunity_score(
    profile, sender_gems: list, weights, target_industries: list[str],
    relationship_type: str = "unknown",
    relationship_caps: RelationshipScoreCaps | None = None,
) -> dict:
    """Decompose opportunity score into tiers and components.

    Same inputs as _opportunity_score(), returns structured breakdown instead of int.
    """
    if relationship_caps is None:
        relationship_caps = RelationshipScoreCaps()

    # --- 1. Inbound Signal Score (max 30) ---
    initiation = profile["thread_initiation_ratio"]
    reply_rate = profile["user_reply_rate"]

    initiation_val = 0.0
    initiation_detail = "No initiation data"
    if initiation is not None:
        initiation_val = (1.0 - initiation) * weights.inbound_initiation
        initiation_detail = f"Initiation ratio {initiation:.2f} (lower = they reach out more)"

    engagement_val = 0.0
    engagement_detail = "No reply rate data"
    if reply_rate is not None:
        engagement_val = reply_rate * weights.inbound_engagement
        engagement_detail = f"User reply rate {reply_rate:.2f}"

    inbound_total = initiation_val + engagement_val

    # --- 2. Base Profile Score (max 40) ---
    # Reachability
    size = profile["company_size"] or ""
    if size == "small":
        reachability_val = float(weights.reachability)
        reachability_detail = "Small company (full score)"
    elif size == "medium":
        reachability_val = weights.reachability * 0.67
        reachability_detail = "Medium company (67%)"
    else:
        reachability_val = weights.reachability * 0.2
        reachability_detail = f"Large/unknown company size '{size}' (20%)"

    # Relevance
    industry = profile["industry"] or ""
    if industry in target_industries:
        relevance_val = float(weights.relevance)
        relevance_detail = f"Target industry: {industry}"
    else:
        relevance_val = weights.relevance * 0.3
        relevance_detail = f"Non-target industry: {industry or 'unknown'} (30%)"

    # Recency
    recency_val = 0.0
    recency_detail = "No last contact date"
    last_contact = profile["last_contact"]
    if last_contact:
        try:
            from email.utils import parsedate_to_datetime
            last_dt = parsedate_to_datetime(last_contact)
            days = (datetime.now(timezone.utc) - last_dt).days
            if days <= 30:
                recency_val = float(weights.recency)
                recency_detail = f"Last contact {days}d ago (within 30d, full score)"
            elif days <= 90:
                recency_val = weights.recency * 0.5
                recency_detail = f"Last contact {days}d ago (within 90d, 50%)"
            else:
                recency_detail = f"Last contact {days}d ago (>90d, no score)"
        except Exception:
            recency_detail = "Failed to parse last contact date"

    # Known contacts
    contacts = []
    try:
        contacts = json.loads(profile["known_contacts"]) if profile["known_contacts"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    known_contacts_val = 0.0
    if contacts and any(c.get("role") for c in contacts):
        known_contacts_val = float(weights.known_contacts)
        known_contacts_detail = f"{len(contacts)} contacts with roles"
    elif contacts:
        known_contacts_val = weights.known_contacts * 0.2
        known_contacts_detail = f"{len(contacts)} contacts without roles (20%)"
    else:
        known_contacts_detail = "No known contacts"

    # Monetary signals
    monetary_eligible = {"inbound_prospect", "warm_contact", "unknown", "potential_partner"}
    monetary_val = 0.0
    if relationship_type in monetary_eligible:
        monetary = []
        try:
            monetary = json.loads(profile["monetary_signals"]) if profile["monetary_signals"] else []
        except (json.JSONDecodeError, TypeError):
            pass
        if monetary:
            monetary_val = float(weights.monetary_signals)
            monetary_detail = f"{len(monetary)} monetary signals detected"
        else:
            monetary_detail = "No monetary signals"
    else:
        monetary_detail = f"Not eligible ({relationship_type})"

    base_total = reachability_val + relevance_val + recency_val + known_contacts_val + monetary_val

    # --- 3. Gem Bonus (max 30) ---
    gem_types = set(g["gem_type"] for g in sender_gems)
    diversity_val = min(len(gem_types) * weights.gem_diversity_per_type, weights.gem_diversity_cap)
    diversity_detail = f"{len(gem_types)} unique type(s) x {weights.gem_diversity_per_type} (cap {weights.gem_diversity_cap})"

    dormant_val = float(weights.dormant_thread_bonus) if "dormant_warm_thread" in gem_types else 0.0
    dormant_detail = "Dormant warm thread detected" if dormant_val else "No dormant warm thread"

    partner_val = float(weights.partner_bonus) if "partner_program" in gem_types else 0.0
    partner_detail = "Partner program gem detected" if partner_val else "No partner program gem"

    procurement_val = float(weights.procurement_bonus) if "procurement_signal" in gem_types else 0.0
    procurement_detail = "Procurement signal detected" if procurement_val else "No procurement signal"

    gem_total = diversity_val + dormant_val + partner_val + procurement_val

    # --- 4. Cap ---
    total_raw = inbound_total + base_total + gem_total
    cap = getattr(relationship_caps, relationship_type, 100)
    effective_cap = min(cap, 100)
    total_capped = min(int(total_raw), effective_cap)

    return {
        "total_raw": round(total_raw, 1),
        "total_capped": total_capped,
        "cap_applied": effective_cap,
        "cap_source": relationship_type,
        "cap_reduced_by": max(0, int(total_raw) - total_capped),
        "tiers": {
            "inbound_signal": {
                "label": "Inbound Signal Score", "max": 30,
                "value": round(inbound_total, 1),
                "components": {
                    "initiation": {
                        "label": "They Reach Out", "max": weights.inbound_initiation,
                        "value": round(initiation_val, 1), "detail": initiation_detail,
                    },
                    "engagement": {
                        "label": "User Engagement", "max": weights.inbound_engagement,
                        "value": round(engagement_val, 1), "detail": engagement_detail,
                    },
                },
            },
            "base_profile": {
                "label": "Base Profile Score", "max": 40,
                "value": round(base_total, 1),
                "components": {
                    "reachability": {
                        "label": "Reachability", "max": weights.reachability,
                        "value": round(reachability_val, 1), "detail": reachability_detail,
                    },
                    "relevance": {
                        "label": "Relevance", "max": weights.relevance,
                        "value": round(relevance_val, 1), "detail": relevance_detail,
                    },
                    "recency": {
                        "label": "Recency", "max": weights.recency,
                        "value": round(recency_val, 1), "detail": recency_detail,
                    },
                    "known_contacts": {
                        "label": "Known Contacts", "max": weights.known_contacts,
                        "value": round(known_contacts_val, 1), "detail": known_contacts_detail,
                    },
                    "monetary_signals": {
                        "label": "Monetary Signals", "max": weights.monetary_signals,
                        "value": round(monetary_val, 1), "detail": monetary_detail,
                    },
                },
            },
            "gem_bonus": {
                "label": "Gem Bonus", "max": 30,
                "value": round(gem_total, 1),
                "components": {
                    "diversity": {
                        "label": "Type Diversity", "max": weights.gem_diversity_cap,
                        "value": round(diversity_val, 1), "detail": diversity_detail,
                    },
                    "dormant_thread": {
                        "label": "Dormant Thread", "max": weights.dormant_thread_bonus,
                        "value": round(dormant_val, 1), "detail": dormant_detail,
                    },
                    "partner": {
                        "label": "Partner", "max": weights.partner_bonus,
                        "value": round(partner_val, 1), "detail": partner_detail,
                    },
                    "procurement": {
                        "label": "Procurement", "max": weights.procurement_bonus,
                        "value": round(procurement_val, 1), "detail": procurement_detail,
                    },
                },
            },
        },
    }


def _classify_spend_subsegment(db, profile) -> list[tuple[str, float]]:
    """Classify spend map sub-segments with churned vendor detection."""
    subs = []
    renewal_dates = []
    try:
        renewal_dates = json.loads(profile["renewal_dates"]) if profile["renewal_dates"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    # Churned vendor detection: if last_contact > 180 days ago
    last_contact = profile["last_contact"]
    is_churned = False
    if last_contact:
        try:
            from email.utils import parsedate_to_datetime
            last_dt = parsedate_to_datetime(last_contact)
            days = (datetime.now(timezone.utc) - last_dt).days
            if days > 180:
                is_churned = True
        except Exception:
            pass

    if is_churned:
        subs.append(("churned_vendor", 0.8))
    elif renewal_dates:
        subs.append(("upcoming_renewal", 0.9))
    else:
        subs.append(("active_subscription", 0.7))
    return subs or [("general", 0.5)]


def _classify_partner_subsegment(db, profile) -> list[tuple[str, float]]:
    """Classify partner map sub-segments."""
    urls = []
    try:
        urls = json.loads(profile["partner_program_urls"]) if profile["partner_program_urls"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    if urls:
        return [("referral_program", 0.8)]
    return [("general", 0.5)]


def _classify_prospect_subsegment(db, profile) -> list[tuple[str, float]]:
    """Classify prospect map sub-segments."""
    soph = profile["marketing_sophistication_avg"] or 0
    if soph <= 3:
        return [("hot_lead", 0.8)]
    elif soph <= 5:
        return [("warm_prospect", 0.6)]
    return [("intelligence_value", 0.4)]


def _classify_distribution_subsegment(db, profile) -> list[tuple[str, float]]:
    """Classify distribution map sub-segments using offer_type_distribution."""
    offer_dist = {}
    try:
        offer_dist = json.loads(profile["offer_type_distribution"]) if profile["offer_type_distribution"] else {}
    except (json.JSONDecodeError, TypeError):
        pass

    subs = []
    if "newsletter" in offer_dist or "digest" in offer_dist:
        subs.append(("newsletter", 0.8))
    if "event_invitation" in offer_dist or "event" in offer_dist or "webinar" in offer_dist:
        subs.append(("event_organizer", 0.7))
    if "community" in offer_dist or "forum" in offer_dist:
        subs.append(("community", 0.6))

    return subs or [("newsletter", 0.7)]


def _classify_procurement_subsegment(db, profile) -> list[tuple[str, float]]:
    """Classify procurement map sub-segments using entity data."""
    domain = profile["sender_domain"]

    procurement_entities = db.execute(
        """SELECT ee.entity_value, ee.entity_normalized
           FROM extracted_entities ee
           JOIN parsed_metadata pm ON ee.message_id = pm.message_id
           WHERE pm.sender_domain = ? AND ee.entity_type = 'procurement_signal'""",
        (domain,),
    ).fetchall()

    if not procurement_entities:
        return [("evaluation", 0.6)]

    keywords = " ".join(e["entity_value"].lower() for e in procurement_entities)

    subs = []
    if any(kw in keywords for kw in ("security", "compliance", "soc", "gdpr", "hipaa")):
        subs.append(("security_compliance", 0.8))
    if any(kw in keywords for kw in ("rfp", "request for proposal", "rfq", "bid")):
        subs.append(("formal_rfp", 0.9))
    if any(kw in keywords for kw in ("evaluation", "trial", "poc", "proof of concept", "pilot")):
        subs.append(("evaluation", 0.7))

    return subs or [("evaluation", 0.6)]


def _matches_rules(profile, rules: dict, db: sqlite3.Connection) -> bool:
    """Check if a sender profile matches custom segment rules."""
    for field, expected in rules.items():
        if field == "segment_includes":
            segments = []
            try:
                segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
            except (json.JSONDecodeError, TypeError):
                pass
            if expected not in segments:
                return False
            continue

        if field == "renewal_date_within_days":
            # Would need date parsing — simplified check
            renewal_dates = []
            try:
                renewal_dates = json.loads(profile["renewal_dates"]) if profile["renewal_dates"] else []
            except (json.JSONDecodeError, TypeError):
                pass
            if not renewal_dates:
                return False
            continue

        # Direct field comparison
        actual = profile[field] if field in profile.keys() else None
        if actual is None:
            return False

        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif isinstance(expected, dict):
            if "lt" in expected and not (isinstance(actual, (int, float)) and actual < expected["lt"]):
                return False
            if "gt" in expected and not (isinstance(actual, (int, float)) and actual > expected["gt"]):
                return False
        elif isinstance(expected, bool):
            if bool(actual) != expected:
                return False
        else:
            if str(actual) != str(expected):
                return False

    return True
