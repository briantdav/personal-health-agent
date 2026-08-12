"""Tests for src/web/trends.py — daily/weekly/monthly rollups."""

import pytest

from src.history import db
from src.web import trends


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


def _seed(*days):
    """days: list of (date, field_kwargs) tuples."""
    with db.connect() as conn:
        for iso_date, fields in days:
            db.upsert_day(conn, iso_date, **fields)


def test_daily_series_fills_gaps_with_none():
    _seed(("2026-08-01", {"miles": 5}), ("2026-08-03", {"miles": 3}))

    series = [
        row
        for row in trends.get_daily_series(days=3650)
        if row["date"] in ("2026-08-01", "2026-08-02", "2026-08-03")
    ]

    by_date = {row["date"]: row for row in series}
    assert by_date["2026-08-01"]["miles"] == 5
    assert by_date["2026-08-02"]["miles"] is None
    assert by_date["2026-08-03"]["miles"] == 3


def test_vo2_max_forward_fills_sparse_readings():
    _seed(("2026-08-01", {"vo2_max": 54.0}), ("2026-08-04", {"vo2_max": 55.0}))

    series = {
        row["date"]: row["vo2_max"]
        for row in trends.get_daily_series(days=3650)
        if row["date"] in ("2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04")
    }

    assert series == {
        "2026-08-01": 54.0,
        "2026-08-02": 54.0,  # carried forward
        "2026-08-03": 54.0,  # carried forward
        "2026-08-04": 55.0,
    }


def test_weekly_aggregation_sums_volume_metrics():
    # 2026-08-03 through 2026-08-09 is one ISO week.
    _seed(
        ("2026-08-03", {"miles": 3, "sleep_score": 80}),
        ("2026-08-04", {"miles": 4, "sleep_score": 70}),
    )

    weekly = trends.get_weekly_series(days=3650)
    week = next(w for w in weekly if w["period"] == "2026-W32")

    assert week["miles"] == 7  # summed — weekly mileage, not a daily average
    assert week["sleep_score"] == 75  # averaged


def test_monthly_aggregation_groups_by_calendar_month():
    _seed(("2026-08-01", {"resting_heart_rate": 46}), ("2026-08-08", {"resting_heart_rate": 44}))

    monthly = trends.get_monthly_series(days=3650)
    month = next(m for m in monthly if m["period"] == "2026-08")

    assert month["resting_heart_rate"] == 45


def test_get_trends_reports_has_data():
    assert trends.get_trends(days=30)["has_data"] is False

    _seed(("2026-08-01", {"miles": 1}))

    assert trends.get_trends(days=3650)["has_data"] is True
