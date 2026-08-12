"""Garmin Connect data tool.

Garmin's official Connect Developer Health API requires applying as a legal
entity (company/university) — there's no self-serve path for an individual to
read their own data. So this wraps the unofficial `garminconnect` library
(https://github.com/cyberjunky/python-garminconnect), which logs in as your
own Garmin Connect account (the same way the mobile app does) and caches
OAuth tokens to disk so you only hit login/MFA once.

Env vars (see .env.example):
    GARMIN_EMAIL     - Garmin Connect account email (prompted if unset)
    GARMIN_PASSWORD  - Garmin Connect account password (prompted if unset)
    GARMINTOKENS     - token cache path (default ~/.garminconnect)
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from getpass import getpass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

load_dotenv()

# Errors that mean "this endpoint didn't come back" rather than a bug — safe
# to catch broadly and degrade gracefully (used by get_daily_health_snapshot
# and by src/web/metrics.py).
GARMIN_ERRORS = (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

_client: Garmin | None = None


def _tokenstore_path() -> str:
    return str(Path(os.getenv("GARMINTOKENS", "~/.garminconnect")).expanduser())


def get_client(force_relogin: bool = False) -> Garmin:
    """Return an authenticated Garmin client, reusing cached tokens when possible.

    A client is cached at module level for the life of the process. Pass
    force_relogin=True to bypass that cache and re-authenticate (e.g. after
    the cached tokens were rejected).
    """
    global _client
    if _client is not None and not force_relogin:
        return _client

    tokenstore = _tokenstore_path()

    try:
        client = Garmin()
        client.login(tokenstore)
        _client = client
        return client
    except (GarminConnectAuthenticationError, GarminConnectConnectionError, FileNotFoundError):
        pass  # no valid cached tokens — fall through to a fresh credential login

    email = os.getenv("GARMIN_EMAIL") or input("Garmin email: ").strip()
    password = os.getenv("GARMIN_PASSWORD") or getpass("Garmin password: ")
    client = Garmin(
        email=email,
        password=password,
        prompt_mfa=lambda: input("MFA code: ").strip(),
    )
    client.login(tokenstore)
    _client = client
    return client


def to_iso_date(day: date | str | None) -> str:
    """Normalize a date/str/None into the 'YYYY-MM-DD' string the API expects."""
    if day is None:
        return date.today().isoformat()
    return day.isoformat() if isinstance(day, date) else day


def get_daily_summary(day: date | str | None = None) -> dict[str, Any]:
    """Steps, calories, distance, resting HR etc. for one day."""
    return get_client().get_user_summary(to_iso_date(day))


def get_sleep(day: date | str | None = None) -> dict[str, Any]:
    return get_client().get_sleep_data(to_iso_date(day))


def get_heart_rate(day: date | str | None = None) -> dict[str, Any]:
    return get_client().get_heart_rates(to_iso_date(day))


def get_hrv(day: date | str | None = None) -> dict[str, Any] | None:
    return get_client().get_hrv_data(to_iso_date(day))


def get_stress(day: date | str | None = None) -> dict[str, Any]:
    return get_client().get_stress_data(to_iso_date(day))


def get_body_battery(day: date | str | None = None) -> list[dict[str, Any]]:
    cdate = to_iso_date(day)
    return get_client().get_body_battery(cdate, cdate)


def get_training_readiness(day: date | str | None = None) -> list[dict[str, Any]]:
    return get_client().get_training_readiness(to_iso_date(day))


def get_morning_recovery(day: date | str | None = None) -> dict[str, Any] | None:
    """The Training Readiness reading taken right after waking (Morning Report)."""
    return get_client().get_morning_training_readiness(to_iso_date(day))


def get_training_status(day: date | str | None = None) -> dict[str, Any]:
    return get_client().get_training_status(to_iso_date(day))


def get_recent_activities(limit: int = 10) -> list[dict[str, Any]] | dict[str, Any]:
    return get_client().get_activities(0, limit)


def get_activities_for_date(day: date | str | None = None) -> list[dict[str, Any]]:
    """All activities logged on a given day (runs, rides, workouts, ...)."""
    cdate = to_iso_date(day)
    return get_client().get_activities_by_date(cdate, cdate)


def is_running_activity(activity: dict[str, Any]) -> bool:
    """True for Garmin's whole running family — running itself (typeId 1)
    plus its children (treadmill/trail/track/indoor running, ..., all
    carrying parentTypeId 1) — false for golf, walking, cycling, strength,
    etc. Used to compute "running miles" as distinct from total activity
    distance (which would double-count e.g. a round of golf's GPS track)."""
    activity_type = activity.get("activityType") or {}
    return activity_type.get("typeId") == 1 or activity_type.get("parentTypeId") == 1


# --- Bulk-range endpoints, for pulling history (see src/history/sync.py) ---
#
# Garmin has genuine range endpoints for these, unlike the single-day
# metrics above — one call each covers up to ~a year (the library chunks
# transparently where the underlying endpoint needs it). Training
# readiness/recovery has no such endpoint; src/history/sync.py loops
# get_morning_recovery() per day for that one.


def get_activities_range(
    start: date | str, end: date | str
) -> list[dict[str, Any]]:
    """All activities between two dates (inclusive), across the whole range."""
    return get_client().get_activities_by_date(to_iso_date(start), to_iso_date(end))


def get_sleep_range(start: date | str, end: date | str) -> list[dict[str, Any]]:
    """Daily sleep summaries (score, deep/rem/light seconds, RHR, HRV, ...)."""
    return get_client().get_sleep_daily(to_iso_date(start), to_iso_date(end))


def get_rhr_range(start: date | str, end: date | str) -> list[dict[str, Any]]:
    """Daily resting heart rate as [{"calendarDate": ..., "value": ...}, ...]."""
    return get_client().get_rhr_daily(to_iso_date(start), to_iso_date(end))


def get_hrv_range(start: date | str, end: date | str) -> dict[str, Any] | None:
    """HRV summaries for the range, as {"hrvSummaries": [...]}."""
    return get_client().get_hrv_data_range(to_iso_date(start), to_iso_date(end))


def get_vo2max_range(start: date | str, end: date | str) -> list[dict[str, Any]]:
    """VO2 max readings for the range. Sparse — Garmin only emits a new one
    every so often, not daily."""
    return get_client().get_max_metrics_range(to_iso_date(start), to_iso_date(end))


_BODY_BATTERY_CHUNK_DAYS = 28  # matches the limit Garmin's own get_sleep_daily chunks around


def get_body_battery_range(start: date | str, end: date | str) -> list[dict[str, Any]]:
    """One entry per day, each carrying that day's body battery time series.

    Unlike get_sleep_daily/get_rhr_daily, the underlying get_body_battery
    call doesn't chunk long ranges itself — Garmin's endpoint 400s with
    "requested date range is too big" past ~a month, so this does the
    chunking the library omitted.
    """
    start_date = date.fromisoformat(to_iso_date(start))
    end_date = date.fromisoformat(to_iso_date(end))

    results: list[dict[str, Any]] = []
    chunk_start = start_date
    while chunk_start <= end_date:
        chunk_end = min(chunk_start + timedelta(days=_BODY_BATTERY_CHUNK_DAYS - 1), end_date)
        results.extend(
            get_client().get_body_battery(chunk_start.isoformat(), chunk_end.isoformat())
        )
        chunk_start = chunk_end + timedelta(days=1)
    return results


def get_daily_health_snapshot(day: date | str | None = None) -> dict[str, Any]:
    """Aggregate the metrics most relevant to a morning check-in into one dict.

    Best-effort: if a given endpoint errors or isn't enabled for this account,
    its entry becomes {"error": "..."} instead of raising, so one flaky
    endpoint doesn't take down the whole snapshot.
    """
    cdate = to_iso_date(day)
    fetchers = {
        "summary": get_daily_summary,
        "sleep": get_sleep,
        "heart_rate": get_heart_rate,
        "hrv": get_hrv,
        "stress": get_stress,
        "body_battery": get_body_battery,
        "training_readiness": get_training_readiness,
        "training_status": get_training_status,
    }
    snapshot: dict[str, Any] = {"date": cdate}
    for key, fetch in fetchers.items():
        try:
            snapshot[key] = fetch(cdate)
        except GARMIN_ERRORS as e:
            snapshot[key] = {"error": str(e)}
    return snapshot


if __name__ == "__main__":
    # Quick manual check: `python -m src.tools.garmin` prints today's snapshot.
    print(json.dumps(get_daily_health_snapshot(), indent=2, default=str))
