"""SQLite-backed storage for morning journal entries.

Shares data/history.db with src/history/db.py — different table
(journal_entries, not daily_metrics), so this stays clearly "user-entered"
rather than "synced from Garmin", but living in the same file makes
joining habits against recovery/sleep by date trivial later.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from src.history.db import db_path

# Every non-key column, with its SQL type. Booleans store as 0/1
# (SQLite has no native bool); times store as "HH:MM" text.
FIELD_TYPES = {
    "water_cups": "REAL",
    "took_creatine": "INTEGER",
    "hit_protein_goal": "INTEGER",
    "read_before_bed": "INTEGER",
    "read_devotional": "INTEGER",
    "stretched_before_bed": "INTEGER",
    "cold_plunge": "INTEGER",
    "sauna_or_hot_tub": "INTEGER",
    "took_magnesium": "INTEGER",
    "drank_alcohol": "INTEGER",
    "drink_count": "REAL",
    "last_drink_time": "TEXT",
    "used_phone_in_bed": "INTEGER",
    "worked_late": "INTEGER",
    "meditated_or_prayed": "INTEGER",
    "last_meal_time": "TEXT",
}
FIELDS = tuple(FIELD_TYPES)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS journal_entries (
    date TEXT PRIMARY KEY,
    {", ".join(f"{name} {sqltype}" for name, sqltype in FIELD_TYPES.items())},
    submitted_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """One-off renames that CREATE TABLE IF NOT EXISTS won't retroactively
    apply to a table that already exists on disk. Each check is a no-op
    once applied, so this is safe to run on every connect()."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(journal_entries)")}
    if "ready_before_bed" in columns and "read_before_bed" not in columns:
        conn.execute("ALTER TABLE journal_entries RENAME COLUMN ready_before_bed TO read_before_bed")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(SCHEMA)
        _migrate(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_entry(entry_date: str, **fields: Any) -> None:
    """Upsert — merges the given fields into the day's row, same as
    src/history/db.py's upsert_day. Callers that want a full replace
    (the journal form does, via src/web/journal.py's parse_form, which
    always returns every question key) just need to pass every field."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError(f"Unknown journal_entries field(s): {sorted(unknown)}")

    columns = ["date", *fields.keys(), "submitted_at"]
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{col}=excluded.{col}" for col in fields)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sql = (
        f"INSERT INTO journal_entries ({', '.join(columns)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {updates}, submitted_at=excluded.submitted_at"
    )
    with connect() as conn:
        conn.execute(sql, (entry_date, *fields.values(), now))


def get_entry(entry_date: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM journal_entries WHERE date = ?", (entry_date,)
        ).fetchone()
    return dict(row) if row else None
