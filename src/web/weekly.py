"""Weekly review view model — the Monday read of the week just closed.

Mirrors src/web/metrics.py's split of responsibilities: this module shapes
what the /review page and the dashboard's Monday sheet display, reading the
local caches (src/history/db.py for Garmin metrics, src/journal/db.py for
habits) rather than hitting Garmin. Everything is best-effort: a missing
column yields None, not a failure.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import fmean
from typing import Any

from src.history import db as history_db
from src.journal import db as journal_db
from src.web import journal as journal_cfg

DAY_LETTERS = ["M", "T", "W", "T", "F", "S", "S"]

# Habits worth showing in the grid, in display order. "flag" marks the ones
# a "yes" is bad for — they paint red rather than ink.
GRID_HABITS: list[tuple[str, str, bool]] = [
    ("took_creatine", "Creatine", False),
    ("hit_protein_goal", "Protein goal", False),
    ("read_before_bed", "Read before bed", False),
    ("stretched_before_bed", "Stretching", False),
    ("used_phone_in_bed", "Phone in bed", True),
    ("drank_alcohol", "Alcohol", True),
]


def week_bounds(day: date | None = None) -> tuple[date, date]:
    """The Monday-to-Sunday week that just closed, relative to `day`."""
    today = day or date.today()
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    return last_monday, last_monday + timedelta(days=6)


def _avg(rows: list[dict[str, Any]], field: str, decimals: int = 1) -> float | int | None:
    values = [r[field] for r in rows if r.get(field) is not None]
    if not values:
        return None
    avg = fmean(values)
    return round(avg) if decimals == 0 else round(avg, decimals)


def _total(rows: list[dict[str, Any]], field: str) -> float:
    return round(sum(r[field] for r in rows if r.get(field) is not None), 1)


def _label(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def get_weekly_review(day: date | None = None, miles_planned: float | None = None) -> dict[str, Any]:
    start, end = week_bounds(day)
    prev_start, prev_end = start - timedelta(days=7), start - timedelta(days=1)

    rows = history_db.get_range(start.isoformat(), end.isoformat())
    prev_rows = history_db.get_range(prev_start.isoformat(), prev_end.isoformat())

    miles = _total(rows, "miles")
    recovery = _avg(rows, "recovery_score", decimals=0)
    recovery_prev = _avg(prev_rows, "recovery_score", decimals=0)

    entries = {}
    for offset in range(7):
        d = (start + timedelta(days=offset)).isoformat()
        entries[d] = journal_db.get_entry(d) or {}

    habits = []
    answered = filled = 0
    for key, label, flag in GRID_HABITS:
        days = []
        for offset in range(7):
            d = (start + timedelta(days=offset)).isoformat()
            value = entries[d].get(key)
            days.append(bool(value))
            if value is not None:
                answered += 1
                if bool(value) is not flag:
                    filled += 1
        habits.append({"key": key, "label": label, "days": days, "flag": flag})

    sessions = []
    for offset in range(7):
        d = start + timedelta(days=offset)
        row = next((r for r in rows if r.get("date") == d.isoformat()), {})
        sessions.append({
            "day": d.strftime("%a"),
            "title": row.get("workout_title") or ("Run" if row.get("miles") else "Rest"),
            "miles": row.get("miles"),
            "pace": row.get("avg_pace"),
        })

    return {
        "week_label": _label(start),
        "next_week_label": _label(end + timedelta(days=1)),
        "closed": True,
        "headline": _headline(recovery, recovery_prev, miles),
        "miles": miles,
        "miles_planned": miles_planned if miles_planned is not None else "—",
        "miles_prev": _total(prev_rows, "miles"),
        "recovery": recovery,
        "recovery_prev": recovery_prev,
        "sleep": _avg(rows, "sleep_hours"),
        "sleep_prev": _avg(prev_rows, "sleep_hours"),
        "habit_pct": round(filled / answered * 100) if answered else 0,
        "habits": habits,
        "day_letters": DAY_LETTERS,
        "sessions": sessions,
        "note": None,  # filled by src/agent.py once the LLM read exists
        "next_week_summary": "Plan not synced yet",
    }


def _headline(recovery: int | None, recovery_prev: int | None, miles: float) -> str:
    if recovery is None:
        return f"{miles} miles logged"
    if recovery_prev is not None and recovery > recovery_prev:
        return "Recovery up on more volume"
    if recovery_prev is not None and recovery < recovery_prev:
        return "Volume held, recovery slipped"
    return f"{miles} miles, recovery steady"


def is_review_day(day: date | None = None) -> bool:
    """The dashboard shows the review sheet on Mondays only."""
    return (day or date.today()).weekday() == 0
