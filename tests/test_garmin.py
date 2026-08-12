"""Tests for the Garmin Connect tool wrapper (src/tools/garmin.py).

All tests patch get_client so no network calls or real credentials are
needed to run the suite.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from src.tools import garmin


@patch("src.tools.garmin.get_client")
def test_get_daily_summary_passes_explicit_date(mock_get_client):
    mock_client = MagicMock()
    mock_client.get_user_summary.return_value = {"totalSteps": 1234}
    mock_get_client.return_value = mock_client

    result = garmin.get_daily_summary("2026-08-12")

    mock_client.get_user_summary.assert_called_once_with("2026-08-12")
    assert result == {"totalSteps": 1234}


@patch("src.tools.garmin.get_client")
def test_get_daily_summary_defaults_to_today(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    garmin.get_daily_summary()

    mock_client.get_user_summary.assert_called_once_with(date.today().isoformat())


@patch("src.tools.garmin.get_client")
def test_get_body_battery_uses_same_start_and_end_date(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    garmin.get_body_battery("2026-08-12")

    mock_client.get_body_battery.assert_called_once_with("2026-08-12", "2026-08-12")


@patch("src.tools.garmin.get_client")
def test_get_body_battery_range_chunks_long_ranges(mock_get_client):
    """Garmin's endpoint 400s on long ranges ("date range is too big") —
    unlike get_sleep_daily/get_rhr_daily, get_body_battery doesn't chunk
    itself, so this wrapper has to."""
    mock_client = MagicMock()
    mock_client.get_body_battery.side_effect = lambda start, end: [{"date": start}]
    mock_get_client.return_value = mock_client

    result = garmin.get_body_battery_range("2026-01-01", "2026-03-01")  # 60 days

    calls = mock_client.get_body_battery.call_args_list
    assert len(calls) == 3  # 28 + 28 + 4 days
    assert calls[0].args == ("2026-01-01", "2026-01-28")
    assert calls[1].args == ("2026-01-29", "2026-02-25")
    assert calls[2].args == ("2026-02-26", "2026-03-01")
    assert result == [{"date": "2026-01-01"}, {"date": "2026-01-29"}, {"date": "2026-02-26"}]


@patch("src.tools.garmin.get_client")
def test_get_body_battery_range_single_chunk_for_short_range(mock_get_client):
    mock_client = MagicMock()
    mock_client.get_body_battery.return_value = [{"date": "2026-08-12"}]
    mock_get_client.return_value = mock_client

    garmin.get_body_battery_range("2026-08-01", "2026-08-12")

    mock_client.get_body_battery.assert_called_once_with("2026-08-01", "2026-08-12")


@pytest.mark.parametrize(
    "activity_type,expected",
    [
        ({"typeId": 1, "typeKey": "running", "parentTypeId": 17}, True),
        ({"typeId": 18, "typeKey": "treadmill_running", "parentTypeId": 1}, True),
        ({"typeId": 88, "typeKey": "golf", "parentTypeId": 4}, False),
        ({"typeId": 13, "typeKey": "strength_training", "parentTypeId": 29}, False),
        ({}, False),
    ],
)
def test_is_running_activity(activity_type, expected):
    assert garmin.is_running_activity({"activityType": activity_type}) is expected


def test_is_running_activity_missing_activity_type():
    assert garmin.is_running_activity({}) is False


@patch("src.tools.garmin.get_client")
def test_snapshot_aggregates_all_metrics(mock_get_client):
    mock_client = MagicMock()
    mock_client.get_user_summary.return_value = {"totalSteps": 1234}
    mock_client.get_sleep_data.return_value = {"sleepTimeSeconds": 25200}
    mock_get_client.return_value = mock_client

    snapshot = garmin.get_daily_health_snapshot("2026-08-12")

    assert snapshot["date"] == "2026-08-12"
    assert snapshot["summary"] == {"totalSteps": 1234}
    assert snapshot["sleep"] == {"sleepTimeSeconds": 25200}


@patch("src.tools.garmin.get_client")
def test_snapshot_records_endpoint_errors_without_raising(mock_get_client):
    mock_client = MagicMock()
    mock_client.get_user_summary.side_effect = garmin.GarminConnectConnectionError("boom")
    mock_get_client.return_value = mock_client

    snapshot = garmin.get_daily_health_snapshot("2026-08-12")

    assert snapshot["summary"] == {"error": "boom"}
