"""Tests for src/history/db.py — the local SQLite metrics cache.

Each test points HISTORY_DB_PATH at a fresh tmp_path file, so nothing here
touches the real data/history.db.
"""

import pytest

from src.history import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


def test_upsert_and_read_back():
    with db.connect() as conn:
        db.upsert_day(conn, "2026-08-11", miles=10.01, sleep_hours=6.3)

    rows = db.get_range("2026-08-01", "2026-08-31")

    assert len(rows) == 1
    assert rows[0]["date"] == "2026-08-11"
    assert rows[0]["miles"] == 10.01
    assert rows[0]["sleep_hours"] == 6.3


def test_upsert_merges_fields_across_calls():
    """Different syncers (sleep, activities, recovery) write different
    field subsets to the same date — later writes must not clobber
    fields they don't mention."""
    with db.connect() as conn:
        db.upsert_day(conn, "2026-08-11", miles=10.01)
        db.upsert_day(conn, "2026-08-11", sleep_hours=6.3)

    rows = db.get_range("2026-08-11", "2026-08-11")

    assert rows[0]["miles"] == 10.01
    assert rows[0]["sleep_hours"] == 6.3


def test_upsert_overwrites_same_field():
    with db.connect() as conn:
        db.upsert_day(conn, "2026-08-11", recovery_score=43)
        db.upsert_day(conn, "2026-08-11", recovery_score=50)

    rows = db.get_range("2026-08-11", "2026-08-11")

    assert rows[0]["recovery_score"] == 50


def test_upsert_rejects_unknown_field():
    with db.connect() as conn:
        with pytest.raises(ValueError):
            db.upsert_day(conn, "2026-08-11", not_a_real_field=1)


def test_get_range_excludes_outside_dates():
    with db.connect() as conn:
        db.upsert_day(conn, "2026-08-01", miles=1)
        db.upsert_day(conn, "2026-08-15", miles=2)
        db.upsert_day(conn, "2026-09-01", miles=3)

    rows = db.get_range("2026-08-01", "2026-08-31")

    assert [r["date"] for r in rows] == ["2026-08-01", "2026-08-15"]
