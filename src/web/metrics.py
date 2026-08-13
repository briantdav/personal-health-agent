"""Shapes raw Garmin data into the view model for the daily dashboard.

Keeps presentation logic (unit conversion, picking which fields the dashboard
cares about, status bucketing, trend-vs-history comparisons) separate from
src/tools/garmin.py, which just wraps the raw Garmin Connect API.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean
from typing import Any

from src.history import db as history_db
from src.tools import garmin
from src.tools.garmin import GARMIN_ERRORS

METERS_PER_MILE = 1609.344

# Simple heuristic bucketing for the recovery status badge — Garmin doesn't
# publish its own band thresholds, so these are a reasonable first pass.
# Tune (or replace with Garmin's own "level" string) once real data comes in.
_RECOVERY_BANDS = (
    (75, "good"),
    (50, "warning"),
    (25, "serious"),
)


def _recovery_status(score: int | None) -> str | None:
    if score is None:
        return None
    for threshold, status in _RECOVERY_BANDS:
        if score >= threshold:
            return status
    return "critical"


# Sleep score and body battery are both already 0-100 Garmin scales, and
# share this same band scheme for the dashboard's progress rings.
_RING_BANDS = (
    (90, "good", "Excellent"),
    (75, "warning", "Good"),
    (60, "serious", "Fair"),
)


def _ring_band(value: int | None) -> dict[str, Any]:
    """status: one of this project's four status tokens, for ring color.
    label: the user-facing tier name shown next to the ring (distinct from
    "status" because "good" is both a status-token name *and* one of the
    tier labels — Sleep score 75-89 is "Good" but colored status-warning,
    not status-good, which is reserved for 90+ "Excellent")."""
    if value is None:
        return {"status": "unknown", "label": None}
    for threshold, status, label in _RING_BANDS:
        if value >= threshold:
            return {"status": status, "label": label}
    return {"status": "critical", "label": "Poor"}


def _running_miles(activities: list[dict[str, Any]]) -> float:
    """Only Garmin's running family counts as mileage — golf, walks, rides
    etc. have a GPS distance too, but they aren't running miles."""
    meters = sum(a.get("distance") or 0 for a in activities if garmin.is_running_activity(a))
    return meters / METERS_PER_MILE


def _workout_hours(activities: list[dict[str, Any]]) -> float:
    """Every activity type counts here — this is "time spent training",
    not "time spent running"."""
    seconds = sum(a.get("duration") or 0 for a in activities)
    return seconds / 3600


def _sleep_hours(sleep_data: dict[str, Any]) -> float | None:
    seconds = (sleep_data.get("dailySleepDTO") or {}).get("sleepTimeSeconds")
    return round(seconds / 3600, 1) if seconds is not None else None


def _sleep_score(sleep_data: dict[str, Any]) -> int | None:
    scores = (sleep_data.get("dailySleepDTO") or {}).get("sleepScores") or {}
    return (scores.get("overall") or {}).get("value")


def _rem_and_deep_sleep_hours(sleep_data: dict[str, Any]) -> tuple[float | None, float | None]:
    dto = sleep_data.get("dailySleepDTO") or {}
    rem_seconds = dto.get("remSleepSeconds")
    deep_seconds = dto.get("deepSleepSeconds")
    rem_hours = round(rem_seconds / 3600, 1) if rem_seconds is not None else None
    deep_hours = round(deep_seconds / 3600, 1) if deep_seconds is not None else None
    return rem_hours, deep_hours


def _hrv_value(hrv_data: dict[str, Any] | None) -> int | None:
    return ((hrv_data or {}).get("hrvSummary") or {}).get("lastNightAvg")


def _body_battery_value(summary_data: dict[str, Any]) -> int | None:
    """Peak body battery for the day — same "peak" definition src/history/
    sync.py stores, so the live dashboard ring and future trend history
    mean the same thing."""
    return (summary_data or {}).get("bodyBatteryHighestValue")


def _recovery(day_iso: str) -> dict[str, Any]:
    try:
        readiness = garmin.get_morning_recovery(day_iso)
    except GARMIN_ERRORS:
        readiness = None
    score = (readiness or {}).get("score")
    return {
        "score": score,
        "level": (readiness or {}).get("level"),
        "status": _recovery_status(score),
    }


def _window_rows(end_day: str, days: int) -> list[dict[str, Any]]:
    start = (date.fromisoformat(end_day) - timedelta(days=days - 1)).isoformat()
    return history_db.get_range(start, end_day)


def _window_average(end_day: str, days: int, field: str, decimals: int = 1) -> float | int | None:
    values = [r[field] for r in _window_rows(end_day, days) if r.get(field) is not None]
    if not values:
        return None
    avg = fmean(values)
    return round(avg) if decimals == 0 else round(avg, decimals)


def _window_total(end_day: str, days: int, field: str, decimals: int = 2) -> float:
    values = [r[field] for r in _window_rows(end_day, days) if r.get(field) is not None]
    return round(sum(values), decimals) if values else 0.0


def _trend(value: float | int | None, avg: float | int | None) -> str | None:
    """"Compared to the trailing average" — up/down/flat, or None if either
    side is missing. Deliberately not a status color: a single day being
    below a rolling average isn't a health alarm, just a comparison."""
    if value is None or avg is None:
        return None
    if value > avg:
        return "up"
    if value < avg:
        return "down"
    return "flat"


def _trend_info(value: float | int | None, end_day: str, field: str, decimals: int = 1) -> dict[str, Any]:
    """7d/30d trailing averages (ending the day before "today", so today's
    own not-yet-synced value can't skew its own comparison) plus an
    up/down/flat read of today vs. each — reused by sleep hours, sleep
    score, recovery score, and HRV, which all want the same treatment."""
    avg_7d = _window_average(end_day, 7, field, decimals)
    avg_30d = _window_average(end_day, 30, field, decimals)
    return {
        "avg_7d": avg_7d,
        "avg_30d": avg_30d,
        "trend_7d": _trend(value, avg_7d),
        "trend_30d": _trend(value, avg_30d),
    }


def _totals_info(end_day: str, field: str, decimals: int = 2) -> dict[str, Any]:
    """7d/30d trailing totals — for volume metrics (miles, workout hours)
    where a sum ("32 miles this week") is what matters, not an average."""
    return {
        "total_7d": _window_total(end_day, 7, field, decimals),
        "total_30d": _window_total(end_day, 30, field, decimals),
    }


def _scheduled_run(day_iso: str) -> dict[str, Any] | None:
    """Today's scheduled run from the Garmin calendar — itself fed by the
    coach's TrainingPeaks plan once TrainingPeaks has synced it down to
    Garmin — or None if nothing's there (a real rest day, the sync
    hasn't caught up yet, or the endpoint errored). Only itemType
    "workout" with sportTypeKey "running" counts; races, other sports,
    and non-workout calendar items (badges, events, ...) don't."""
    year, month = int(day_iso[:4]), int(day_iso[5:7])
    try:
        items = garmin.get_scheduled_workouts_for_month(year, month)
    except GARMIN_ERRORS:
        return None
    for item in items:
        if item.get("date") == day_iso and item.get("itemType") == "workout" and item.get("sportTypeKey") == "running":
            return item
    return None


def get_todays_training_plan(day: date | str | None = None) -> dict[str, Any]:
    """Today's run, pulled from the Garmin calendar — "Rest Day" if
    nothing's scheduled there. Run workouts only, for now: strength and
    everything else will come from a different source once that's built,
    and until then this card only speaks to running.
    """
    day_iso = garmin.to_iso_date(day)
    run = _scheduled_run(day_iso)
    if run is None:
        return {"summary": "Rest Day", "details": None}
    return {"summary": run.get("title") or "Scheduled run", "details": None}


def get_dashboard_metrics(day: date | str | None = None) -> dict[str, Any]:
    """Aggregate the metrics shown on the daily dashboard for one day.

    Sleep/recovery/HRV are keyed to `day` (Garmin already attributes
    overnight sleep and the morning readiness reading to the wake-up
    date). Miles/workout time are keyed to the day *before* — this is a
    summary of yesterday's training, not a live count of an in-progress
    day — and every 7d/30d window (both the totals and the trend
    averages) is anchored there too, so nothing on the page mixes a
    partial "today" into a trailing window.

    Best-effort like garmin.get_daily_health_snapshot: a failing endpoint
    yields a missing/None value for that metric instead of taking the
    whole dashboard down.
    """
    day_iso = garmin.to_iso_date(day)
    yesterday_iso = (date.fromisoformat(day_iso) - timedelta(days=1)).isoformat()

    try:
        activities = garmin.get_activities_for_date(yesterday_iso)
    except GARMIN_ERRORS:
        activities = []
    miles = round(_running_miles(activities), 2)
    workout_hours = round(_workout_hours(activities), 2)

    try:
        sleep_data = garmin.get_sleep(day_iso)
    except GARMIN_ERRORS:
        sleep_data = {}
    sleep_hours = _sleep_hours(sleep_data)
    sleep_score = _sleep_score(sleep_data)
    rem_sleep_hours, deep_sleep_hours = _rem_and_deep_sleep_hours(sleep_data)

    try:
        hrv_data = garmin.get_hrv(day_iso)
    except GARMIN_ERRORS:
        hrv_data = None
    hrv = _hrv_value(hrv_data)

    try:
        summary_data = garmin.get_daily_summary(day_iso)
    except GARMIN_ERRORS:
        summary_data = {}
    body_battery = _body_battery_value(summary_data)

    recovery = _recovery(day_iso)

    return {
        "date": day_iso,
        "activity_date": yesterday_iso,
        "miles": miles,
        "miles_totals": _totals_info(yesterday_iso, "miles"),
        "workout_hours": workout_hours,
        "workout_hours_totals": _totals_info(yesterday_iso, "workout_hours"),
        "sleep_hours": sleep_hours,
        "sleep_hours_trend": _trend_info(sleep_hours, yesterday_iso, "sleep_hours", decimals=1),
        "sleep_score": sleep_score,
        "sleep_score_band": _ring_band(sleep_score),
        "sleep_score_trend": _trend_info(sleep_score, yesterday_iso, "sleep_score", decimals=0),
        "rem_sleep_hours": rem_sleep_hours,
        "deep_sleep_hours": deep_sleep_hours,
        "recovery_score": recovery["score"],
        "recovery_level": recovery["level"],
        "recovery_status": recovery["status"],
        "recovery_score_trend": _trend_info(recovery["score"], yesterday_iso, "recovery_score", decimals=0),
        "body_battery": body_battery,
        "body_battery_band": _ring_band(body_battery),
        "hrv": hrv,
        "hrv_trend": _trend_info(hrv, yesterday_iso, "hrv_overnight_avg", decimals=0),
        "training_plan": get_todays_training_plan(day_iso),
    }
