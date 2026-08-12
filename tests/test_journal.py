"""Tests for src/web/journal.py — form parsing and the full-replace
guarantee (checkbox absence = False, conditional fields cleared)."""

import pytest

from src.journal import db
from src.web import journal


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


def test_parse_form_unchecked_checkbox_is_false():
    # took_creatine simply isn't in the submitted form — as real unchecked
    # HTML checkboxes behave.
    fields = journal.parse_form({"water_cups": "6"})

    assert fields["took_creatine"] == 0
    assert fields["water_cups"] == 6.0


def test_parse_form_checked_checkbox_is_true():
    fields = journal.parse_form({"took_creatine": "on"})

    assert fields["took_creatine"] == 1


def test_parse_form_blank_number_and_time_are_none():
    fields = journal.parse_form({"water_cups": "", "last_meal_time": ""})

    assert fields["water_cups"] is None
    assert fields["last_meal_time"] is None


def test_parse_form_clears_conditional_fields_when_parent_is_false():
    fields = journal.parse_form({"drink_count": "3", "last_drink_time": "22:00"})
    # drank_alcohol wasn't checked, so the alcohol-detail fields shouldn't
    # survive even though raw values were present in the submission.

    assert fields["drank_alcohol"] == 0
    assert fields["drink_count"] is None
    assert fields["last_drink_time"] is None


def test_parse_form_keeps_conditional_fields_when_parent_is_true():
    fields = journal.parse_form({"drank_alcohol": "on", "drink_count": "3", "last_drink_time": "22:00"})

    assert fields["drank_alcohol"] == 1
    assert fields["drink_count"] == 3.0
    assert fields["last_drink_time"] == "22:00"


def test_save_entry_is_a_full_replace_across_submissions():
    journal.save_entry("2026-08-12", {"took_creatine": "on", "drank_alcohol": "on", "drink_count": "2"})
    # Resubmitting the same day without checking those boxes should clear
    # them, not leave yesterday's checked state behind.
    journal.save_entry("2026-08-12", {"water_cups": "6"})

    values = journal.get_values("2026-08-12")

    assert values["took_creatine"] == 0
    assert values["drank_alcohol"] == 0
    assert values["drink_count"] is None
    assert values["water_cups"] == 6.0


def test_get_values_defaults_when_no_entry_yet():
    values = journal.get_values("2026-08-12")

    assert values["water_cups"] is None
    assert values["took_creatine"] is None  # no entry at all yet — unanswered, not "no"


def test_already_submitted():
    assert journal.already_submitted("2026-08-12") is False

    journal.save_entry("2026-08-12", {})

    assert journal.already_submitted("2026-08-12") is True


def test_get_values_defaults_to_today(monkeypatch):
    from datetime import date as real_date

    class FixedDate(real_date):
        @classmethod
        def today(cls):
            return real_date(2026, 8, 12)

    monkeypatch.setattr(journal, "_date", FixedDate)
    journal.save_entry("2026-08-12", {"water_cups": "5"})

    assert journal.get_values()["water_cups"] == 5.0
    assert journal.already_submitted() is True
