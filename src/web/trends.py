"""Daily/weekly/monthly trend series for the /trends dashboard page.

Reads from the local history DB (src/history/db.py) — never hits Garmin
live, so this stays fast no matter how much history is cached. Run
`python -m src.history.sync` first to populate it.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import fmean
from typing import Any

from src.history import db

# key -> display label, in the order charts should appear.
METRICS: dict[str, str] = {
    "miles": "Miles",
    "workout_hours": "Workout time (hrs)",
    "sleep_hours": "Sleep (hrs)",
    "deep_sleep_hours": "Deep sleep (hrs)",
    "rem_sleep_hours": "REM sleep (hrs)",
    "sleep_score": "Sleep score",
    "resting_heart_rate": "Resting heart rate",
    "hrv_overnight_avg": "HRV (overnight avg)",
    "body_battery_peak": "Body battery (peak)",
    "vo2_max": "VO2 max",
    "recovery_score": "Recovery score",
}

# Volume metrics roll up as a total ("10.2 miles this week"); everything
# else is a rate/score, which rolls up as an average. Mislabeling weekly
# mileage as a per-day average would be actively misleading for a runner.
SUM_METRICS = {"miles", "workout_hours"}


def _forward_fill(series: list[dict[str, Any]], field: str) -> None:
    """VO2 max only gets a new reading every so often — carry the last
    known value forward so the chart doesn't show false dips to zero."""
    last = None
    for row in series:
        if row[field] is None:
            row[field] = last
        else:
            last = row[field]


def get_daily_series(days: int = 365) -> list[dict[str, Any]]:
    """One row per calendar day in range, gaps filled with None."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    by_date = {row["date"]: row for row in db.get_range(start.isoformat(), end.isoformat())}

    series = []
    d = start
    while d <= end:
        iso = d.isoformat()
        row = by_date.get(iso, {})
        series.append({"date": iso, **{key: row.get(key) for key in METRICS}})
        d += timedelta(days=1)

    _forward_fill(series, "vo2_max")
    return series


def _week_key(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _month_key(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _aggregate(series: list[dict[str, Any]], key_fn) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in series:
        key = key_fn(date.fromisoformat(row["date"]))
        for metric in METRICS:
            value = row.get(metric)
            if value is not None:
                buckets[key][metric].append(value)

    result = []
    for key in sorted(buckets):
        entry: dict[str, Any] = {"period": key}
        for metric in METRICS:
            values = buckets[key][metric]
            if not values:
                entry[metric] = None
            elif metric in SUM_METRICS:
                entry[metric] = round(sum(values), 2)
            else:
                entry[metric] = round(fmean(values), 2)
        result.append(entry)
    return result


def get_weekly_series(days: int = 365) -> list[dict[str, Any]]:
    return _aggregate(get_daily_series(days), _week_key)


def get_monthly_series(days: int = 365) -> list[dict[str, Any]]:
    return _aggregate(get_daily_series(days), _month_key)


def get_trends(days: int = 365) -> dict[str, Any]:
    daily = get_daily_series(days)
    return {
        "metrics": METRICS,
        "sum_metrics": sorted(SUM_METRICS),
        "has_data": any(row.get(m) is not None for row in daily for m in METRICS),
        "daily": daily,
        "weekly": get_weekly_series(days),
        "monthly": get_monthly_series(days),
    }
