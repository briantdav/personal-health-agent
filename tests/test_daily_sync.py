"""Tests for src/history/daily_sync.py — the idempotent per-invocation check.

Time-window and "already synced" behavior is exercised directly against
the pure helper functions rather than by freezing the clock, so these
stay fast and don't depend on wall-clock time at test-run time.
"""

from datetime import date, datetime, time
from unittest.mock import patch

import pytest

from src.history import daily_sync, db


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))


def test_already_synced_today_false_when_no_row():
    assert daily_sync._already_synced_today() is False


def test_already_synced_today_true_once_recovery_score_present():
    with db.connect() as conn:
        db.upsert_day(conn, date.today().isoformat(), recovery_score=50)

    assert daily_sync._already_synced_today() is True


def test_already_synced_today_false_if_only_other_fields_present():
    """A partial sync (e.g. sleep synced but recovery still pending)
    shouldn't count as done — recovery is always the last field written."""
    with db.connect() as conn:
        db.upsert_day(conn, date.today().isoformat(), sleep_hours=7.0)

    assert daily_sync._already_synced_today() is False


@patch("src.tools.garmin.get_sleep")
def test_sleep_ready_true_when_sleep_time_present(mock_get_sleep):
    mock_get_sleep.return_value = {"dailySleepDTO": {"sleepTimeSeconds": 25000}}

    assert daily_sync._sleep_ready("2026-08-12") is True


@patch("src.tools.garmin.get_sleep")
def test_sleep_ready_false_when_missing(mock_get_sleep):
    mock_get_sleep.return_value = {"dailySleepDTO": {}}

    assert daily_sync._sleep_ready("2026-08-12") is False


@patch("src.tools.garmin.get_sleep")
def test_sleep_ready_false_on_garmin_error(mock_get_sleep):
    from src.tools import garmin

    mock_get_sleep.side_effect = garmin.GarminConnectConnectionError("boom")

    assert daily_sync._sleep_ready("2026-08-12") is False


def _fixed_clock(hour: int, minute: int):
    """A stand-in for the datetime class whose .now() returns a real
    datetime (today's date, given time) so _log's .isoformat() etc.
    keep working — only "now" is frozen, nothing else about datetime."""
    fixed = datetime.combine(date.today(), time(hour, minute))

    class FixedDatetime:
        @staticmethod
        def now():
            return fixed

    return FixedDatetime


@patch("src.history.daily_sync._sleep_ready", return_value=True)
@patch("src.history.daily_sync._run_catch_up_sync")
def test_check_and_sync_runs_when_ready_and_in_window(mock_run_sync, mock_ready, monkeypatch):
    monkeypatch.setattr(daily_sync, "datetime", _fixed_clock(7, 0))

    result = daily_sync.check_and_sync()

    assert result is True
    mock_run_sync.assert_called_once()


@patch("src.history.daily_sync._sleep_ready", return_value=True)
@patch("src.history.daily_sync._run_catch_up_sync")
def test_check_and_sync_noops_outside_window(mock_run_sync, mock_ready, monkeypatch):
    monkeypatch.setattr(daily_sync, "datetime", _fixed_clock(23, 0))  # 11pm — outside the morning window

    result = daily_sync.check_and_sync()

    assert result is False
    mock_run_sync.assert_not_called()


@patch("src.history.daily_sync._sleep_ready", return_value=False)
@patch("src.history.daily_sync._run_catch_up_sync")
def test_check_and_sync_noops_when_sleep_not_ready(mock_run_sync, mock_ready, monkeypatch):
    monkeypatch.setattr(daily_sync, "datetime", _fixed_clock(7, 0))

    result = daily_sync.check_and_sync()

    assert result is False
    mock_run_sync.assert_not_called()
