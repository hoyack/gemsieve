"""Stage 1: Header forensics and ESP identification."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from email.utils import parsedate_to_datetime

from gemsieve.esp_rules import load_esp_rules, match_esp


def extract_metadata(db: sqlite3.Connection, esp_rules_path: str = "esp_rules.yaml") -> int:
    """Parse headers for all unprocessed messages, identify ESP, compute temporal patterns.

    Returns count of messages processed.
    """
    esp_rules = load_esp_rules(esp_rules_path)

    # Get messages not yet in parsed_metadata
    rows = db.execute(
        """SELECT m.message_id, m.headers_raw, m.from_address, m.date
           FROM messages m
           LEFT JOIN parsed_metadata pm ON m.message_id = pm.message_id
           WHERE pm.message_id IS NULL"""
    ).fetchall()

    processed = 0
    for row in rows:
        msg_id = row["message_id"]
        from_address = row["from_address"] or ""
        sender_domain = from_address.split("@")[1] if "@" in from_address else ""

        # Parse headers
        headers: dict[str, list[str]] = {}
        if row["headers_raw"]:
            try:
                headers = json.loads(row["headers_raw"])
            except (json.JSONDecodeError, TypeError):
                pass

        # Extract Return-Path / envelope sender
        return_path_vals = headers.get("return-path", [])
        envelope_sender = ""
        if return_path_vals:
            rp = return_path_vals[0]
            match = re.search(r"<([^>]+)>", rp)
            envelope_sender = match.group(1) if match else rp.strip()

        # ESP fingerprinting
        esp_name, esp_confidence = match_esp(headers, sender_domain, esp_rules)

        # DKIM domain
        dkim_domain = None
        dkim_vals = headers.get("dkim-signature", [])
        if dkim_vals:
            dkim_match = re.search(r"d=([^\s;]+)", dkim_vals[0])
            if dkim_match:
                dkim_domain = dkim_match.group(1)

        # SPF result
        spf_result = _extract_auth_result(headers, "spf")

        # DMARC result
        dmarc_result = _extract_auth_result(headers, "dmarc")

        # Sending IP from Received headers
        sending_ip = None
        received_vals = headers.get("received", [])
        if received_vals:
            # Last received header (outermost) typically has the originating IP
            ip_match = re.search(r"\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]", received_vals[-1])
            if ip_match:
                sending_ip = ip_match.group(1)

        # List-Unsubscribe
        unsub_url = None
        unsub_email = None
        unsub_vals = headers.get("list-unsubscribe", [])
        if unsub_vals:
            unsub_str = unsub_vals[0]
            url_match = re.search(r"<(https?://[^>]+)>", unsub_str)
            if url_match:
                unsub_url = url_match.group(1)
            mailto_match = re.search(r"<mailto:([^>]+)>", unsub_str)
            if mailto_match:
                unsub_email = mailto_match.group(1)

        # Is bulk?
        precedence_vals = headers.get("precedence", [])
        is_bulk = any(v.lower().strip() in ("bulk", "list", "junk") for v in precedence_vals)
        if not is_bulk and unsub_url:
            is_bulk = True  # Has unsubscribe → likely bulk

        db.execute(
            """INSERT OR REPLACE INTO parsed_metadata
               (message_id, sender_domain, envelope_sender, esp_identified, esp_confidence,
                dkim_domain, spf_result, dmarc_result, sending_ip,
                list_unsubscribe_url, list_unsubscribe_email, is_bulk)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, sender_domain, envelope_sender, esp_name, esp_confidence,
             dkim_domain, spf_result, dmarc_result, sending_ip,
             unsub_url, unsub_email, is_bulk),
        )
        processed += 1

    # Compute sender temporal patterns
    _compute_sender_temporal(db)

    db.commit()
    return processed


def _extract_auth_result(headers: dict[str, list[str]], protocol: str) -> str | None:
    """Extract SPF/DMARC result from Authentication-Results header."""
    auth_vals = headers.get("authentication-results", [])
    for val in auth_vals:
        pattern = rf"{protocol}=(\w+)"
        match = re.search(pattern, val, re.IGNORECASE)
        if match:
            return match.group(1).lower()

    # Also check dedicated Received-SPF header for SPF
    if protocol == "spf":
        spf_vals = headers.get("received-spf", [])
        if spf_vals:
            result = spf_vals[0].strip().split()[0].lower()
            if result in ("pass", "fail", "softfail", "neutral", "none", "temperror", "permerror"):
                return result

    return None


def _compute_sender_temporal(db: sqlite3.Connection) -> None:
    """Aggregate temporal patterns per sender domain."""
    rows = db.execute(
        """SELECT pm.sender_domain, m.date
           FROM parsed_metadata pm
           JOIN messages m ON pm.message_id = m.message_id
           WHERE pm.sender_domain != ''
           ORDER BY pm.sender_domain, m.date"""
    ).fetchall()

    # Group by domain
    domain_dates: dict[str, list[datetime]] = {}
    for row in rows:
        domain = row["sender_domain"]
        date_str = row["date"]
        if not date_str:
            continue
        try:
            dt = parsedate_to_datetime(date_str)
            domain_dates.setdefault(domain, []).append(dt)
        except Exception:
            pass

    for domain, dates in domain_dates.items():
        dates.sort()
        total = len(dates)
        first_seen = dates[0].isoformat()
        last_seen = dates[-1].isoformat()

        # Average frequency
        avg_freq = None
        if total > 1:
            gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
            avg_freq = sum(gaps) / len(gaps) if gaps else None

        # Most common send hour and day
        hours = Counter(d.hour for d in dates)
        days = Counter(d.weekday() for d in dates)
        most_common_hour = hours.most_common(1)[0][0] if hours else None
        most_common_day = days.most_common(1)[0][0] if days else None

        db.execute(
            """INSERT OR REPLACE INTO sender_temporal
               (sender_domain, first_seen, last_seen, total_messages,
                avg_frequency_days, most_common_send_hour, most_common_send_day)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (domain, first_seen, last_seen, total, avg_freq,
             most_common_hour, most_common_day),
        )
