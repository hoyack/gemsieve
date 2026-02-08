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
