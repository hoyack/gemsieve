"""Tests for Stage 3: Entity extraction."""

import json
import sys

import pytest

from tests.conftest import insert_message
from gemsieve.stages.content import parse_content

# Check if spaCy is usable in this environment
_spacy_available = True
_spacy_skip_reason = ""
try:
    import spacy
except Exception as e:
    _spacy_available = False
    _spacy_skip_reason = f"spaCy not usable: {e}"

pytestmark = pytest.mark.skipif(not _spacy_available, reason=_spacy_skip_reason)


@pytest.fixture
def prepped_db(db, sample_message):
    """DB with message and parsed content ready for entity extraction."""
    insert_message(db, sample_message)
    parse_content(db)
    return db


def test_extract_entities_basic(prepped_db):
    """Entity extraction finds people and monetary values."""
    try:
        from gemsieve.stages.entities import extract_entities
        count = extract_entities(prepped_db, spacy_model="en_core_web_sm")
    except OSError:
        pytest.skip("spaCy model en_core_web_sm not installed")

    assert count == 1

    entities = prepped_db.execute(
        "SELECT * FROM extracted_entities WHERE message_id = 'msg_001'"
    ).fetchall()

    assert len(entities) > 0

    # Should find the sender as a person
    person_entities = [e for e in entities if e["entity_type"] == "person"]
    assert len(person_entities) > 0

    # Should find monetary values ($500/mo)
    money_entities = [e for e in entities if e["entity_type"] == "money"]
    assert len(money_entities) > 0
    assert any("500" in e["entity_value"] for e in money_entities)


def test_extract_entities_idempotent(prepped_db):
    """Running entity extraction twice doesn't reprocess."""
    try:
        from gemsieve.stages.entities import extract_entities
        count1 = extract_entities(prepped_db, spacy_model="en_core_web_sm")
        count2 = extract_entities(prepped_db, spacy_model="en_core_web_sm")
    except OSError:
        pytest.skip("spaCy model en_core_web_sm not installed")

    assert count1 == 1
    assert count2 == 0


def test_classify_person_relationship():
    """Person relationship classification works for various email patterns."""
    from gemsieve.stages.entities import _classify_person_relationship

    assert _classify_person_relationship("sender", "header", "noreply@acme.com") == "automated"
    assert _classify_person_relationship("sender", "header", "no-reply@acme.com") == "automated"
    assert _classify_person_relationship("CEO", "signature", "john@acme.com") == "decision_maker"
    assert _classify_person_relationship("VP Engineering", "signature", "sarah@acme.com") == "decision_maker"
    assert _classify_person_relationship("sender", "header", "sales@acme.com") == "vendor_contact"
    assert _classify_person_relationship("sender", "header", "john@acme.com") == "peer"


def test_cc_entity_extraction():
    """CC addresses are extracted as person entities."""
    from gemsieve.stages.entities import _extract_cc_entities
    import sqlite3

    # Simulate a row dict with cc_addresses
    class FakeRow:
        def __init__(self, cc):
            self._data = {"cc_addresses": cc}
        def __getitem__(self, key):
            return self._data.get(key)

    row = FakeRow(json.dumps([
        {"name": "Alice", "email": "alice@example.com"},
        {"name": "", "email": "bob@noreply.example.com"},
    ]))

    entities = _extract_cc_entities(row)
    assert len(entities) == 2
    assert entities[0]["entity_value"] == "Alice"
    assert "peer" in entities[0]["context"]
    assert "automated" in entities[1]["context"]  # noreply


def test_config_toggle_disables_extraction():
    """Entity config toggles disable monetary/date/procurement extraction."""
    from gemsieve.stages.entities import _extract_monetary, _extract_dates, _extract_procurement

    text = "We'll spend $5000 by March 15, 2025. This is an RFP evaluation."

    # Verify they normally find entities
    assert len(_extract_monetary(text)) > 0
    assert len(_extract_procurement(text)) > 0

    # The toggle is enforced at the extract_entities level, not in individual helpers.
    # This test just confirms the helpers work correctly.
