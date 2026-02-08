"""Gmail API wrapper — search, fetch, threads, history."""

from __future__ import annotations

import base64
import email.utils
import json
from typing import Any


class GmailClient:
    """Wraps the Gmail API service with pagination and message parsing."""

    def __init__(self, service, user_email: str):
        self.service = service
        self.user_email = user_email

    def search_messages(self, query: str) -> list[dict]:
        """Return all message stubs matching the Gmail search query."""
        messages: list[dict] = []
        page_token = None

        while True:
            result = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, pageToken=page_token)
                .execute()
            )
            messages.extend(result.get("messages", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return messages

    def get_message(self, message_id: str, fmt: str = "full") -> dict:
        """Fetch a single message in the specified format."""
        return (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format=fmt)
            .execute()
        )

    def get_thread(self, thread_id: str) -> dict:
        """Fetch a full thread including all messages."""
        return (
            self.service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
        )

    def list_history(self, start_history_id: str) -> list[dict]:
        """List history events since the given historyId."""
        history: list[dict] = []
        page_token = None

        while True:
            try:
                result = (
                    self.service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=start_history_id,
                        pageToken=page_token,
                    )
                    .execute()
                )
            except Exception:
                # historyId expired or invalid — caller should fall back to full sync
                return []

            history.extend(result.get("history", []))
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return history

    def get_current_history_id(self) -> str:
        """Get the current historyId from the user's profile."""
        profile = self.service.users().getProfile(userId="me").execute()
        return str(profile["historyId"])

    def parse_message(self, raw_msg: dict) -> dict:
        """Parse a raw Gmail API message into a structured dict."""
        payload = raw_msg.get("payload", {})
        headers = payload.get("headers", [])

        header_map: dict[str, str] = {}
        all_headers: dict[str, list[str]] = {}
        for h in headers:
            key = h.get("name", "").lower()
            value = h.get("value", "")
            # Keep first occurrence for simple lookups
            if key not in header_map:
                header_map[key] = value
            # Keep all for raw storage
            all_headers.setdefault(key, []).append(value)

        # Extract body parts
        body_html = ""
        body_text = ""
        attachments: list[dict] = []
        self._extract_parts(payload, body_parts={"html": [], "text": []}, attachments=attachments)

        # Reconstruct body from collected parts
        body_parts: dict[str, list] = {"html": [], "text": []}
        self._extract_parts(payload, body_parts=body_parts, attachments=attachments)
        # Reset — we double-called; let's do it once properly
        body_parts = {"html": [], "text": []}
        attachments = []
        self._extract_parts(payload, body_parts=body_parts, attachments=attachments)

        body_html = "\n".join(body_parts["html"])
        body_text = "\n".join(body_parts["text"])

        # Determine if sent by user
        from_addr = header_map.get("from", "")
        parsed_from = email.utils.parseaddr(from_addr)
        from_email = parsed_from[1].lower()
        is_sent = from_email == self.user_email.lower()

        # Parse addresses
        to_raw = header_map.get("to", "")
        cc_raw = header_map.get("cc", "")
        to_addresses = [
            {"name": n.strip(), "email": e.strip().lower()}
            for n, e in email.utils.getaddresses([to_raw]) if e
        ]
        cc_addresses = [
            {"name": n.strip(), "email": e.strip().lower()}
            for n, e in email.utils.getaddresses([cc_raw]) if e
        ]

        return {
            "message_id": raw_msg["id"],
            "thread_id": raw_msg.get("threadId", ""),
            "date": header_map.get("date"),
            "from_address": from_email,
            "from_name": parsed_from[0].strip(),
            "reply_to": header_map.get("reply-to"),
            "to_addresses": json.dumps(to_addresses),
            "cc_addresses": json.dumps(cc_addresses),
            "subject": header_map.get("subject", ""),
            "headers_raw": json.dumps(all_headers),
            "body_html": body_html,
            "body_text": body_text,
            "labels": json.dumps(raw_msg.get("labelIds", [])),
            "snippet": raw_msg.get("snippet", ""),
            "size_estimate": raw_msg.get("sizeEstimate", 0),
            "is_sent": is_sent,
            "attachments": attachments,
        }

    def _extract_parts(
        self,
        part: dict,
        body_parts: dict[str, list],
        attachments: list[dict],
    ) -> None:
        """Recursively extract body text/html and attachments from a message part."""
        mime_type = part.get("mimeType", "")
        filename = part.get("filename", "")

        if filename:
            # It's an attachment
            body_data = part.get("body", {})
            attachments.append({
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": body_data.get("size", 0),
                "attachment_id": body_data.get("attachmentId", ""),
            })
            return

        # Check for sub-parts (multipart)
        sub_parts = part.get("parts", [])
        if sub_parts:
            for sub in sub_parts:
                self._extract_parts(sub, body_parts, attachments)
            return

        # Leaf part — extract body data
        body_data = part.get("body", {}).get("data", "")
        if not body_data:
            return

        try:
            decoded = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="replace")
        except Exception:
            return

        if mime_type == "text/html":
            body_parts["html"].append(decoded)
        elif mime_type == "text/plain":
            body_parts["text"].append(decoded)
