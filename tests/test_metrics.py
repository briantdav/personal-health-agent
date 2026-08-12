"""Tests for src/web/metrics.py — the dashboard view-model layer.

Patches src.tools.garmin functions directly so no network calls or real
credentials are needed to run the suite. get_dashboard_metrics now also
reads 7d/30d windows from the history DB, so most tests use an isolated
tmp-path DB (same pattern as tests/test_trends.py).
"""

from unittest.mock import patch

import pytest

from src.history import db as history_db
from src.tools import garmin
from src.web import metrics

RUNNING = {"typeId": 1, "typeKey": "running", "parentTypeId": 17}
GOLF = {"typeId": 88, "typeKey": "golf", "parentTypeId": 4}
STRENGTH = {"typeId": 13, "typeKey": "strength_training", "parentTypeId": 29}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


def test_running_miles_only_counts_running_activities():
    activities = [
        {"distance": 5000, "duration": 1800, "activityType": RUNNING},
        {"distance": 4772.87, "duration": 8414.91, "activityType": GOLF},
    ]
    assert round(metrics._running_miles(activities), 2) == 3.11


def test_running_miles_handles_no_activities():
    assert metrics._running_miles([]) == 0


def test_workout_hours_sums_every_activity_type():
    activities = [
        {"distance": 5000, "duration": 1800, "activityType": RUNNING},
        {"distance": 0, "duration": 1800, "activityType": STRENGTH},
    ]
    assert round(metrics._workout_hours(activities), 2) == 1.0


def test_workout_hours_handles_no_activities():
    assert metrics._workout_hours([]) == 0


def test_sleep_hours_reads_nested_dto():
    sleep_data = {"dailySleepDTO": {"sleepTimeSeconds": 27000}}
    assert metrics._sleep_hours(sleep_data) == 7.5


def test_sleep_hours_missing_is_none():
    assert metrics._sleep_hours({}) is None


def test_sleep_score_reads_nested_overall_value():
    sleep_data = {"dailySleepDTO": {"sleepScores": {"overall": {"value": 76}}}}
    assert metrics._sleep_score(sleep_data) == 76


def test_sleep_score_missing_is_none():
    assert metrics._sleep_score({}) is None


def test_hrv_value_reads_last_night_avg():
    assert metrics._hrv_value({"hrvSummary": {"lastNightAvg": 80}}) == 80


def test_hrv_value_missing_is_none():
    assert metrics._hrv_value(None) is None
    assert metrics._hrv_value({}) is None


def test_recovery_status_bands():
    assert metrics._recovery_status(90) == "good"
    assert metrics._recovery_status(60) == "warning"
    assert metrics._recovery_status(30) == "serious"
    assert metrics._recovery_status(10) == "critical"
    assert metrics._recovery_status(None) is None


def _seed(*days):
    with history_db.connect() as conn:
        for iso_date, fields in days:
            history_db.upsert_day(conn, iso_date, **fields)


def test_window_average_rounds_to_requested_decimals():
    _seed(("2026-08-10", {"sleep_score": 70}), ("2026-08-11", {"sleep_score": 76}))

    assert metrics._window_average("2026-08-11", 7, "sleep_score", decimals=0) == 73
    assert isinstance(metrics._window_average("2026-08-11", 7, "sleep_score", decimals=0), int)


def test_window_average_none_when_no_data():
    assert metrics._window_average("2026-08-11", 7, "sleep_score") is None


def test_window_total_sums_and_defaults_to_zero():
    _seed(("2026-08-10", {"miles": 6.0}), ("2026-08-11", {"miles": 10.0}))

    assert metrics._window_total("2026-08-11", 7, "miles") == 16.0
    assert metrics._window_total("2026-08-11", 7, "workout_hours") == 0.0


@pytest.mark.parametrize(
    "value,avg,expected",
    [(80, 75, "up"), (70, 75, "down"), (75, 75, "flat"), (None, 75, None), (80, None, None)],
)
def test_trend(value, avg, expected):
    assert metrics._trend(value, avg) == expected


@patch("src.tools.garmin.get_morning_recovery")
@patch("src.tools.garmin.get_hrv")
@patch("src.tools.garmin.get_sleep")
@patch("src.tools.garmin.get_activities_for_date")
def test_get_dashboard_metrics_pulls_activities_for_the_day_before(
    mock_activities, mock_sleep, mock_hrv, mock_recovery
):
    mock_activities.return_value = []
    mock_sleep.return_value = {}
    mock_hrv.return_value = None
    mock_recovery.return_value = None

    metrics.get_dashboard_metrics("2026-08-12")

    mock_activities.assert_called_once_with("2026-08-11")
    # Sleep/HRV/recovery stay keyed to the passed-in day (Garmin already
    # attributes the overnight reading to the wake-up date).
    mock_sleep.assert_called_once_with("2026-08-12")
    mock_hrv.assert_called_once_with("2026-08-12")
    mock_recovery.assert_called_once_with("2026-08-12")


@patch("src.tools.garmin.get_morning_recovery")
@patch("src.tools.garmin.get_hrv")
@patch("src.tools.garmin.get_sleep")
@patch("src.tools.garmin.get_activities_for_date")
def test_get_dashboard_metrics_aggregates_everything(
    mock_activities, mock_sleep, mock_hrv, mock_recovery
):
    mock_activities.return_value = [{"distance": 1609.344, "duration": 600, "activityType": RUNNING}]
    mock_sleep.return_value = {
        "dailySleepDTO": {"sleepTimeSeconds": 25200, "sleepScores": {"overall": {"value": 76}}}
    }
    mock_hrv.return_value = {"hrvSummary": {"lastNightAvg": 80}}
    mock_recovery.return_value = {"score": 82, "level": "HIGH"}

    # 2026-07-20 is within the 30d window ending 2026-08-11 (starts 07-13)
    # but outside the 7d window (starts 08-05) — exercises both at once.
    _seed(("2026-07-20", {"sleep_score": 70, "miles": 3.0}))

    result = metrics.get_dashboard_metrics("2026-08-12")

    assert result["date"] == "2026-08-12"
    assert result["activity_date"] == "2026-08-11"
    assert result["miles"] == 1.0
    assert result["miles_totals"] == {"total_7d": 0.0, "total_30d": 3.0}
    assert result["sleep_hours"] == 7.0
    assert result["sleep_score"] == 76
    assert result["sleep_score_trend"]["avg_30d"] == 70
    assert result["sleep_score_trend"]["trend_30d"] == "up"
    assert result["hrv"] == 80
    assert result["recovery_score"] == 82
    assert result["recovery_level"] == "HIGH"
    assert result["recovery_status"] == "good"
    assert "training_plan" in result


@patch("src.tools.garmin.get_morning_recovery")
@patch("src.tools.garmin.get_hrv")
@patch("src.tools.garmin.get_sleep")
@patch("src.tools.garmin.get_activities_for_date")
def test_get_dashboard_metrics_degrades_on_endpoint_errors(
    mock_activities, mock_sleep, mock_hrv, mock_recovery
):
    mock_activities.side_effect = garmin.GarminConnectConnectionError("boom")
    mock_sleep.side_effect = garmin.GarminConnectConnectionError("boom")
    mock_hrv.side_effect = garmin.GarminConnectConnectionError("boom")
    mock_recovery.side_effect = garmin.GarminConnectConnectionError("boom")

    result = metrics.get_dashboard_metrics("2026-08-12")

    assert result["miles"] == 0
    assert result["sleep_hours"] is None
    assert result["sleep_score"] is None
    assert result["hrv"] is None
    assert result["recovery_score"] is None
    assert result["recovery_status"] is None
