"""Tests for src/history/sync.py — orchestration between Garmin and the DB.

All Garmin calls are mocked with real-shaped payloads (captured from an
actual account) so no network access or credentials are needed.
"""

from datetime import date
from unittest.mock import patch

import pytest

from src.history import db, sync
from src.tools import garmin


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


@patch("src.tools.garmin.get_sleep_range")
def test_sync_sleep_extracts_score_deep_rem_rhr_hrv(mock_sleep_range):
    mock_sleep_range.return_value = [
        {
            "calendarDate": "2026-08-11",
            "values": {
                "totalSleepTimeInSeconds": 22680,
                "deepTime": 3600,
                "remTime": 2400,
                "sleepScore": 76,
                "restingHeartRate": 47,
                "avgOvernightHrv": 80.0,
            },
        }
    ]

    with db.connect() as conn:
        sync._sync_sleep(conn, "2026-08-11", "2026-08-11")

    row = db.get_range("2026-08-11", "2026-08-11")[0]
    assert row["sleep_hours"] == 6.3
    assert row["deep_sleep_hours"] == 1.0
    assert row["rem_sleep_hours"] == pytest.approx(0.67, abs=0.01)
    assert row["sleep_score"] == 76
    assert row["resting_heart_rate"] == 47
    assert row["hrv_overnight_avg"] == 80.0


@patch("src.tools.garmin.get_activities_range")
def test_sync_activities_sums_per_day(mock_activities):
    mock_activities.return_value = [
        {"startTimeLocal": "2026-08-11 17:13:14", "distance": 0.0, "duration": 3694.47},  # strength
        {"startTimeLocal": "2026-08-11 05:37:13", "distance": 16103.1, "duration": 4374.45},  # run
        {"startTimeLocal": "2026-08-10 06:25:10", "distance": 9670.1, "duration": 2831.67},
    ]

    with db.connect() as conn:
        sync._sync_activities(conn, "2026-08-10", "2026-08-11")

    rows = {r["date"]: r for r in db.get_range("2026-08-10", "2026-08-11")}
    assert rows["2026-08-11"]["miles"] == pytest.approx(10.01, abs=0.01)
    assert rows["2026-08-11"]["workout_hours"] == pytest.approx(2.24, abs=0.01)
    assert rows["2026-08-10"]["miles"] == pytest.approx(6.01, abs=0.01)


@patch("src.tools.garmin.get_vo2max_range")
def test_sync_vo2max_skips_days_without_a_reading(mock_vo2):
    mock_vo2.return_value = [
        {"generic": {"calendarDate": "2026-06-13", "vo2MaxValue": 54.0}},
        {"generic": {"calendarDate": "2026-06-14", "vo2MaxValue": None}},
    ]

    with db.connect() as conn:
        sync._sync_vo2max(conn, "2026-06-13", "2026-06-14")

    rows = db.get_range("2026-06-13", "2026-06-14")
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-06-13"


@patch("src.tools.garmin.get_morning_recovery")
def test_sync_recovery_continues_past_a_failing_day(mock_recovery):
    mock_recovery.side_effect = [
        {"score": 43, "level": "LOW"},
        garmin.GarminConnectConnectionError("boom"),
        {"score": 73, "level": "MODERATE"},
    ]

    with db.connect() as conn:
        sync._sync_recovery(conn, date(2026, 8, 10), date(2026, 8, 12), delay=0)

    rows = {r["date"]: r for r in db.get_range("2026-08-10", "2026-08-12")}
    assert rows["2026-08-10"]["recovery_score"] == 43
    assert "2026-08-11" not in rows  # the failing day is skipped, not zeroed
    assert rows["2026-08-12"]["recovery_score"] == 73
