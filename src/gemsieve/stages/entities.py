"""Stage 3: Entity extraction using spaCy NER and regex."""

from __future__ import annotations

import json
import re
import sqlite3

# Module-level spaCy model cache
_nlp = None


def _get_nlp(model_name: str = "en_core_web_sm"):
    """Load and cache spaCy model."""
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load(model_name)
    return _nlp


def extract_entities(
    db: sqlite3.Connection,
    spacy_model: str = "en_core_web_sm",
    entity_config=None,
) -> int:
    """Extract entities from parsed content for unprocessed messages.

    Args:
        entity_config: EntityConfig instance controlling which extraction types are enabled.

    Returns count of messages processed.
    """
    # Get messages with parsed content but no entities yet
    rows = db.execute(
        """SELECT pc.message_id, pc.body_clean, pc.signature_block,
                  m.from_address, m.from_name, m.subject, m.cc_addresses
           FROM parsed_content pc
           JOIN messages m ON pc.message_id = m.message_id
           LEFT JOIN extracted_entities ee ON pc.message_id = ee.message_id
           WHERE ee.message_id IS NULL"""
    ).fetchall()

    if not rows:
        return 0

    nlp = _get_nlp(spacy_model)
    processed = 0

    # Determine toggles from config
    do_monetary = entity_config.extract_monetary if entity_config else True
    do_dates = entity_config.extract_dates if entity_config else True
    do_procurement = entity_config.extract_procurement if entity_config else True

    for row in rows:
        msg_id = row["message_id"]
        body_clean = row["body_clean"] or ""
        signature_block = row["signature_block"] or ""
        from_name = row["from_name"] or ""
        from_address = row["from_address"] or ""
        subject = row["subject"] or ""

        entities: list[dict] = []

        # NER on body text
        if body_clean:
            doc = nlp(body_clean[:50000])  # limit to avoid OOM on huge emails
            for ent in doc.ents:
                if ent.label_ in ("PERSON", "ORG", "GPE", "MONEY", "DATE"):
                    entity_type = _map_spacy_label(ent.label_)
                    entities.append({
                        "entity_type": entity_type,
                        "entity_value": ent.text,
                        "entity_normalized": ent.text.strip(),
                        "context": _get_context(body_clean, ent.start_char, ent.end_char),
                        "confidence": 0.8,
                        "source": "body",
                    })

        # NER on signature block
        if signature_block:
            doc = nlp(signature_block)
            for ent in doc.ents:
                if ent.label_ in ("PERSON", "ORG"):
                    entity_type = _map_spacy_label(ent.label_)
                    entities.append({
                        "entity_type": entity_type,
                        "entity_value": ent.text,
                        "entity_normalized": ent.text.strip(),
                        "context": "signature",
                        "confidence": 0.9,
                        "source": "signature",
                    })

        # Add sender as a person entity with relationship classification
        if from_name:
            relationship = _classify_person_relationship("sender", "header", from_address)
            entities.append({
                "entity_type": "person",
                "entity_value": from_name,
                "entity_normalized": from_name.strip(),
                "context": f"From: {from_name} <{from_address}> ({relationship})",
                "confidence": 1.0,
                "source": "header",
            })

        # Extract CC entities as person entities
        entities.extend(_extract_cc_entities(row))

        # Regex: monetary values (controlled by config toggle)
        if do_monetary:
            entities.extend(_extract_monetary(body_clean + " " + subject))

        # Regex: dates in context with future date detection (controlled by config toggle)
        if do_dates:
            entities.extend(_extract_dates(body_clean))

        # Regex: procurement signals (controlled by config toggle)
        if do_procurement:
            entities.extend(_extract_procurement(body_clean))

        # Regex: role/title from signature
        entities.extend(_extract_roles(signature_block, from_name))

        # Store all entities
        for ent in entities:
            db.execute(
                """INSERT INTO extracted_entities
                   (message_id, entity_type, entity_value, entity_normalized,
                    context, confidence, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, ent["entity_type"], ent["entity_value"],
                 ent["entity_normalized"], ent["context"],
                 ent["confidence"], ent["source"]),
            )

        processed += 1

    db.commit()
    return processed


def _classify_person_relationship(role: str, source: str, from_address: str) -> str:
    """Classify person relationship based on role, source, and email patterns.

    Returns: decision_maker, automated, vendor_contact, or peer.
    """
    address_lower = from_address.lower() if from_address else ""

    # Automated senders
    automated_patterns = [
        "noreply", "no-reply", "donotreply", "notifications", "mailer-daemon",
        "bounce", "automated", "system", "alerts",
    ]
    local_part = address_lower.split("@")[0] if "@" in address_lower else ""
    if any(p in local_part for p in automated_patterns):
        return "automated"

    # Decision maker patterns in role/title context
    decision_maker_titles = [
        "ceo", "cto", "cfo", "coo", "cmo", "founder", "co-founder",
        "president", "vp", "vice president", "director", "head of", "partner",
    ]
    role_lower = role.lower() if role else ""
    if any(t in role_lower for t in decision_maker_titles):
        return "decision_maker"

    # Vendor contact patterns
    vendor_patterns = ["sales", "support", "billing", "account", "success"]
    if any(p in local_part for p in vendor_patterns):
        return "vendor_contact"

    return "peer"


def _extract_cc_entities(message_row) -> list[dict]:
    """Extract CC addresses as person entities."""
    entities = []
    cc_raw = message_row["cc_addresses"]
    if not cc_raw:
        return entities

    try:
        cc_list = json.loads(cc_raw)
    except (json.JSONDecodeError, TypeError):
        return entities

    for cc in cc_list:
        if isinstance(cc, dict):
            name = cc.get("name", "")
            email = cc.get("email", "")
        elif isinstance(cc, str):
            name = ""
            email = cc
        else:
            continue

        if not email:
            continue

        relationship = _classify_person_relationship("cc", "header", email)
        entities.append({
            "entity_type": "person",
            "entity_value": name or email,
            "entity_normalized": (name or email).strip(),
            "context": f"CC: {name} <{email}> ({relationship})",
            "confidence": 0.7,
            "source": "header",
        })

    return entities


def _is_future_date(date_str: str) -> bool:
    """Check if a date string represents a future date using python-dateutil."""
    try:
        from dateutil import parser as dateutil_parser
        parsed = dateutil_parser.parse(date_str, fuzzy=True)
        from datetime import datetime, timezone
        return parsed.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return False


def _map_spacy_label(label: str) -> str:
    """Map spaCy NER labels to our entity types."""
    mapping = {
        "PERSON": "person",
        "ORG": "organization",
        "GPE": "organization",  # geopolitical entity, often useful
        "MONEY": "money",
        "DATE": "date",
    }
    return mapping.get(label, label.lower())


def _get_context(text: str, start: int, end: int, window: int = 50) -> str:
    """Get surrounding context for an entity."""
    ctx_start = max(0, start - window)
    ctx_end = min(len(text), end + window)
    return text[ctx_start:ctx_end].strip()


def _extract_monetary(text: str) -> list[dict]:
    """Extract monetary values using regex patterns."""
    entities = []

    patterns = [
        (r"\$[\d,]+(?:\.\d{2})?", "USD amount"),
        (r"\d+[kK]\s*(?:ARR|MRR|/mo|/yr)", "SaaS metric"),
        (r"\d+%\s*(?:off|discount|commission|revenue share)", "percentage offer"),
    ]

    for pattern, context in patterns:
        for match in re.finditer(pattern, text):
            entities.append({
                "entity_type": "money",
                "entity_value": match.group(0),
                "entity_normalized": match.group(0).strip(),
                "context": context,
                "confidence": 0.85,
                "source": "body",
            })

    return entities


def _extract_dates(text: str) -> list[dict]:
    """Extract dates in renewal/expiration/deadline context.

    Encodes future date detection in entity_normalized as 'renewal:future' etc.
    """
    entities = []

    patterns = [
        (r"renew(?:s|al)?\s+(?:on|by|before)\s+([A-Za-z]+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", "renewal"),
        (r"expires?\s+(?:on\s+)?([A-Za-z]+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", "expiration"),
        (r"(?:by|before|due)\s+([A-Za-z]+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", "deadline"),
    ]

    for pattern, context in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            date_str = match.group(1).strip()
            # Encode future date detection in entity_normalized
            normalized = date_str
            if _is_future_date(date_str):
                normalized = f"{context}:future"
            entities.append({
                "entity_type": "date",
                "entity_value": date_str,
                "entity_normalized": normalized,
                "context": context,
                "confidence": 0.8,
                "source": "body",
            })

    return entities


PROCUREMENT_SIGNALS = {
    "active_buying": [
        "evaluating solutions", "looking for a vendor", "RFP",
        "request for proposal", "shortlist", "proof of concept", "POC",
    ],
    "contract_activity": [
        "terms of service", "SLA", "service level agreement",
        "data processing agreement", "master service agreement", "SOW", "statement of work",
    ],
    "security_review": [
        "SOC 2", "ISO 27001", "security questionnaire",
        "vendor risk assessment", "penetration test", "GDPR compliance",
    ],
}


def _extract_procurement(text: str) -> list[dict]:
    """Extract procurement signal keywords."""
    entities = []
    text_lower = text.lower()

    for category, keywords in PROCUREMENT_SIGNALS.items():
        for keyword in keywords:
            if keyword.lower() in text_lower:
                entities.append({
                    "entity_type": "procurement_signal",
                    "entity_value": keyword,
                    "entity_normalized": category,
                    "context": category,
                    "confidence": 0.75,
                    "source": "body",
                })

    return entities


def _extract_roles(signature: str, from_name: str) -> list[dict]:
    """Extract role/title information from signature block."""
    if not signature:
        return []

    entities = []
    # Common title patterns
    title_patterns = [
        r"(?:^|\n)\s*((?:VP|Vice President|Director|Head|Manager|CEO|CTO|CFO|COO|CMO|"
        r"Founder|Co-Founder|President|Partner|Principal|Lead|Senior|Sr\.|Jr\.)"
        r"[^\n]{0,50})",
    ]

    for pattern in title_patterns:
        match = re.search(pattern, signature, re.IGNORECASE | re.MULTILINE)
        if match:
            title = match.group(1).strip()
            if len(title) < 100:  # sanity check
                entities.append({
                    "entity_type": "person",
                    "entity_value": from_name or "Unknown",
                    "entity_normalized": title,
                    "context": f"Role: {title}",
                    "confidence": 0.85,
                    "source": "signature",
                })

    return entities
