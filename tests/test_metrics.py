"""Tests for src/web/metrics.py — the dashboard view-model layer.

Patches src.tools.garmin functions directly so no network calls or real
credentials are needed to run the suite.
"""

from unittest.mock import patch

from src.tools import garmin
from src.web import metrics


def test_miles_and_workout_hours_sum_across_activities():
    activities = [
        {"distance": 5000, "duration": 1800},  # 5km in 30 min
        {"distance": 3218.688, "duration": 1200},  # 2mi in 20 min
    ]
    miles, hours = metrics._miles_and_workout_hours(activities)

    assert round(miles, 2) == 5.11
    assert round(hours, 2) == 0.83


def test_miles_and_workout_hours_handles_no_activities():
    miles, hours = metrics._miles_and_workout_hours([])
    assert miles == 0
    assert hours == 0


def test_sleep_hours_reads_nested_dto():
    sleep_data = {"dailySleepDTO": {"sleepTimeSeconds": 27000}}
    assert metrics._sleep_hours(sleep_data) == 7.5


def test_sleep_hours_missing_is_none():
    assert metrics._sleep_hours({}) is None


def test_recovery_status_bands():
    assert metrics._recovery_status(90) == "good"
    assert metrics._recovery_status(60) == "warning"
    assert metrics._recovery_status(30) == "serious"
    assert metrics._recovery_status(10) == "critical"
    assert metrics._recovery_status(None) is None


@patch("src.tools.garmin.get_morning_recovery")
@patch("src.tools.garmin.get_sleep")
@patch("src.tools.garmin.get_activities_for_date")
def test_get_dashboard_metrics_aggregates_everything(
    mock_activities, mock_sleep, mock_recovery
):
    mock_activities.return_value = [{"distance": 1609.344, "duration": 600}]
    mock_sleep.return_value = {"dailySleepDTO": {"sleepTimeSeconds": 25200}}
    mock_recovery.return_value = {"score": 82, "level": "HIGH"}

    result = metrics.get_dashboard_metrics("2026-08-12")

    assert result["date"] == "2026-08-12"
    assert result["miles"] == 1.0
    assert result["sleep_hours"] == 7.0
    assert result["recovery_score"] == 82
    assert result["recovery_level"] == "HIGH"
    assert result["recovery_status"] == "good"
    assert "training_plan" in result


@patch("src.tools.garmin.get_morning_recovery")
@patch("src.tools.garmin.get_sleep")
@patch("src.tools.garmin.get_activities_for_date")
def test_get_dashboard_metrics_degrades_on_endpoint_errors(
    mock_activities, mock_sleep, mock_recovery
):
    mock_activities.side_effect = garmin.GarminConnectConnectionError("boom")
    mock_sleep.side_effect = garmin.GarminConnectConnectionError("boom")
    mock_recovery.side_effect = garmin.GarminConnectConnectionError("boom")

    result = metrics.get_dashboard_metrics("2026-08-12")

    assert result["miles"] == 0
    assert result["sleep_hours"] is None
    assert result["recovery_score"] is None
    assert result["recovery_status"] is None
