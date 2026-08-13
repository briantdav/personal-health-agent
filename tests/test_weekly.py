"""Tests for src/web/weekly.py — the Monday weekly-review view model.

Same isolated-DB pattern as tests/test_metrics.py and tests/test_trends.py.
"""

from datetime import date

import pytest

from src.history import db as history_db
from src.journal import db as journal_db
from src.web import weekly


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


def test_week_bounds_on_a_monday_is_the_week_that_just_closed():
    # 2026-08-10 is a Monday.
    start, end = weekly.week_bounds(date(2026, 8, 10))
    assert start == date(2026, 8, 3)
    assert end == date(2026, 8, 9)


def test_week_bounds_mid_week_still_uses_the_prior_full_week():
    # 2026-08-13 is a Thursday, in the same week week_bounds treats as
    # "this week" (not yet closed) — the closed week is still last week.
    start, end = weekly.week_bounds(date(2026, 8, 13))
    assert start == date(2026, 8, 3)
    assert end == date(2026, 8, 9)


def test_is_review_day_true_only_on_monday():
    assert weekly.is_review_day(date(2026, 8, 10)) is True  # Monday
    assert weekly.is_review_day(date(2026, 8, 11)) is False  # Tuesday


def _seed_history(*days):
    with history_db.connect() as conn:
        for iso_date, fields in days:
            history_db.upsert_day(conn, iso_date, **fields)


def test_get_weekly_review_totals_and_deltas_vs_prior_week():
    # Week of 2026-08-03..09, prior week 2026-07-27..08-02.
    _seed_history(
        ("2026-08-03", {"miles": 5.0, "recovery_score": 70, "sleep_hours": 7.0}),
        ("2026-08-05", {"miles": 5.0, "recovery_score": 80, "sleep_hours": 7.4}),
        ("2026-07-27", {"miles": 3.0, "recovery_score": 60, "sleep_hours": 6.5}),
    )

    review = weekly.get_weekly_review(date(2026, 8, 10))

    assert review["miles"] == 10.0
    assert review["miles_prev"] == 3.0
    assert review["recovery"] == 75
    assert review["recovery_prev"] == 60
    assert review["sleep"] == 7.2
    assert review["sleep_prev"] == 6.5
    assert review["week_label"] == "3 Aug"
    assert review["next_week_label"] == "10 Aug"
    assert review["closed"] is True


def test_get_weekly_review_honors_explicit_miles_planned():
    review = weekly.get_weekly_review(date(2026, 8, 10), miles_planned=25)
    assert review["miles_planned"] == 25


def test_get_weekly_review_defaults_miles_planned_to_dash():
    review = weekly.get_weekly_review(date(2026, 8, 10))
    assert review["miles_planned"] == "—"


def test_get_weekly_review_habit_grid_matches_journal_entries():
    journal_db.save_entry("2026-08-03", drank_alcohol=1, took_creatine=1)
    journal_db.save_entry("2026-08-04", drank_alcohol=0, took_creatine=1)

    review = weekly.get_weekly_review(date(2026, 8, 10))

    alcohol = next(h for h in review["habits"] if h["key"] == "drank_alcohol")
    creatine = next(h for h in review["habits"] if h["key"] == "took_creatine")
    assert alcohol["flag"] is True
    assert alcohol["days"][0] is True  # Monday 08-03
    assert alcohol["days"][1] is False  # Tuesday 08-04
    assert creatine["flag"] is False
    assert creatine["days"][0] is True
    assert creatine["days"][1] is True


def test_get_weekly_review_habit_pct_counts_flag_habits_correctly():
    # A flagged habit (e.g. alcohol) answered "no" counts as a filled/good
    # day, same as a non-flagged habit answered "yes".
    journal_db.save_entry("2026-08-03", drank_alcohol=0)

    review = weekly.get_weekly_review(date(2026, 8, 10))

    assert review["habit_pct"] == 100  # the one answered day was "good"


def test_get_weekly_review_sessions_degrade_without_workout_title_or_pace():
    _seed_history(("2026-08-03", {"miles": 4.0}))

    review = weekly.get_weekly_review(date(2026, 8, 10))

    monday_session = review["sessions"][0]
    assert monday_session["title"] == "Run"  # no workout_title column yet -> falls back
    assert monday_session["pace"] is None  # no avg_pace column yet


def test_get_weekly_review_rest_day_session_has_no_title_fallback_to_rest():
    review = weekly.get_weekly_review(date(2026, 8, 10))  # nothing seeded at all

    assert review["sessions"][0]["title"] == "Rest"


def test_get_weekly_review_note_and_next_week_summary_are_placeholders():
    review = weekly.get_weekly_review(date(2026, 8, 10))
    assert review["note"] is None
    assert review["next_week_summary"] == "Plan not synced yet"
