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


def extract_entities(db: sqlite3.Connection, spacy_model: str = "en_core_web_sm") -> int:
    """Extract entities from parsed content for unprocessed messages.

    Returns count of messages processed.
    """
    # Get messages with parsed content but no entities yet
    rows = db.execute(
        """SELECT pc.message_id, pc.body_clean, pc.signature_block,
                  m.from_address, m.from_name, m.subject
           FROM parsed_content pc
           JOIN messages m ON pc.message_id = m.message_id
           LEFT JOIN extracted_entities ee ON pc.message_id = ee.message_id
           WHERE ee.message_id IS NULL"""
    ).fetchall()

    if not rows:
        return 0

    nlp = _get_nlp(spacy_model)
    processed = 0

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

        # Add sender as a person entity
        if from_name:
            entities.append({
                "entity_type": "person",
                "entity_value": from_name,
                "entity_normalized": from_name.strip(),
                "context": f"From: {from_name} <{from_address}>",
                "confidence": 1.0,
                "source": "header",
            })

        # Regex: monetary values
        entities.extend(_extract_monetary(body_clean + " " + subject))

        # Regex: dates in context
        entities.extend(_extract_dates(body_clean))

        # Regex: procurement signals
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
    """Extract dates in renewal/expiration/deadline context."""
    entities = []

    patterns = [
        (r"renew(?:s|al)?\s+(?:on|by|before)\s+([A-Za-z]+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", "renewal"),
        (r"expires?\s+(?:on\s+)?([A-Za-z]+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", "expiration"),
        (r"(?:by|before|due)\s+([A-Za-z]+ \d{1,2},?\s*\d{4}|\d{1,2}/\d{1,2}/\d{2,4})", "deadline"),
    ]

    for pattern, context in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            entities.append({
                "entity_type": "date",
                "entity_value": match.group(1),
                "entity_normalized": match.group(1).strip(),
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
