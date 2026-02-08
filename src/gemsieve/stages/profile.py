"""Stage 5: Sender profiling and gem detection."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timezone

from gemsieve.models import GemType


# --- Warm Signal Detection (Spec §2) ---

WARM_SIGNALS = {
    "pricing": [
        re.compile(r"\b(?:pricing|price|cost|quote|budget|investment)\b", re.IGNORECASE),
    ],
    "meeting_request": [
        re.compile(r"\b(?:schedule|call|meeting|demo|zoom|calendly|book a time)\b", re.IGNORECASE),
    ],
    "explicit_ask": [
        re.compile(r"\b(?:interested in|looking for|evaluating|considering)\b", re.IGNORECASE),
    ],
    "follow_up": [
        re.compile(r"\b(?:following up|circling back|checking in|just wanted to)\b", re.IGNORECASE),
    ],
    "decision_maker": [
        re.compile(r"\b(?:CEO|CTO|VP|Director|Head of|Founder)\b"),
    ],
    "budget_indicator": [
        re.compile(r"\$[\d,]+(?:\.\d{2})?", re.IGNORECASE),
        re.compile(r"\b\d+[kK]\s*(?:ARR|MRR|budget)\b", re.IGNORECASE),
    ],
}


# --- Distribution Content Signals (Spec §14) ---

DISTRIBUTION_CONTENT_SIGNALS = [
    re.compile(r"\bguest post\b", re.IGNORECASE),
    re.compile(r"\bspeaker application\b", re.IGNORECASE),
    re.compile(r"\bcall for papers\b", re.IGNORECASE),
    re.compile(r"\bpodcast interview\b", re.IGNORECASE),
    re.compile(r"\bsponsorship\b", re.IGNORECASE),
    re.compile(r"\bcontributor\b", re.IGNORECASE),
    re.compile(r"\bsubmit (?:your|a) (?:talk|session|abstract)\b", re.IGNORECASE),
    re.compile(r"\bfeature (?:story|article|piece)\b", re.IGNORECASE),
]


# --- Deterministic Sophistication Score (Spec §7) ---

def compute_sophistication_score(
    esp: str | None,
    has_personalization: bool,
    has_utm: bool,
    template_complexity: int,
    spf: str | None,
    dkim: str | None,
    dmarc: str | None,
    has_unsubscribe: bool,
    unique_campaign_count: int,
) -> int:
    """Compute a deterministic 10-point marketing sophistication score.

    Formula:
    - ESP tier (1-3): enterprise=3, mid=2, basic/none=1
    - Personalization (0-2): has tokens = 2, else 0
    - UTM tracking (0-1): uses UTM = 1
    - Template quality (0-1): complexity >= 50 = 1
    - Segmentation signals (0-1): >= 3 unique campaigns = 1
    - Authentication (0-1): SPF+DKIM+DMARC all pass = 1
    - Unsubscribe (0-1): has list-unsubscribe = 1
    """
    score = 0

    # ESP tier (1-3)
    enterprise_esps = {"HubSpot", "Klaviyo", "ActiveCampaign", "salesforce_mc", "Marketo", "Pardot"}
    mid_esps = {"SendGrid", "amazon_ses", "postmark", "Mailgun", "SparkPost"}
    if esp in enterprise_esps:
        score += 3
    elif esp in mid_esps:
        score += 2
    else:
        score += 1

    # Personalization (0-2)
    if has_personalization:
        score += 2

    # UTM tracking (0-1)
    if has_utm:
        score += 1

    # Template quality (0-1)
    if template_complexity >= 50:
        score += 1

    # Segmentation signals (0-1)
    if unique_campaign_count >= 3:
        score += 1

    # Authentication (0-1)
    if spf == "pass" and dmarc == "pass" and dkim:
        score += 1

    # Unsubscribe (0-1)
    if has_unsubscribe:
        score += 1

    return min(score, 10)


def build_profiles(db: sqlite3.Connection) -> int:
    """Build/update sender profiles by aggregating all message-level data per domain.

    Returns count of profiles built.
    """
    # Get all unique sender domains from parsed_metadata
    domains = db.execute(
        """SELECT DISTINCT sender_domain FROM parsed_metadata
           WHERE sender_domain != ''"""
    ).fetchall()

    built = 0
    for row in domains:
        domain = row["sender_domain"]
        _build_single_profile(db, domain)
        built += 1

    db.commit()
    return built


def _build_single_profile(db: sqlite3.Connection, domain: str) -> None:
    """Build a profile for a single sender domain."""
    # Get all messages from this domain
    messages = db.execute(
        """SELECT m.message_id, m.from_address, m.from_name, m.reply_to, m.date
           FROM messages m
           JOIN parsed_metadata pm ON m.message_id = pm.message_id
           WHERE pm.sender_domain = ?
           ORDER BY m.date""",
        (domain,),
    ).fetchall()

    if not messages:
        return

    # Get AI classifications (majority vote)
    classifications = db.execute(
        """SELECT ac.industry, ac.company_size_estimate, ac.marketing_sophistication,
                  ac.sender_intent, ac.product_type, ac.product_description,
                  ac.pain_points, ac.target_audience,
                  ac.partner_program_detected, ac.renewal_signal_detected
           FROM ai_classification ac
           JOIN parsed_metadata pm ON ac.message_id = pm.message_id
           WHERE pm.sender_domain = ?""",
        (domain,),
    ).fetchall()

    # Get parsed content data
    content_rows = db.execute(
        """SELECT pc.offer_types, pc.cta_texts, pc.has_personalization,
                  pc.social_links, pc.utm_campaigns, pc.link_intents,
                  pc.has_physical_address, pc.physical_address_text,
                  pc.template_complexity_score
           FROM parsed_content pc
           JOIN parsed_metadata pm ON pc.message_id = pm.message_id
           WHERE pm.sender_domain = ?""",
        (domain,),
    ).fetchall()

    # Get metadata
    meta = db.execute(
        """SELECT esp_identified, spf_result, dmarc_result, dkim_domain,
                  list_unsubscribe_url
           FROM parsed_metadata WHERE sender_domain = ? LIMIT 1""",
        (domain,),
    ).fetchone()

    # Get entities
    entities = db.execute(
        """SELECT ee.entity_type, ee.entity_value, ee.entity_normalized, ee.context
           FROM extracted_entities ee
           JOIN parsed_metadata pm ON ee.message_id = pm.message_id
           WHERE pm.sender_domain = ?""",
        (domain,),
    ).fetchall()

    # Get temporal data
    temporal = db.execute(
        "SELECT * FROM sender_temporal WHERE sender_domain = ?", (domain,)
    ).fetchone()

    # --- Aggregation ---

    # Basic info
    primary_email = messages[0]["from_address"]
    reply_to_email = messages[0]["reply_to"]
    company_name = _infer_company_name(domain, messages)
    total_messages = len(messages)
    first_contact = messages[0]["date"]
    last_contact = messages[-1]["date"]
    avg_freq = temporal["avg_frequency_days"] if temporal else None

    # Industry & size via majority vote
    industry = _majority_vote([c["industry"] for c in classifications if c["industry"]])
    company_size = _majority_vote([c["company_size_estimate"] for c in classifications if c["company_size_estimate"]])

    # Marketing sophistication average and trend
    soph_scores = [c["marketing_sophistication"] for c in classifications if c["marketing_sophistication"]]
    ai_soph_avg = sum(soph_scores) / len(soph_scores) if soph_scores else 0
    soph_trend = "stable"
    if len(soph_scores) >= 3:
        first_half = sum(soph_scores[:len(soph_scores) // 2]) / (len(soph_scores) // 2)
        second_half = sum(soph_scores[len(soph_scores) // 2:]) / (len(soph_scores) - len(soph_scores) // 2)
        if second_half - first_half > 1:
            soph_trend = "improving"
        elif first_half - second_half > 1:
            soph_trend = "declining"

    # Most recent product info
    product_type = ""
    product_desc = ""
    pain_points = []
    target_audience = ""
    if classifications:
        latest = classifications[-1]
        product_type = latest["product_type"] or ""
        product_desc = latest["product_description"] or ""
        try:
            pain_points = json.loads(latest["pain_points"]) if latest["pain_points"] else []
        except (json.JSONDecodeError, TypeError):
            pain_points = []
        target_audience = latest["target_audience"] or ""

    # ESP
    esp_used = meta["esp_identified"] if meta else None

    # Offer type distribution
    offer_dist: Counter = Counter()
    all_ctas: list[str] = []
    all_utm_names: list[str] = []
    has_personalization = False
    social_links = {}
    physical_address = None
    partner_urls: list[str] = []
    max_template_complexity = 0

    for cr in content_rows:
        try:
            offers = json.loads(cr["offer_types"]) if cr["offer_types"] else []
            offer_dist.update(offers)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            ctas = json.loads(cr["cta_texts"]) if cr["cta_texts"] else []
            all_ctas.extend(ctas)
        except (json.JSONDecodeError, TypeError):
            pass
        if cr["has_personalization"]:
            has_personalization = True
        try:
            sl = json.loads(cr["social_links"]) if cr["social_links"] else {}
            social_links.update(sl)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            utms = json.loads(cr["utm_campaigns"]) if cr["utm_campaigns"] else []
            for utm in utms:
                if "utm_campaign" in utm:
                    all_utm_names.append(utm["utm_campaign"])
        except (json.JSONDecodeError, TypeError):
            pass
        if cr["has_physical_address"] and cr["physical_address_text"]:
            physical_address = cr["physical_address_text"]
        # Partner program URLs
        try:
            intents = json.loads(cr["link_intents"]) if cr["link_intents"] else {}
            if "partner_program" in intents:
                partner_urls.extend(intents["partner_program"])
        except (json.JSONDecodeError, TypeError):
            pass
        # Track template complexity for deterministic scoring
        tcs = cr["template_complexity_score"] or 0
        if tcs > max_template_complexity:
            max_template_complexity = tcs

    # Known contacts from entities
    known_contacts = []
    seen_names: set[str] = set()
    for ent in entities:
        if ent["entity_type"] == "person" and ent["entity_value"] not in seen_names:
            seen_names.add(ent["entity_value"])
            contact = {"name": ent["entity_value"], "email": "", "role": ""}
            if ent["entity_normalized"] and ent["entity_normalized"] != ent["entity_value"]:
                contact["role"] = ent["entity_normalized"]
            known_contacts.append(contact)

    # Monetary signals
    monetary = []
    for ent in entities:
        if ent["entity_type"] == "money":
            monetary.append({"amount": ent["entity_value"], "context": ent["context"] or ""})

    # Renewal dates
    renewal_dates = []
    for ent in entities:
        if ent["entity_type"] == "date" and ent["context"] in ("renewal", "expiration"):
            renewal_dates.append(ent["entity_value"])

    # Partner program detection
    has_partner_program = bool(partner_urls) or any(
        c["partner_program_detected"] for c in classifications if c["partner_program_detected"]
    )

    # Authentication quality
    auth_quality = "unknown"
    if meta:
        passing = sum(1 for r in [meta["spf_result"], meta["dmarc_result"]] if r == "pass")
        has_dkim = bool(meta["dkim_domain"])
        if passing == 2 and has_dkim:
            auth_quality = "excellent"
        elif passing >= 1 or has_dkim:
            auth_quality = "good"
        else:
            auth_quality = "poor"

    # Deterministic sophistication score (blended 60/40 with AI average)
    det_score = compute_sophistication_score(
        esp=esp_used,
        has_personalization=has_personalization,
        has_utm=bool(all_utm_names),
        template_complexity=max_template_complexity,
        spf=meta["spf_result"] if meta else None,
        dkim=meta["dkim_domain"] if meta else None,
        dmarc=meta["dmarc_result"] if meta else None,
        has_unsubscribe=bool(meta["list_unsubscribe_url"] if meta else None),
        unique_campaign_count=len(set(all_utm_names)),
    )
    if ai_soph_avg > 0:
        soph_avg = 0.6 * det_score + 0.4 * ai_soph_avg
    else:
        soph_avg = float(det_score)

    # Determine economic segments
    segments = _determine_segments(
        classifications, offer_dist, has_partner_program, renewal_dates
    )

    # Dedupe CTAs
    unique_ctas = list(dict.fromkeys(all_ctas))[:50]

    db.execute(
        """INSERT OR REPLACE INTO sender_profiles
           (sender_domain, company_name, primary_email, reply_to_email,
            industry, company_size, marketing_sophistication_avg,
            marketing_sophistication_trend, esp_used, product_type,
            product_description, pain_points, target_audience,
            known_contacts, total_messages, first_contact, last_contact,
            avg_frequency_days, offer_type_distribution, cta_texts_all,
            social_links, physical_address, utm_campaign_names,
            has_personalization, has_partner_program, partner_program_urls,
            renewal_dates, monetary_signals, authentication_quality,
            unsubscribe_url, economic_segments)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            domain, company_name, primary_email, reply_to_email,
            industry, company_size, soph_avg, soph_trend,
            esp_used, product_type, product_desc,
            json.dumps(pain_points), target_audience,
            json.dumps(known_contacts), total_messages,
            first_contact, last_contact, avg_freq,
            json.dumps(dict(offer_dist)), json.dumps(unique_ctas),
            json.dumps(social_links), physical_address,
            json.dumps(list(set(all_utm_names))),
            has_personalization, has_partner_program,
            json.dumps(list(set(partner_urls))),
            json.dumps(renewal_dates),
            json.dumps(monetary),
            auth_quality,
            meta["list_unsubscribe_url"] if meta else None,
            json.dumps(segments),
        ),
    )


def detect_gems(
    db: sqlite3.Connection,
    engagement_config=None,
    scoring_config=None,
) -> int:
    """Detect gems for all sender profiles.

    Args:
        engagement_config: EngagementConfig for co_marketing audience overlap check.
        scoring_config: ScoringConfig for dormant thread thresholds.

    Returns count of gems detected.
    """
    # Clear existing gems to re-detect (idempotent)
    # Delete engagement drafts first to satisfy foreign key constraint
    db.execute("DELETE FROM engagement_drafts WHERE gem_id IN (SELECT id FROM gems)")
    db.execute("DELETE FROM gems")

    profiles = db.execute("SELECT * FROM sender_profiles").fetchall()

    # Get dormant config from scoring if available
    dormant_config = None
    if scoring_config and hasattr(scoring_config, "dormant_thread"):
        dormant_config = scoring_config.dormant_thread

    # Pre-compute bulk sender domains (>50% of messages are bulk)
    bulk_rows = db.execute("""
        SELECT sender_domain,
               SUM(is_bulk) * 1.0 / COUNT(*) as bulk_ratio
        FROM parsed_metadata
        GROUP BY sender_domain
        HAVING bulk_ratio > 0.5
    """).fetchall()
    bulk_sender_domains = {r["sender_domain"] for r in bulk_rows}

    # Load excluded domains
    excluded_rows = db.execute("SELECT domain FROM domain_exclusions").fetchall()
    excluded_domains = {r["domain"] for r in excluded_rows}

    gem_count = 0
    for profile in profiles:
        domain = profile["sender_domain"]

        # Skip excluded domains
        if domain in excluded_domains:
            continue
        gems = []

        gems.extend(_detect_dormant_warm_thread(db, profile, dormant_config=dormant_config, bulk_sender_domains=bulk_sender_domains))
        gems.extend(_detect_unanswered_ask(db, profile, bulk_sender_domains=bulk_sender_domains))
        gems.extend(_detect_weak_marketing_lead(db, profile, bulk_sender_domains=bulk_sender_domains))
        gems.extend(_detect_partner_program(db, profile))
        gems.extend(_detect_renewal_leverage(db, profile, bulk_sender_domains=bulk_sender_domains))
        gems.extend(_detect_distribution_channel(db, profile))
        gems.extend(_detect_co_marketing(db, profile, engagement_config=engagement_config))
        gems.extend(_detect_vendor_upsell(db, profile))
        gems.extend(_detect_industry_intel(db, profile, bulk_sender_domains=bulk_sender_domains))
        gems.extend(_detect_procurement_signal(db, profile))

        for gem in gems:
            db.execute(
                """INSERT INTO gems
                   (gem_type, sender_domain, thread_id, score,
                    explanation, recommended_actions, source_message_ids, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'new')""",
                (
                    gem["gem_type"], domain, gem.get("thread_id"),
                    gem["score"], json.dumps(gem["explanation"]),
                    json.dumps(gem["recommended_actions"]),
                    json.dumps(gem.get("source_message_ids", [])),
                ),
            )
            gem_count += 1

    db.commit()
    return gem_count


def _majority_vote(values: list[str]) -> str:
    """Return the most common non-empty value."""
    if not values:
        return ""
    counter = Counter(v for v in values if v)
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


def _infer_company_name(domain: str, messages: list) -> str:
    """Infer company name from domain and sender names."""
    names = [m["from_name"] for m in messages if m["from_name"] and "@" not in m["from_name"]]
    if names:
        counter = Counter(names)
        return counter.most_common(1)[0][0]
    parts = domain.split(".")
    return parts[0].title() if parts else domain


def _determine_segments(
    classifications: list, offer_dist: Counter,
    has_partner_program: bool, renewal_dates: list
) -> list[str]:
    """Determine which economic segments a sender belongs to."""
    segments = []

    intents = [c["sender_intent"] for c in classifications if c["sender_intent"]]
    intent_counter = Counter(intents)
    primary_intent = intent_counter.most_common(1)[0][0] if intent_counter else ""

    if primary_intent == "transactional" or "renewal" in offer_dist or renewal_dates:
        segments.append("spend_map")
    if has_partner_program or "partnership" in offer_dist:
        segments.append("partner_map")
    if primary_intent in ("promotional", "nurture_sequence", "cold_outreach"):
        segments.append("prospect_map")
    if primary_intent in ("newsletter", "event_invitation", "community"):
        segments.append("distribution_map")
    if primary_intent == "procurement" or "procurement" in offer_dist:
        segments.append("procurement_map")

    return segments


# --- Warm Signal Scanning ---

def _scan_warm_signals(db: sqlite3.Connection, thread_id: str) -> tuple[list[dict], int]:
    """Scan thread messages for warm signals (pricing, meeting requests, etc.).

    Returns (signals_list, score_boost) with score_boost capped at 30.
    """
    messages = db.execute(
        """SELECT m.message_id, m.body_text, pc.body_clean
           FROM messages m
           LEFT JOIN parsed_content pc ON m.message_id = pc.message_id
           WHERE m.thread_id = ?""",
        (thread_id,),
    ).fetchall()

    signals = []
    score_boost = 0

    for msg in messages:
        text = msg["body_clean"] or msg["body_text"] or ""
        if not text:
            continue

        for signal_type, patterns in WARM_SIGNALS.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    signals.append({
                        "signal": f"warm_{signal_type}",
                        "evidence": match.group(0)[:80],
                    })
                    score_boost += 5
                    break  # one match per signal type per message

    # Also check entity cross-references for the thread
    entity_signals = db.execute(
        """SELECT ee.entity_type, ee.entity_value, ee.context
           FROM extracted_entities ee
           WHERE ee.message_id IN (SELECT message_id FROM messages WHERE thread_id = ?)
             AND (ee.entity_type = 'money' OR (ee.entity_type = 'person' AND ee.context LIKE '%decision_maker%'))""",
        (thread_id,),
    ).fetchall()

    for ent in entity_signals:
        if ent["entity_type"] == "money":
            signals.append({"signal": "warm_budget_indicator", "evidence": ent["entity_value"]})
            score_boost += 5
        elif "decision_maker" in (ent["context"] or ""):
            signals.append({"signal": "warm_decision_maker", "evidence": ent["entity_value"]})
            score_boost += 5

    return signals, min(score_boost, 30)


# --- Gem Detection Functions ---

def _detect_dormant_warm_thread(db: sqlite3.Connection, profile, dormant_config=None, bulk_sender_domains=None) -> list[dict]:
    """Detect dormant warm threads for this sender."""
    gems = []
    domain = profile["sender_domain"]

    # Skip bulk sender domains
    if bulk_sender_domains and domain in bulk_sender_domains:
        return []

    min_dormancy = 14
    max_dormancy = 365
    require_human = True
    if dormant_config:
        min_dormancy = getattr(dormant_config, "min_dormancy_days", 14)
        max_dormancy = getattr(dormant_config, "max_dormancy_days", 365)
        require_human = getattr(dormant_config, "require_human_sender", True)

    threads = db.execute(
        """SELECT t.thread_id, t.subject, t.days_dormant, t.awaiting_response_from,
                  t.last_sender, t.user_participated, t.message_count
           FROM threads t
           JOIN messages m ON t.thread_id = m.thread_id
           JOIN parsed_metadata pm ON m.message_id = pm.message_id
           WHERE pm.sender_domain = ?
             AND t.awaiting_response_from = 'user'
             AND t.days_dormant >= ?
             AND t.days_dormant <= ?
             AND t.user_participated = 1
             AND t.message_count >= 2
           GROUP BY t.thread_id""",
        (domain, min_dormancy, max_dormancy),
    ).fetchall()

    for t in threads:
        msg_ids = [r["message_id"] for r in db.execute(
            "SELECT message_id FROM messages WHERE thread_id = ?", (t["thread_id"],)
        ).fetchall()]

        # Scan for warm signals
        warm_signals, warm_boost = _scan_warm_signals(db, t["thread_id"])

        # Require at least 2 distinct warm signal types
        distinct_signal_types = {
            s["signal"].split("_", 1)[-1] if s["signal"].startswith("warm_") else s["signal"]
            for s in warm_signals
        }
        if require_human and len(distinct_signal_types) < 2:
            continue

        # Filter out transactional/re_engagement intents
        intents = db.execute(
            """SELECT ac.sender_intent FROM ai_classification ac
               JOIN messages m ON ac.message_id = m.message_id
               WHERE m.thread_id = ?""",
            (t["thread_id"],),
        ).fetchall()
        skip_intents = {"transactional", "re_engagement"}
        if any(i["sender_intent"] in skip_intents for i in intents if i["sender_intent"]):
            continue

        signals = list(warm_signals)
        score = 40 + warm_boost

        if t["user_participated"]:
            signals.append({"signal": "user_participated", "evidence": "You were part of this conversation"})
            score += 10

        if t["days_dormant"] < 60:
            score += 15
        elif t["days_dormant"] < 120:
            score += 10

        if t["message_count"] and t["message_count"] > 2:
            signals.append({"signal": "multi_message_thread", "evidence": f"{t['message_count']} messages exchanged"})
            score += 5

        # Determine estimated_value and urgency
        estimated_value = "medium"
        if warm_boost >= 15:
            estimated_value = "high"
        elif warm_boost == 0:
            estimated_value = "low"

        urgency = "medium"
        if t["days_dormant"] < 30:
            urgency = "high"
        elif t["days_dormant"] > 180:
            urgency = "low"

        gems.append({
            "gem_type": GemType.DORMANT_WARM_THREAD.value,
            "thread_id": t["thread_id"],
            "score": min(score, 100),
            "explanation": {
                "gem_type": "dormant_warm_thread",
                "summary": f"Thread '{t['subject']}' has been dormant for {t['days_dormant']} days. You owe a reply.",
                "signals": signals,
                "confidence": 0.8,
                "estimated_value": estimated_value,
                "urgency": urgency,
            },
            "recommended_actions": ["Reply to thread with new value-add"],
            "source_message_ids": msg_ids,
        })

    return gems


def _detect_unanswered_ask(db: sqlite3.Connection, profile, bulk_sender_domains=None) -> list[dict]:
    """Detect unanswered asks from this sender."""
    gems = []
    domain = profile["sender_domain"]

    # Skip bulk sender domains
    if bulk_sender_domains and domain in bulk_sender_domains:
        return []

    threads = db.execute(
        """SELECT t.thread_id, t.subject, t.days_dormant, t.last_sender
           FROM threads t
           JOIN messages m ON t.thread_id = m.thread_id
           JOIN parsed_metadata pm ON m.message_id = pm.message_id
           WHERE pm.sender_domain = ?
             AND t.awaiting_response_from = 'user'
             AND t.days_dormant >= 3
             AND t.days_dormant < 14
             AND t.message_count >= 2
             AND t.user_participated = 1
           GROUP BY t.thread_id""",
        (domain,),
    ).fetchall()

    for t in threads:
        msg_ids = [r["message_id"] for r in db.execute(
            "SELECT message_id FROM messages WHERE thread_id = ?", (t["thread_id"],)
        ).fetchall()]

        gems.append({
            "gem_type": GemType.UNANSWERED_ASK.value,
            "thread_id": t["thread_id"],
            "score": 50,
            "explanation": {
                "gem_type": "unanswered_ask",
                "summary": f"'{t['subject']}' — {t['last_sender']} is waiting for your reply ({t['days_dormant']} days).",
                "signals": [{"signal": "awaiting_response", "evidence": f"Last message from {t['last_sender']}"}],
                "confidence": 0.9,
                "estimated_value": "medium-high",
                "urgency": "high",
            },
            "recommended_actions": ["Reply promptly"],
            "source_message_ids": msg_ids,
        })

    return gems


def _detect_weak_marketing_lead(db: sqlite3.Connection, profile, bulk_sender_domains=None) -> list[dict]:
    """Detect senders with marketing gaps you can fill."""
    domain = profile["sender_domain"]

    # Skip bulk sender domains (they ARE the marketers, not leads)
    if bulk_sender_domains and domain in bulk_sender_domains:
        return []

    # Require enough data to evaluate
    if not profile["total_messages"] or profile["total_messages"] < 3:
        return []

    # Require known industry
    if not profile["industry"]:
        return []

    soph = profile["marketing_sophistication_avg"] or 0
    size = profile["company_size"] or ""

    if soph > 5 or size == "enterprise":
        return []

    score = 30
    signals = []

    if soph <= 3:
        signals.append({"signal": "low_sophistication", "evidence": f"Marketing sophistication: {soph:.1f}/10"})
        score += 20
    elif soph <= 5:
        signals.append({"signal": "moderate_sophistication", "evidence": f"Marketing sophistication: {soph:.1f}/10"})
        score += 10

    if size == "small":
        score += 10
    elif size == "medium":
        score += 5

    # Determine estimated_value based on company_size
    estimated_value = "medium"
    if size == "medium":
        estimated_value = "medium-high"
    elif size == "small":
        estimated_value = "medium"

    return [{
        "gem_type": GemType.WEAK_MARKETING_LEAD.value,
        "score": min(score, 100),
        "explanation": {
            "gem_type": "weak_marketing_lead",
            "summary": f"{profile['company_name']} ({profile['sender_domain']}) has marketing gaps you could address.",
            "signals": signals,
            "confidence": 0.7,
            "estimated_value": estimated_value,
            "urgency": "low",
        },
        "recommended_actions": ["Send audit-style outreach highlighting specific gaps"],
    }]


def _detect_partner_program(db: sqlite3.Connection, profile) -> list[dict]:
    """Detect partner program opportunities."""
    if not profile["has_partner_program"]:
        return []

    urls = []
    try:
        urls = json.loads(profile["partner_program_urls"]) if profile["partner_program_urls"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    score = 40
    signals = [{"signal": "partner_program_detected", "evidence": "Partner/affiliate program links found"}]

    if urls:
        signals.append({"signal": "direct_urls", "evidence": f"{len(urls)} partner program URL(s)"})
        score += 15

    return [{
        "gem_type": GemType.PARTNER_PROGRAM.value,
        "score": min(score, 100),
        "explanation": {
            "gem_type": "partner_program",
            "summary": f"{profile['company_name']} has a partner/affiliate program you could join.",
            "signals": signals,
            "confidence": 0.8,
            "estimated_value": "medium",
            "urgency": "low",
        },
        "recommended_actions": ["Apply to partner program", "Review commission structure"],
    }]


def _detect_renewal_leverage(db: sqlite3.Connection, profile, bulk_sender_domains=None) -> list[dict]:
    """Detect renewal negotiation windows."""
    domain = profile["sender_domain"]

    # Skip bulk sender domains
    if bulk_sender_domains and domain in bulk_sender_domains:
        return []

    renewal_dates = []
    try:
        renewal_dates = json.loads(profile["renewal_dates"]) if profile["renewal_dates"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    segments = []
    try:
        segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    if not renewal_dates and "spend_map" not in segments:
        return []

    score = 35
    signals = []

    # Determine value by monetary signals
    monetary = []
    try:
        monetary = json.loads(profile["monetary_signals"]) if profile["monetary_signals"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    estimated_value = "medium"
    if monetary:
        estimated_value = "high"

    if renewal_dates:
        signals.append({"signal": "renewal_dates", "evidence": f"Renewal dates found: {', '.join(renewal_dates)}"})
        score += 20

    if "spend_map" in segments:
        signals.append({"signal": "active_vendor", "evidence": "You're an active customer"})
        score += 10

    # Urgency by renewal date proximity (simple: high if we have renewal dates)
    urgency = "high" if renewal_dates else "medium"

    return [{
        "gem_type": GemType.RENEWAL_LEVERAGE.value,
        "score": min(score, 100),
        "explanation": {
            "gem_type": "renewal_leverage",
            "summary": f"Upcoming renewal window with {profile['company_name']} — negotiation opportunity.",
            "signals": signals,
            "confidence": 0.75,
            "estimated_value": estimated_value,
            "urgency": urgency,
        },
        "recommended_actions": ["Prepare negotiation strategy", "Research competitive alternatives"],
    }]


def _detect_distribution_channel(db: sqlite3.Connection, profile) -> list[dict]:
    """Detect newsletters/events that could amplify your reach."""
    segments = []
    try:
        segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    if "distribution_map" not in segments:
        return []

    score = 30
    signals = [{"signal": "distribution_channel", "evidence": "Sender is a newsletter/event/community"}]

    if profile["total_messages"] and profile["total_messages"] > 10:
        signals.append({"signal": "active_publication", "evidence": f"{profile['total_messages']} messages received"})
        score += 15

    # Distribution content signal enhancement (Spec §14)
    domain = profile["sender_domain"]
    content_rows = db.execute(
        """SELECT pc.body_clean FROM parsed_content pc
           JOIN parsed_metadata pm ON pc.message_id = pm.message_id
           JOIN messages m ON pc.message_id = m.message_id
           WHERE pm.sender_domain = ? AND m.is_sent = 0""",
        (domain,),
    ).fetchall()

    for cr in content_rows:
        text = cr["body_clean"] or ""
        for pattern in DISTRIBUTION_CONTENT_SIGNALS:
            match = pattern.search(text)
            if match:
                signals.append({
                    "signal": "content_opportunity",
                    "evidence": match.group(0)[:80],
                })
                score += 15
                break  # one content opportunity signal is enough

    # Determine value by activity
    estimated_value = "medium" if (profile["total_messages"] or 0) > 10 else "low"

    return [{
        "gem_type": GemType.DISTRIBUTION_CHANNEL.value,
        "score": min(score, 100),
        "explanation": {
            "gem_type": "distribution_channel",
            "summary": f"{profile['company_name']} could amplify your reach through their audience.",
            "signals": signals,
            "confidence": 0.65,
            "estimated_value": estimated_value,
            "urgency": "low",
        },
        "recommended_actions": ["Pitch guest content or sponsorship"],
    }]


def _detect_co_marketing(db: sqlite3.Connection, profile, engagement_config=None) -> list[dict]:
    """Detect co-marketing opportunities where audiences overlap."""
    industry = profile["industry"] or ""
    target = profile["target_audience"] or ""
    size = profile["company_size"] or ""

    if not industry or not target:
        return []

    # Skip enterprise companies (different league)
    if size == "enterprise":
        return []

    # Check audience overlap using engagement_config.your_audience
    user_audience = ""
    if engagement_config and hasattr(engagement_config, "your_audience"):
        user_audience = engagement_config.your_audience or ""

    if not user_audience:
        return []

    # Tokenize and compare audiences
    user_keywords = set(user_audience.lower().split())
    target_keywords = set(target.lower().split())

    # Remove common stop words
    stop_words = {"and", "the", "for", "to", "of", "a", "an", "in", "on", "with", "who", "that", "are", "is"}
    user_keywords -= stop_words
    target_keywords -= stop_words

    overlap = user_keywords & target_keywords
    if len(overlap) < 2:
        return []

    signals = [
        {"signal": "audience_overlap", "evidence": f"Shared keywords: {', '.join(sorted(overlap)[:5])}"},
        {"signal": "target_audience", "evidence": target},
    ]

    # Check distribution capability
    offer_dist = {}
    try:
        offer_dist = json.loads(profile["offer_type_distribution"]) if profile["offer_type_distribution"] else {}
    except (json.JSONDecodeError, TypeError):
        pass

    if any(k in offer_dist for k in ("newsletter", "event", "webinar")):
        signals.append({"signal": "has_distribution", "evidence": "Has newsletter/event distribution"})

    score = 35 + len(overlap) * 5

    return [{
        "gem_type": GemType.CO_MARKETING.value,
        "score": min(score, 100),
        "explanation": {
            "gem_type": "co_marketing",
            "summary": f"{profile['company_name']} targets a similar audience — co-marketing opportunity.",
            "signals": signals,
            "confidence": 0.6,
            "estimated_value": "medium",
            "urgency": "low",
        },
        "recommended_actions": ["Propose co-marketing campaign", "Explore content collaboration"],
    }]


def _detect_vendor_upsell(db: sqlite3.Connection, profile) -> list[dict]:
    """Detect vendors pitching upgrades (they value you as a customer)."""
    segments = []
    try:
        segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
    except (json.JSONDecodeError, TypeError):
        pass

    offer_dist = {}
    try:
        offer_dist = json.loads(profile["offer_type_distribution"]) if profile["offer_type_distribution"] else {}
    except (json.JSONDecodeError, TypeError):
        pass

    if "spend_map" not in segments:
        return []

    if not any(k in offer_dist for k in ("discount", "free_trial", "product_launch")):
        return []

    return [{
        "gem_type": GemType.VENDOR_UPSELL.value,
        "score": 25,
        "explanation": {
            "gem_type": "vendor_upsell",
            "summary": f"{profile['company_name']} is pitching upgrades — they value your business.",
            "signals": [{"signal": "upsell_offers", "evidence": "Discount/upgrade offers detected"}],
            "confidence": 0.6,
            "estimated_value": "low",
            "urgency": "medium",
        },
        "recommended_actions": ["Evaluate upgrade offers for leverage"],
    }]


def _detect_industry_intel(db: sqlite3.Connection, profile, bulk_sender_domains=None) -> list[dict]:
    """Detect useful industry intelligence from this sender's pattern."""
    domain = profile["sender_domain"]

    # Skip bulk sender domains
    if bulk_sender_domains and domain in bulk_sender_domains:
        return []

    # Require sufficient message volume and known industry
    if not profile["total_messages"] or profile["total_messages"] < 10:
        return []

    if not profile["industry"]:
        return []

    return [{
        "gem_type": GemType.INDUSTRY_INTEL.value,
        "score": 20,
        "explanation": {
            "gem_type": "industry_intel",
            "summary": f"{profile['company_name']} provides market intelligence for {profile['industry'] or 'their'} industry.",
            "signals": [{"signal": "message_volume", "evidence": f"{profile['total_messages']} messages analyzed"}],
            "confidence": 0.5,
            "estimated_value": "low",
            "urgency": "low",
        },
        "recommended_actions": ["Include in industry analysis report"],
    }]


def _detect_procurement_signal(db: sqlite3.Connection, profile) -> list[dict]:
    """Detect active buying or vendor evaluation signals."""
    domain = profile["sender_domain"]

    procurement_entities = db.execute(
        """SELECT ee.entity_value, ee.entity_normalized
           FROM extracted_entities ee
           JOIN parsed_metadata pm ON ee.message_id = pm.message_id
           WHERE pm.sender_domain = ? AND ee.entity_type = 'procurement_signal'""",
        (domain,),
    ).fetchall()

    if not procurement_entities:
        return []

    signals = [
        {"signal": "procurement_keyword", "evidence": e["entity_value"]}
        for e in procurement_entities[:5]
    ]

    return [{
        "gem_type": GemType.PROCUREMENT_SIGNAL.value,
        "score": 45,
        "explanation": {
            "gem_type": "procurement_signal",
            "summary": f"Procurement signals detected from {profile['company_name']}.",
            "signals": signals,
            "confidence": 0.7,
            "estimated_value": "high",
            "urgency": "high",
        },
        "recommended_actions": ["Review procurement context", "Prepare response if applicable"],
    }]
