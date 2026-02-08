"""Classification override CRUD operations."""

from __future__ import annotations

import sqlite3


def add_override(
    db: sqlite3.Connection,
    field_name: str,
    corrected_value: str,
    sender_domain: str | None = None,
    message_id: str | None = None,
) -> int:
    """Add a classification override.

    Returns the override ID.
    """
    if not sender_domain and not message_id:
        raise ValueError("Must specify either sender_domain or message_id")

    # Determine scope
    if sender_domain:
        scope = "sender"
    else:
        scope = "message"
        # Look up sender_domain from message
        row = db.execute(
            """SELECT pm.sender_domain FROM parsed_metadata pm
               WHERE pm.message_id = ?""",
            (message_id,),
        ).fetchone()
        if row:
            sender_domain = row["sender_domain"]

    # Get original value if possible
    original_value = None
    if message_id:
        row = db.execute(
            f"SELECT {field_name} FROM ai_classification WHERE message_id = ?",
            (message_id,),
        ).fetchone()
        if row:
            original_value = row[field_name]
    elif sender_domain:
        row = db.execute(
            f"""SELECT ac.{field_name} FROM ai_classification ac
                JOIN parsed_metadata pm ON ac.message_id = pm.message_id
                WHERE pm.sender_domain = ? LIMIT 1""",
            (sender_domain,),
        ).fetchone()
        if row:
            original_value = row[field_name]

    cursor = db.execute(
        """INSERT INTO classification_overrides
           (message_id, sender_domain, field_name, original_value,
            corrected_value, override_scope)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (message_id, sender_domain, field_name, str(original_value) if original_value else None,
         corrected_value, scope),
    )
    db.commit()
    return cursor.lastrowid


def list_overrides(db: sqlite3.Connection) -> list[dict]:
    """List all active overrides."""
    rows = db.execute(
        """SELECT id, message_id, sender_domain, field_name,
                  original_value, corrected_value, override_scope, created_at
           FROM classification_overrides
           ORDER BY created_at DESC"""
    ).fetchall()

    return [dict(row) for row in rows]


def override_stats(db: sqlite3.Connection) -> dict[str, dict]:
    """Compute override statistics per field.

    Returns dict of field_name -> {total_overrides, total_classifications, override_rate}.
    """
    stats: dict[str, dict] = {}

    # Count overrides per field
    override_counts = db.execute(
        """SELECT field_name, COUNT(*) as cnt
           FROM classification_overrides
           GROUP BY field_name"""
    ).fetchall()

    # Total classifications
    total_class = db.execute("SELECT COUNT(*) as cnt FROM ai_classification").fetchone()
    total = total_class["cnt"] if total_class else 0

    for row in override_counts:
        field = row["field_name"]
        count = row["cnt"]
        rate = (count / total * 100) if total > 0 else 0
        stats[field] = {
            "total_overrides": count,
            "total_classifications": total,
            "override_rate": round(rate, 1),
            "needs_tuning": rate > 20,
        }

    return stats


def delete_override(db: sqlite3.Connection, override_id: int) -> bool:
    """Delete an override by ID. Returns True if deleted."""
    cursor = db.execute(
        "DELETE FROM classification_overrides WHERE id = ?", (override_id,)
    )
    db.commit()
    return cursor.rowcount > 0
