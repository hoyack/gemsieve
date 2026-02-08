"""Stage 0: Gmail ingestion — full and incremental sync."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone

from gemsieve.gmail.client import GmailClient


class SyncEngine:
    """Handles full and incremental Gmail sync to local database."""

    def __init__(self, client: GmailClient, db: sqlite3.Connection):
        self.client = client
        self.db = db

    def full_sync(self, query: str, progress_callback=None) -> int:
        """Pull all messages matching query and store in DB.

        Returns count of new messages stored.
        """
        stubs = self.client.search_messages(query)
        total = len(stubs)
        stored = 0

        for i, stub in enumerate(stubs, 1):
            msg_id = stub["id"]

            # Skip if already ingested
            existing = self.db.execute(
                "SELECT 1 FROM messages WHERE message_id = ?", (msg_id,)
            ).fetchone()
            if existing:
                continue

            raw_msg = self.client.get_message(msg_id)
            parsed = self.client.parse_message(raw_msg)
            self._store_message(parsed)
            stored += 1

            if progress_callback and (i % 50 == 0 or i == total):
                progress_callback(i, total, stored)

        # Update thread metadata
        self._update_threads()

        # Update sync state
        history_id = self.client.get_current_history_id()
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """INSERT INTO sync_state (id, last_history_id, last_full_sync, total_messages_synced)
               VALUES (1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   last_history_id = excluded.last_history_id,
                   last_full_sync = excluded.last_full_sync,
                   total_messages_synced = total_messages_synced + excluded.total_messages_synced""",
            (history_id, now, stored),
        )
        self.db.commit()
        return stored

    def incremental_sync(self, progress_callback=None) -> int:
        """Sync only new/modified messages since last sync.

        Falls back to full sync if historyId is expired.
        Returns count of new messages stored.
        """
        row = self.db.execute(
            "SELECT last_history_id FROM sync_state WHERE id = 1"
        ).fetchone()
        if not row or not row["last_history_id"]:
            raise RuntimeError("No previous sync state found. Run a full sync first.")

        history = self.client.list_history(row["last_history_id"])
        if not history:
            # historyId expired — caller should run full sync
            return -1

        # Collect unique message IDs from history events
        message_ids = set()
        for event in history:
            for msg_added in event.get("messagesAdded", []):
                message_ids.add(msg_added["message"]["id"])

        stored = 0
        total = len(message_ids)
        for i, msg_id in enumerate(message_ids, 1):
            # Skip if already ingested
            existing = self.db.execute(
                "SELECT 1 FROM messages WHERE message_id = ?", (msg_id,)
            ).fetchone()
            if existing:
                continue

            raw_msg = self.client.get_message(msg_id)
            parsed = self.client.parse_message(raw_msg)
            self._store_message(parsed)
            stored += 1

            if progress_callback and (i % 50 == 0 or i == total):
                progress_callback(i, total, stored)

        # Update threads
        self._update_threads()

        # Update sync state
        history_id = self.client.get_current_history_id()
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """UPDATE sync_state SET
                last_history_id = ?,
                last_incremental_sync = ?,
                total_messages_synced = total_messages_synced + ?
               WHERE id = 1""",
            (history_id, now, stored),
        )
        self.db.commit()
        return stored

    def _store_message(self, parsed: dict) -> None:
        """Insert a parsed message and its attachments into the DB."""
        attachments = parsed.pop("attachments", [])

        # Ensure thread row exists before inserting message (FK constraint)
        self.db.execute(
            "INSERT OR IGNORE INTO threads (thread_id) VALUES (?)",
            (parsed["thread_id"],),
        )

        self.db.execute(
            """INSERT OR IGNORE INTO messages
               (message_id, thread_id, date, from_address, from_name, reply_to,
                to_addresses, cc_addresses, subject, headers_raw, body_html, body_text,
                labels, snippet, size_estimate, is_sent)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                parsed["message_id"], parsed["thread_id"], parsed["date"],
                parsed["from_address"], parsed["from_name"], parsed["reply_to"],
                parsed["to_addresses"], parsed["cc_addresses"], parsed["subject"],
                parsed["headers_raw"], parsed["body_html"], parsed["body_text"],
                parsed["labels"], parsed["snippet"], parsed["size_estimate"],
                parsed["is_sent"],
            ),
        )

        for att in attachments:
            self.db.execute(
                """INSERT INTO attachments (message_id, filename, mime_type, size_bytes, attachment_id)
                   VALUES (?, ?, ?, ?, ?)""",
                (parsed["message_id"], att["filename"], att["mime_type"],
                 att["size_bytes"], att["attachment_id"]),
            )

        self.db.commit()

    def _update_threads(self) -> None:
        """Compute/update thread metadata from stored messages."""
        thread_ids = self.db.execute(
            "SELECT DISTINCT thread_id FROM messages WHERE thread_id IS NOT NULL"
        ).fetchall()

        for row in thread_ids:
            tid = row["thread_id"]
            messages = self.db.execute(
                """SELECT message_id, date, from_address, is_sent, subject
                   FROM messages WHERE thread_id = ? ORDER BY date""",
                (tid,),
            ).fetchall()

            if not messages:
                continue

            participants = set()
            first_date = None
            last_date = None
            last_sender = None
            user_participated = False
            user_last_replied = None
            subject = messages[0]["subject"] or ""

            # Strip Re:/Fwd: prefixes
            clean_subject = re.sub(r"^(?:Re|Fwd|Fw):\s*", "", subject, flags=re.IGNORECASE).strip()

            for msg in messages:
                if msg["from_address"]:
                    participants.add(msg["from_address"])
                if msg["date"]:
                    if first_date is None:
                        first_date = msg["date"]
                    last_date = msg["date"]
                last_sender = msg["from_address"]
                if msg["is_sent"]:
                    user_participated = True
                    user_last_replied = msg["date"]

            # Determine awaiting_response_from
            if messages:
                last_msg = messages[-1]
                if last_msg["is_sent"]:
                    awaiting = "other"
                else:
                    awaiting = "user"
            else:
                awaiting = "none"

            # Compute dormancy
            days_dormant = 0
            if last_date:
                try:
                    from email.utils import parsedate_to_datetime
                    last_dt = parsedate_to_datetime(last_date)
                    days_dormant = (datetime.now(timezone.utc) - last_dt).days
                except Exception:
                    pass

            self.db.execute(
                """INSERT INTO threads
                   (thread_id, subject, participant_count, message_count,
                    first_message_date, last_message_date, last_sender,
                    user_participated, user_last_replied, awaiting_response_from, days_dormant)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(thread_id) DO UPDATE SET
                       subject = excluded.subject,
                       participant_count = excluded.participant_count,
                       message_count = excluded.message_count,
                       first_message_date = excluded.first_message_date,
                       last_message_date = excluded.last_message_date,
                       last_sender = excluded.last_sender,
                       user_participated = excluded.user_participated,
                       user_last_replied = excluded.user_last_replied,
                       awaiting_response_from = excluded.awaiting_response_from,
                       days_dormant = excluded.days_dormant""",
                (
                    tid, clean_subject, len(participants), len(messages),
                    first_date, last_date, last_sender,
                    user_participated, user_last_replied, awaiting, days_dormant,
                ),
            )

        self.db.commit()
