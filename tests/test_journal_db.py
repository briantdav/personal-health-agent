"""Tests for src/journal/db.py — journal entry storage."""

import pytest

from src.journal import db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


def test_save_and_get_entry():
    db.save_entry("2026-08-12", water_cups=6.0, took_creatine=1, last_meal_time="19:30")

    entry = db.get_entry("2026-08-12")

    assert entry["water_cups"] == 6.0
    assert entry["took_creatine"] == 1
    assert entry["last_meal_time"] == "19:30"


def test_get_entry_missing_date_returns_none():
    assert db.get_entry("2026-08-12") is None


def test_save_entry_merges_partial_fields():
    """db.save_entry is an upsert primitive, same as history/db.py's
    upsert_day — a full replace-per-submission is a guarantee that lives
    in src/web/journal.py (parse_form always returns every key), not here."""
    db.save_entry("2026-08-12", water_cups=6.0, took_creatine=1)
    db.save_entry("2026-08-12", water_cups=8.0)

    entry = db.get_entry("2026-08-12")

    assert entry["water_cups"] == 8.0
    assert entry["took_creatine"] == 1  # untouched by the second call


def test_save_entry_rejects_unknown_field():
    with pytest.raises(ValueError):
        db.save_entry("2026-08-12", not_a_real_field=1)
