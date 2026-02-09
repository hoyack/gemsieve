"""Stage 5.5: Relationship detection — classify senders by relationship direction."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from gemsieve.known_entities import is_known_entity, load_known_entities
from gemsieve.stages.metadata import collapse_subdomain

# Relationship types
RELATIONSHIP_TYPES = {
    "my_vendor",           # You pay them (Stripe, Heroku)
    "my_service_provider", # Professional services you hired
    "my_infrastructure",   # SaaS infrastructure (Google, AWS)
    "selling_to_me",       # Cold outreach, trying to sell you something
    "inbound_prospect",    # They reached out interested in YOUR services
    "warm_contact",        # Bidirectional relationship, mutual engagement
    "potential_partner",   # Partnership/collaboration interest
    "community",           # Newsletter, event, community
    "institutional",       # Insurance, payroll, government
    "unknown",             # No classification yet
}

# Known entity category -> relationship type mapping
_CATEGORY_TO_RELATIONSHIP = {
    "infrastructure": "my_infrastructure",
    "institutional": "institutional",
    "marketing_platforms": "my_infrastructure",
    "user_suppressed": "unknown",
}

# Vendor signal patterns
_VENDOR_PATTERNS = [
    re.compile(r"\b(?:invoice|receipt|payment|subscription|billing|renewal)\b", re.IGNORECASE),
    re.compile(r"\b(?:your (?:account|plan|subscription|license|trial))\b", re.IGNORECASE),
    re.compile(r"\b(?:service (?:update|notification|alert))\b", re.IGNORECASE),
    re.compile(r"\b(?:onboarding|getting started|welcome to)\b", re.IGNORECASE),
    re.compile(r"\b(?:support ticket|case \#|helpdesk)\b", re.IGNORECASE),
]

# Prospect signal patterns (they're interested in YOUR services)
_PROSPECT_PATTERNS = [
    re.compile(r"\b(?:interested in (?:your|learning about))\b", re.IGNORECASE),
    re.compile(r"\b(?:can you (?:help|tell me|share))\b", re.IGNORECASE),
    re.compile(r"\b(?:looking for (?:a|an|someone|help))\b", re.IGNORECASE),
    re.compile(r"\b(?:referr(?:ed|al) (?:by|from))\b", re.IGNORECASE),
    re.compile(r"\b(?:saw your (?:work|talk|article|post))\b", re.IGNORECASE),
]

# Selling-to-me patterns (cold outreach)
_SELLING_PATTERNS = [
    re.compile(r"\b(?:I (?:wanted to|thought you|noticed your))\b", re.IGNORECASE),
    re.compile(r"\b(?:quick question|touching base|reaching out)\b", re.IGNORECASE),
    re.compile(r"\b(?:book a (?:demo|call|meeting))\b", re.IGNORECASE),
    re.compile(r"\b(?:free trial|special offer|limited time)\b", re.IGNORECASE),
    re.compile(r"\b(?:would you be (?:open|interested))\b", re.IGNORECASE),
]

# Completion signal patterns
_COMPLETION_PATTERNS = [
    re.compile(r"\b(?:final (?:deliverable|report|version))\b", re.IGNORECASE),
    re.compile(r"\b(?:project (?:complete|finished|wrapped))\b", re.IGNORECASE),
    re.compile(r"\b(?:great working with you)\b", re.IGNORECASE),
    re.compile(r"\b(?:contract (?:ended|expired|concluded))\b", re.IGNORECASE),
    re.compile(r"\b(?:closing out|wrapping up)\b", re.IGNORECASE),
    re.compile(r"\b(?:all set,?\s*thanks)\b", re.IGNORECASE),
]


def detect_relationships(
    db: sqlite3.Connection,
    known_entities: dict[str, list[str]] | None = None,
    known_entities_file: str | None = None,
    apply: bool = False,
) -> list[dict]:
    """Classify all profiled senders by relationship type.

    Returns proposals [{sender_domain, proposed_type, confidence, signals}].
    If apply=True, writes high-confidence detections to sender_relationships table.
    """
    if known_entities is None:
        known_entities = load_known_entities(known_entities_file)

    profiles = db.execute("SELECT * FROM sender_profiles").fetchall()

    proposals = []
    for profile in profiles:
        domain = profile["sender_domain"]
        rel_type, confidence, signals = _classify_relationship(db, profile, known_entities)

        proposal = {
            "sender_domain": domain,
            "proposed_type": rel_type,
            "confidence": confidence,
            "signals": signals,
        }
        proposals.append(proposal)

        if apply and confidence >= 0.6:
            # Check if already exists with manual source — don't overwrite
            existing = db.execute(
                "SELECT source FROM sender_relationships WHERE sender_domain = ?",
                (domain,),
            ).fetchone()
            if existing and existing["source"] == "manual":
                continue

            set_relationship(
                db, domain, rel_type,
                note=f"Auto-detected: {', '.join(s.get('signal', '') for s in signals[:3])}",
                suppress=rel_type in ("my_infrastructure", "institutional"),
                source="auto",
            )

    if apply:
        db.commit()

    return proposals


def _classify_relationship(
    db: sqlite3.Connection,
    profile,
    known_entities: dict[str, list[str]],
) -> tuple[str, float, list[dict]]:
    """Classify single sender's relationship type.

    Priority:
        1. Existing sender_relationships entry (user override)
        2. Known entities match
        3. Signal-based detection
    """
    domain = profile["sender_domain"]

    # 1. Check existing sender_relationships
    existing = db.execute(
        "SELECT relationship_type FROM sender_relationships WHERE sender_domain = ?",
        (domain,),
    ).fetchone()
    if existing:
        return existing["relationship_type"], 1.0, [{"signal": "existing_classification"}]

    # 2. Check known entities
    category = is_known_entity(domain, known_entities)
    if category:
        rel_type = _CATEGORY_TO_RELATIONSHIP.get(category, "unknown")
        return rel_type, 0.9, [{"signal": f"known_entity:{category}", "evidence": domain}]

    # 3. Signal-based detection
    vendor_score, vendor_signals = _scan_vendor_signals(db, profile)
    prospect_score, prospect_signals = _scan_prospect_signals(db, profile)
    selling_score, selling_signals = _scan_selling_signals(db, profile)

    # Determine winner
    scores = {
        "my_vendor": vendor_score,
        "inbound_prospect": prospect_score,
        "selling_to_me": selling_score,
    }
    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score < 0.3:
        # Low confidence — check for community/warm signals
        segments = []
        try:
            segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
        except (json.JSONDecodeError, TypeError):
            pass

        if "distribution_map" in segments:
            return "community", 0.6, [{"signal": "distribution_segment"}]

        # Check for bidirectional engagement
        reply_rate = profile["user_reply_rate"]
        initiation = profile["thread_initiation_ratio"]
        if reply_rate and initiation and 0.2 < initiation < 0.8 and reply_rate > 0.5:
            return "warm_contact", 0.5, [
                {"signal": "bidirectional_engagement",
                 "evidence": f"initiation={initiation:.2f}, reply_rate={reply_rate:.2f}"}
            ]

        return "unknown", 0.2, []

    all_signals = {"my_vendor": vendor_signals, "inbound_prospect": prospect_signals, "selling_to_me": selling_signals}
    return best_type, best_score, all_signals[best_type]


def _scan_vendor_signals(db: sqlite3.Connection, profile) -> tuple[float, list[dict]]:
    """Check for vendor relationship signals."""
    domain = profile["sender_domain"]
    signals = []
    score = 0.0

    # High thread_initiation_ratio = user reaches out to them = likely vendor
    initiation = profile["thread_initiation_ratio"]
    if initiation is not None and initiation > 0.7:
        signals.append({"signal": "user_initiates_contact", "evidence": f"ratio={initiation:.2f}"})
        score += 0.3

    # Check for transactional content
    content_rows = db.execute(
        """SELECT pc.body_clean FROM parsed_content pc
           JOIN parsed_metadata pm ON pc.message_id = pm.message_id
           WHERE pm.sender_domain = ? LIMIT 10""",
        (domain,),
    ).fetchall()

    vendor_hits = 0
    for cr in content_rows:
        text = cr["body_clean"] or ""
        for pattern in _VENDOR_PATTERNS:
            if pattern.search(text):
                vendor_hits += 1
                if len(signals) < 5:
                    signals.append({"signal": "vendor_content", "evidence": pattern.pattern[:60]})
                break

    if vendor_hits >= 3:
        score += 0.4
    elif vendor_hits >= 1:
        score += 0.2

    # Check spend_map segment
    segments = []
    try:
        segments = json.loads(profile["economic_segments"]) if profile["economic_segments"] else []
    except (json.JSONDecodeError, TypeError):
        pass
    if "spend_map" in segments:
        signals.append({"signal": "spend_map_segment"})
        score += 0.2

    return min(score, 1.0), signals


def _scan_prospect_signals(db: sqlite3.Connection, profile) -> tuple[float, list[dict]]:
    """Check for inbound prospect signals (they're interested in your services)."""
    domain = profile["sender_domain"]
    signals = []
    score = 0.0

    # Low initiation ratio = they reach out to you = possible prospect
    initiation = profile["thread_initiation_ratio"]
    if initiation is not None and initiation < 0.3:
        signals.append({"signal": "they_initiate_contact", "evidence": f"ratio={initiation:.2f}"})
        score += 0.2

    # User participated = genuine engagement
    reply_rate = profile["user_reply_rate"]
    if reply_rate is not None and reply_rate > 0.5:
        signals.append({"signal": "high_user_engagement", "evidence": f"reply_rate={reply_rate:.2f}"})
        score += 0.2

    # Check for prospect content patterns
    content_rows = db.execute(
        """SELECT pc.body_clean FROM parsed_content pc
           JOIN parsed_metadata pm ON pc.message_id = pm.message_id
           JOIN messages m ON pc.message_id = m.message_id
           WHERE pm.sender_domain = ? AND m.is_sent = 0 LIMIT 10""",
        (domain,),
    ).fetchall()

    for cr in content_rows:
        text = cr["body_clean"] or ""
        for pattern in _PROSPECT_PATTERNS:
            if pattern.search(text):
                signals.append({"signal": "prospect_language", "evidence": pattern.pattern[:60]})
                score += 0.3
                break

    # Small/unknown company heuristic
    size = profile["company_size"] or ""
    msgs = profile["total_messages"] or 0
    if size in ("small", "") and msgs <= 5:
        signals.append({"signal": "small_unknown_company"})
        score += 0.1

    return min(score, 1.0), signals


def _scan_selling_signals(db: sqlite3.Connection, profile) -> tuple[float, list[dict]]:
    """Check for cold outreach / selling-to-me signals."""
    domain = profile["sender_domain"]
    signals = []
    score = 0.0

    # No user participation = one-way outreach
    reply_rate = profile["user_reply_rate"]
    if reply_rate is not None and reply_rate < 0.1:
        signals.append({"signal": "no_user_participation", "evidence": f"reply_rate={reply_rate:.2f}"})
        score += 0.3

    # High volume one-way
    msgs = profile["total_messages"] or 0
    if msgs >= 5 and reply_rate is not None and reply_rate < 0.2:
        signals.append({"signal": "high_volume_one_way", "evidence": f"{msgs} messages, no replies"})
        score += 0.2

    # Check for selling content
    content_rows = db.execute(
        """SELECT pc.body_clean FROM parsed_content pc
           JOIN parsed_metadata pm ON pc.message_id = pm.message_id
           JOIN messages m ON pc.message_id = m.message_id
           WHERE pm.sender_domain = ? AND m.is_sent = 0 LIMIT 10""",
        (domain,),
    ).fetchall()

    for cr in content_rows:
        text = cr["body_clean"] or ""
        for pattern in _SELLING_PATTERNS:
            if pattern.search(text):
                signals.append({"signal": "selling_language", "evidence": pattern.pattern[:60]})
                score += 0.2
                break

    # Cold outreach intent from classification
    intents = db.execute(
        """SELECT ac.sender_intent FROM ai_classification ac
           JOIN parsed_metadata pm ON ac.message_id = pm.message_id
           WHERE pm.sender_domain = ? AND ac.sender_intent = 'cold_outreach'""",
        (domain,),
    ).fetchall()
    if intents:
        signals.append({"signal": "cold_outreach_intent", "evidence": f"{len(intents)} messages"})
        score += 0.3

    return min(score, 1.0), signals


def scan_completion_signals(db: sqlite3.Connection, thread_id: str) -> list[str]:
    """Scan the last 3 messages of a thread for completion signals.

    Returns list of matched completion signal descriptions.
    """
    messages = db.execute(
        """SELECT m.message_id, pc.body_clean, m.body_text
           FROM messages m
           LEFT JOIN parsed_content pc ON m.message_id = pc.message_id
           WHERE m.thread_id = ?
           ORDER BY m.date DESC LIMIT 3""",
        (thread_id,),
    ).fetchall()

    found = []
    for msg in messages:
        text = msg["body_clean"] or msg["body_text"] or ""
        for pattern in _COMPLETION_PATTERNS:
            match = pattern.search(text)
            if match:
                found.append(match.group(0))

    return found


def set_relationship(
    db: sqlite3.Connection,
    domain: str,
    relationship_type: str,
    note: str | None = None,
    suppress: bool = False,
    source: str = "manual",
) -> None:
    """Insert or update a sender relationship entry."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT OR REPLACE INTO sender_relationships
           (sender_domain, relationship_type, relationship_note,
            suppress_gems, created_at, source)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (domain, relationship_type, note, suppress, now, source),
    )
    db.commit()


def list_relationships(
    db: sqlite3.Connection, type_filter: str | None = None
) -> list[dict]:
    """List all sender relationships, optionally filtered by type."""
    if type_filter:
        rows = db.execute(
            "SELECT * FROM sender_relationships WHERE relationship_type = ? ORDER BY sender_domain",
            (type_filter,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM sender_relationships ORDER BY relationship_type, sender_domain"
        ).fetchall()

    return [dict(r) for r in rows]


def import_relationships(db: sqlite3.Connection, path: str) -> int:
    """Bulk import relationships from YAML file.

    Expected format:
        my_vendor:
          - stripe.com
          - heroku.com
        institutional:
          - rippling.com

    Returns count of relationships imported.
    """
    import yaml

    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return 0

    count = 0
    for rel_type, domains in data.items():
        if not isinstance(domains, list):
            continue
        suppress = rel_type in ("my_infrastructure", "institutional")
        for domain in domains:
            set_relationship(
                db, str(domain), rel_type,
                note=f"Imported from {path}",
                suppress=suppress,
                source="import",
            )
            count += 1

    return count
