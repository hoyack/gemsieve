"""Stage 4: AI-powered classification of senders."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone


def classify_messages(
    db: sqlite3.Connection,
    model_spec: str = "ollama:mistral-nemo",
    batch_size: int = 10,
    max_body_chars: int = 2000,
    ai_config: dict | None = None,
    use_crew: bool = False,
) -> int:
    """Classify unprocessed messages using AI.

    Groups messages by sender_domain and classifies each sender once
    using the most representative messages.

    Args:
        use_crew: If True, use CrewAI multi-agent mode instead of direct calls.

    Returns count of messages classified.
    """
    # Get unclassified messages grouped by sender domain
    rows = db.execute(
        """SELECT m.message_id, m.from_address, m.from_name, m.subject,
                  pm.sender_domain, pm.esp_identified,
                  pc.body_clean, pc.cta_texts, pc.offer_types
           FROM messages m
           JOIN parsed_metadata pm ON m.message_id = pm.message_id
           LEFT JOIN parsed_content pc ON m.message_id = pc.message_id
           LEFT JOIN ai_classification ac ON m.message_id = ac.message_id
           WHERE ac.message_id IS NULL AND pm.sender_domain != ''
           ORDER BY pm.sender_domain, m.date DESC"""
    ).fetchall()

    if not rows:
        return 0

    # Group by sender domain
    domain_messages: dict[str, list] = {}
    for row in rows:
        domain = row["sender_domain"]
        domain_messages.setdefault(domain, []).append(row)

    classified = 0

    for domain, messages in domain_messages.items():
        # Check for sender-scoped overrides
        overrides = _get_sender_overrides(db, domain)

        # Take up to 3 most representative messages for classification
        sample = messages[:3]

        # Get entity summary for context
        entity_summary = _get_entity_summary(db, [m["message_id"] for m in sample])

        # Build prompt context
        msg = sample[0]
        body = (msg["body_clean"] or "")[:max_body_chars]
        cta_texts = msg["cta_texts"] or "[]"
        offer_types = msg["offer_types"] or "[]"

        sender_data = {
            "from_name": msg["from_name"] or "",
            "from_address": msg["from_address"] or "",
            "subject": msg["subject"] or "",
            "esp_identified": msg["esp_identified"] or "unknown",
            "offer_types": offer_types,
            "cta_texts": cta_texts,
            "extracted_entities_summary": entity_summary,
            "body_clean": body,
        }

        try:
            if use_crew:
                from gemsieve.ai.crews import crew_classify
                result = crew_classify(sender_data, model_spec=model_spec, ai_config=ai_config)
            else:
                from gemsieve.ai import get_provider
                from gemsieve.ai.prompts import CLASSIFICATION_PROMPT

                provider, model_name = get_provider(model_spec, config=ai_config)
                prompt = CLASSIFICATION_PROMPT.format(**sender_data)
                result = provider.complete(
                    prompt=prompt,
                    model=model_name,
                    system="You are an email intelligence analyst. Respond with JSON only.",
                    response_format="json",
                )
        except Exception as e:
            print(f"  AI classification failed for {domain}: {e}")
            continue

        # Apply overrides
        for field_name, value in overrides.items():
            result[field_name] = value

        has_override = bool(overrides)

        # Store classification for all messages from this sender
        for m in messages:
            db.execute(
                """INSERT OR REPLACE INTO ai_classification
                   (message_id, industry, company_size_estimate,
                    marketing_sophistication, sender_intent, product_type,
                    product_description, pain_points, target_audience,
                    partner_program_detected, renewal_signal_detected,
                    ai_confidence, model_used, has_override)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    m["message_id"],
                    result.get("industry", ""),
                    result.get("company_size_estimate", ""),
                    result.get("marketing_sophistication", 0),
                    result.get("sender_intent", ""),
                    result.get("product_type", ""),
                    result.get("product_description", ""),
                    json.dumps(result.get("pain_points_addressed", [])),
                    result.get("target_audience", ""),
                    result.get("partner_program_detected", False),
                    result.get("renewal_signal_detected", False),
                    result.get("confidence", 0.0),
                    model_spec,
                    has_override,
                ),
            )
            classified += 1

    db.commit()
    return classified


def _get_sender_overrides(db: sqlite3.Connection, sender_domain: str) -> dict:
    """Get active overrides for a sender domain."""
    rows = db.execute(
        """SELECT field_name, corrected_value FROM classification_overrides
           WHERE sender_domain = ? AND override_scope = 'sender'
           ORDER BY created_at DESC""",
        (sender_domain,),
    ).fetchall()

    overrides = {}
    for row in rows:
        if row["field_name"] not in overrides:
            overrides[row["field_name"]] = row["corrected_value"]
    return overrides


def _get_entity_summary(db: sqlite3.Connection, message_ids: list[str]) -> str:
    """Get a brief summary of extracted entities for given messages."""
    if not message_ids:
        return "None"

    placeholders = ",".join("?" for _ in message_ids)
    rows = db.execute(
        f"""SELECT entity_type, entity_value, context
            FROM extracted_entities
            WHERE message_id IN ({placeholders})
            ORDER BY confidence DESC
            LIMIT 20""",
        message_ids,
    ).fetchall()

    if not rows:
        return "None"

    parts = []
    for row in rows:
        parts.append(f"{row['entity_type']}: {row['entity_value']}")
    return "; ".join(parts)
