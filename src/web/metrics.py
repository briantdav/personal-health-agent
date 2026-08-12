"""Shapes raw Garmin data into the view model for the daily dashboard.

Keeps presentation logic (unit conversion, picking which fields the dashboard
cares about, status bucketing) separate from src/tools/garmin.py, which just
wraps the raw Garmin Connect API.
"""

from __future__ import annotations

from datetime import date
from typing import Any

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


def _miles_and_workout_hours(activities: list[dict[str, Any]]) -> tuple[float, float]:
    total_meters = sum(a.get("distance") or 0 for a in activities)
    total_seconds = sum(a.get("duration") or 0 for a in activities)
    return total_meters / METERS_PER_MILE, total_seconds / 3600


def _sleep_hours(sleep_data: dict[str, Any]) -> float | None:
    seconds = (sleep_data.get("dailySleepDTO") or {}).get("sleepTimeSeconds")
    return round(seconds / 3600, 1) if seconds is not None else None


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


def get_todays_training_plan(day: date | str | None = None) -> dict[str, Any]:
    """Placeholder until src/agent.py can generate a real recommendation.

    Wire this up to real logic (rule-based or LLM, using this same day's
    recovery/sleep data plus the morning journal) once that exists.
    """
    return {
        "summary": "Training plan generation isn't wired up yet.",
        "details": None,
    }


def get_dashboard_metrics(day: date | str | None = None) -> dict[str, Any]:
    """Aggregate the metrics shown on the daily dashboard for one day.

    Best-effort like garmin.get_daily_health_snapshot: a failing endpoint
    yields a missing/None value for that metric instead of taking the whole
    dashboard down.
    """
    day_iso = garmin.to_iso_date(day)

    try:
        activities = garmin.get_activities_for_date(day_iso)
    except GARMIN_ERRORS:
        activities = []
    miles, workout_hours = _miles_and_workout_hours(activities)

    try:
        sleep_data = garmin.get_sleep(day_iso)
    except GARMIN_ERRORS:
        sleep_data = {}
    sleep_hours = _sleep_hours(sleep_data)

    recovery = _recovery(day_iso)

    return {
        "date": day_iso,
        "miles": round(miles, 2),
        "sleep_hours": sleep_hours,
        "workout_hours": round(workout_hours, 2),
        "recovery_score": recovery["score"],
        "recovery_level": recovery["level"],
        "recovery_status": recovery["status"],
        "training_plan": get_todays_training_plan(day_iso),
    }
