"""Backfills/refreshes data/history.db from Garmin Connect.

Run standalone (needs a cached Garmin login — see src/tools/garmin.py):

    python -m src.history.sync --days 365
    python -m src.history.sync --start 2025-08-01 --end 2025-08-31

Sleep (incl. score/deep/REM), resting heart rate, HRV, VO2 max, body
battery, and activities all have real bulk-range endpoints, so a year of
those is a handful of API calls. Training readiness / recovery score has
no range endpoint — this loops one call per day for that metric alone,
paced by --delay seconds to avoid GarminConnectTooManyRequestsError. That
loop dominates the runtime: a full year is ~365 calls, so expect this to
take several minutes. Progress is committed to disk as it goes (day by
day for the recovery loop), so it's safe to Ctrl+C and resume later —
re-running just re-fetches and overwrites, it doesn't append.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime, timedelta

from src.history import db
from src.tools import garmin

METERS_PER_MILE = 1609.344


def _daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _sync_sleep(conn, start: str, end: str) -> None:
    """Sleep hours, deep/REM sleep, sleep score — plus RHR and overnight HRV,
    which this same endpoint happens to carry."""
    for row in garmin.get_sleep_range(start, end):
        cal_date = row.get("calendarDate")
        values = row.get("values") or {}
        if not cal_date or not values:
            continue

        fields: dict[str, float | int] = {}
        if values.get("totalSleepTimeInSeconds") is not None:
            fields["sleep_hours"] = round(values["totalSleepTimeInSeconds"] / 3600, 2)
        if values.get("deepTime") is not None:
            fields["deep_sleep_hours"] = round(values["deepTime"] / 3600, 2)
        if values.get("remTime") is not None:
            fields["rem_sleep_hours"] = round(values["remTime"] / 3600, 2)
        if values.get("sleepScore") is not None:
            fields["sleep_score"] = values["sleepScore"]
        if values.get("restingHeartRate") is not None:
            fields["resting_heart_rate"] = values["restingHeartRate"]
        if values.get("avgOvernightHrv") is not None:
            fields["hrv_overnight_avg"] = values["avgOvernightHrv"]

        if fields:
            db.upsert_day(conn, cal_date, **fields)


def _sync_rhr(conn, start: str, end: str) -> None:
    """The dedicated RHR endpoint — more complete than sleep's, since it
    doesn't depend on a sleep session being recorded that night."""
    for row in garmin.get_rhr_range(start, end):
        cal_date, value = row.get("calendarDate"), row.get("value")
        if cal_date and value is not None:
            db.upsert_day(conn, cal_date, resting_heart_rate=value)


def _sync_hrv(conn, start: str, end: str) -> None:
    data = garmin.get_hrv_range(start, end) or {}
    for row in data.get("hrvSummaries") or []:
        cal_date, value = row.get("calendarDate"), row.get("lastNightAvg")
        if cal_date and value is not None:
            db.upsert_day(conn, cal_date, hrv_overnight_avg=value)


def _sync_vo2max(conn, start: str, end: str) -> None:
    for row in garmin.get_vo2max_range(start, end):
        generic = (row or {}).get("generic") or {}
        cal_date, value = generic.get("calendarDate"), generic.get("vo2MaxValue")
        if cal_date and value is not None:
            db.upsert_day(conn, cal_date, vo2_max=value)


def _sync_body_battery(conn, start: str, end: str) -> None:
    """Stores each day's peak body battery level as the trend value —
    Garmin gives a full intraday time series, not a single daily number."""
    for row in garmin.get_body_battery_range(start, end):
        cal_date = row.get("date")
        levels = [v[1] for v in row.get("bodyBatteryValuesArray") or [] if len(v) > 1 and v[1] is not None]
        if cal_date and levels:
            db.upsert_day(conn, cal_date, body_battery_peak=max(levels))


def _sync_activities(conn, start: str, end: str) -> None:
    """Sums distance/duration per calendar day across all activities that day."""
    totals: dict[str, dict[str, float]] = {}
    for activity in garmin.get_activities_range(start, end):
        start_local = activity.get("startTimeLocal") or ""
        cal_date = start_local.split(" ")[0] if start_local else None
        if not cal_date:
            continue
        bucket = totals.setdefault(cal_date, {"meters": 0.0, "seconds": 0.0})
        bucket["meters"] += activity.get("distance") or 0
        bucket["seconds"] += activity.get("duration") or 0

    for cal_date, totals_for_day in totals.items():
        db.upsert_day(
            conn,
            cal_date,
            miles=round(totals_for_day["meters"] / METERS_PER_MILE, 2),
            workout_hours=round(totals_for_day["seconds"] / 3600, 2),
        )


def _sync_recovery(conn, start: date, end: date, delay: float) -> None:
    total_days = (end - start).days + 1
    for i, d in enumerate(_daterange(start, end), start=1):
        iso = d.isoformat()
        try:
            reading = garmin.get_morning_recovery(iso)
        except garmin.GARMIN_ERRORS as e:
            print(f"  [{i}/{total_days}] {iso}: skipped ({e})", file=sys.stderr)
            continue

        if reading:
            db.upsert_day(
                conn,
                iso,
                recovery_score=reading.get("score"),
                recovery_level=reading.get("level"),
            )

        if i % 10 == 0 or i == total_days:
            conn.commit()  # checkpoint progress — safe to interrupt a long backfill
        if i % 25 == 0 or i == total_days:
            print(f"  recovery backfill: {i}/{total_days} days", file=sys.stderr)

        time.sleep(delay)


def sync(start: date, end: date, delay: float = 0.4, skip_recovery: bool = False) -> None:
    start_iso, end_iso = start.isoformat(), end.isoformat()

    print(f"Syncing sleep/RHR/HRV/VO2max/body battery/activities {start_iso}..{end_iso}...")
    with db.connect() as conn:
        _sync_sleep(conn, start_iso, end_iso)
        _sync_rhr(conn, start_iso, end_iso)
        _sync_hrv(conn, start_iso, end_iso)
        _sync_vo2max(conn, start_iso, end_iso)
        _sync_body_battery(conn, start_iso, end_iso)
        _sync_activities(conn, start_iso, end_iso)

    if not skip_recovery:
        total_days = (end - start).days + 1
        print(
            f"Syncing recovery score {start_iso}..{end_iso} "
            f"(no bulk endpoint — {total_days} calls, ~{delay}s apart, "
            f"~{round(total_days * delay / 60, 1)}+ min)..."
        )
        with db.connect() as conn:
            _sync_recovery(conn, start, end, delay)

    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=365, help="days back from today (default 365)")
    parser.add_argument("--start", type=str, help="start date YYYY-MM-DD (overrides --days)")
    parser.add_argument("--end", type=str, help="end date YYYY-MM-DD (default: today)")
    parser.add_argument("--delay", type=float, default=0.4, help="seconds between recovery-score calls (default 0.4)")
    parser.add_argument("--skip-recovery", action="store_true", help="skip the slow per-day recovery backfill")
    args = parser.parse_args()

    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    start = (
        datetime.strptime(args.start, "%Y-%m-%d").date()
        if args.start
        else end - timedelta(days=args.days - 1)
    )

    sync(start, end, delay=args.delay, skip_recovery=args.skip_recovery)


if __name__ == "__main__":
    main()
