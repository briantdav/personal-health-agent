"""SQLite-backed local cache of daily Garmin metrics.

A year of daily history across ~10 metrics is too slow (and, for the
recovery score, too rate-limit-risky — no bulk endpoint exists for it) to
pull from Garmin on every dashboard request. src/history/sync.py backfills
this database; src/web/trends.py reads from it, never from Garmin directly.

One row per calendar date. Columns are nullable — a day with no logged
activity has miles/workout_hours as NULL (not 0), so aggregates don't
silently treat "never measured" as "measured zero".
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "history.db"

# Every non-key column in daily_metrics, in insertion order, with its SQL type.
FIELD_TYPES = {
    "miles": "REAL",
    "workout_hours": "REAL",
    "sleep_hours": "REAL",
    "deep_sleep_hours": "REAL",
    "rem_sleep_hours": "REAL",
    "sleep_score": "INTEGER",
    "resting_heart_rate": "REAL",
    "hrv_overnight_avg": "REAL",
    "body_battery_peak": "INTEGER",
    "vo2_max": "REAL",
    "recovery_score": "INTEGER",
    "recovery_level": "TEXT",
}
FIELDS = tuple(FIELD_TYPES)

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    {", ".join(f"{name} {sqltype}" for name, sqltype in FIELD_TYPES.items())},
    synced_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def db_path() -> Path:
    """The DB file to use — override with HISTORY_DB_PATH (tests do this)."""
    override = os.getenv("HISTORY_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def upsert_day(conn: sqlite3.Connection, date: str, **fields: Any) -> None:
    """Insert or update one day's row. Unknown kwargs raise, so a typo'd
    field name fails loudly instead of silently being dropped."""
    unknown = set(fields) - set(FIELDS)
    if unknown:
        raise ValueError(f"Unknown daily_metrics field(s): {sorted(unknown)}")

    columns = ["date", *fields.keys(), "synced_at"]
    placeholders = ", ".join("?" for _ in columns)
    updates = ", ".join(f"{col}=excluded.{col}" for col in fields)
    sql = (
        f"INSERT INTO daily_metrics ({', '.join(columns)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT(date) DO UPDATE SET {updates}, synced_at=excluded.synced_at"
    )
    conn.execute(sql, (date, *fields.values(), _now()))


def get_range(start: str, end: str) -> list[dict[str, Any]]:
    """Rows with date in [start, end], ordered by date. Only days that have
    at least one synced value show up here — callers fill the gaps."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_metrics WHERE date BETWEEN ? AND ? ORDER BY date",
            (start, end),
        ).fetchall()
    return [dict(row) for row in rows]


def _now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
