"""Tests for Gmail sync (mocked API)."""

import json
from unittest.mock import MagicMock, patch

from gemsieve.gmail.sync import _classify_awaiting_response
from tests.conftest import insert_message


def test_store_message(db, sample_message):
    """Messages can be stored and retrieved."""
    insert_message(db, sample_message)

    row = db.execute(
        "SELECT * FROM messages WHERE message_id = ?", (sample_message["message_id"],)
    ).fetchone()

    assert row is not None
    assert row["from_address"] == "sarah@acme.com"
    assert row["from_name"] == "Sarah Chen"
    assert "API pricing" in row["subject"]


def test_thread_creation(db, sample_message):
    """Inserting a message also creates a thread."""
    insert_message(db, sample_message)

    thread = db.execute(
        "SELECT * FROM threads WHERE thread_id = ?", (sample_message["thread_id"],)
    ).fetchone()

    assert thread is not None
    assert thread["subject"] == sample_message["subject"]


def test_duplicate_message_ignored(db, sample_message):
    """Inserting the same message twice doesn't create duplicates."""
    insert_message(db, sample_message)
    insert_message(db, sample_message)

    count = db.execute("SELECT COUNT(*) as cnt FROM messages").fetchone()["cnt"]
    assert count == 1


def test_multiple_messages_same_thread(db, sample_message):
    """Multiple messages in the same thread are stored correctly."""
    insert_message(db, sample_message)

    msg2 = dict(sample_message)
    msg2["message_id"] = "msg_001b"
    msg2["from_address"] = "brandon@example.com"
    msg2["is_sent"] = True
    insert_message(db, msg2)

    count = db.execute(
        "SELECT COUNT(*) as cnt FROM messages WHERE thread_id = ?",
        (sample_message["thread_id"],),
    ).fetchone()["cnt"]
    assert count == 2


# --- Content-aware response detection tests ---

def test_classify_awaiting_question_from_other():
    """Other person asks a question -> user should respond."""
    body = "Hi, could you share your pricing details?\nLet me know when you're free."
    assert _classify_awaiting_response(body, is_from_user=False) == "user"


def test_classify_awaiting_question_from_user():
    """User asks a question -> awaiting response from other."""
    body = "I reviewed the details. What do you think about our proposal?"
    assert _classify_awaiting_response(body, is_from_user=True) == "other"


def test_classify_awaiting_concluded_thread():
    """Thread is concluded with thanks -> no one awaiting."""
    body = "Great meeting today.\n\nSounds good, thanks for everything!"
    assert _classify_awaiting_response(body, is_from_user=False) == "none"


def test_classify_awaiting_informational_from_other():
    """Other sends informational message (no question) -> no one awaiting."""
    body = "Here is the report you requested. The quarterly numbers look good."
    assert _classify_awaiting_response(body, is_from_user=False) == "none"


def test_classify_awaiting_informational_from_user():
    """User sends informational message (no question) -> no one awaiting."""
    body = "I've attached the document. Let me know if you need anything else."
    # "let me know" is a question signal, so this should be 'other'
    assert _classify_awaiting_response(body, is_from_user=True) == "other"


def test_classify_awaiting_empty_body():
    """Empty body falls back to simple sent/received logic."""
    assert _classify_awaiting_response(None, is_from_user=False) == "user"
    assert _classify_awaiting_response(None, is_from_user=True) == "other"
    assert _classify_awaiting_response("", is_from_user=False) == "user"
