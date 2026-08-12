"""Checks once whether today's Garmin sleep data has landed yet, and if
so runs a small catch-up sync.

Garmin has no push/webhook for individual accounts — the official Connect
Developer Health API partner program (which does support push) is
business/legal-entity only. This "ask repeatedly, act the moment it's
ready" pattern is the closest available substitute: a launchd job invokes
this script every ~20 minutes during a morning window (see
scripts/com.personalhealthagent.dailysync.plist), and it's cheap and
idempotent to call repeatedly — it no-ops outside the window or once
today's already synced, rather than polling internally itself.

    python -m src.history.daily_sync            # the check launchd runs
    python -m src.history.daily_sync --force     # sync now, bypassing the window/already-synced guards
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, time as dtime, timedelta

from src.history import db, sync
from src.tools import garmin

ACTIVE_WINDOW = (dtime(5, 30), dtime(11, 0))  # local time
CATCH_UP_DAYS = 2  # last night + today, in case a prior run partially failed


def _log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {message}")


def _already_synced_today() -> bool:
    today = date.today().isoformat()
    rows = db.get_range(today, today)
    return bool(rows) and rows[0].get("recovery_score") is not None


def _sleep_ready(today: str) -> bool:
    try:
        data = garmin.get_sleep(today)
    except garmin.GARMIN_ERRORS as e:
        _log(f"sleep check failed ({e})")
        return False
    seconds = ((data or {}).get("dailySleepDTO") or {}).get("sleepTimeSeconds")
    return seconds is not None


def _run_catch_up_sync() -> None:
    end = date.today()
    start = end - timedelta(days=CATCH_UP_DAYS - 1)
    sync.sync(start, end, delay=0.4)
    _log("Daily sync complete.")


def check_and_sync() -> bool:
    """The launchd-driven check: silent no-op outside the window or once
    today's done, so getting invoked every 20 minutes all day is cheap."""
    now = datetime.now().time()
    if not (ACTIVE_WINDOW[0] <= now <= ACTIVE_WINDOW[1]):
        return False
    if _already_synced_today():
        return False

    today = date.today().isoformat()
    if not _sleep_ready(today):
        _log(f"{today}'s sleep data isn't ready yet — will check again")
        return False

    _log(f"{today}'s sleep data is ready — syncing last {CATCH_UP_DAYS} days")
    _run_catch_up_sync()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--force",
        action="store_true",
        help="sync now regardless of time window or whether today's already synced (still requires sleep data to exist)",
    )
    args = parser.parse_args()

    if not args.force:
        check_and_sync()
        return

    today = date.today().isoformat()
    if not _sleep_ready(today):
        _log(f"{today}'s sleep data isn't on Garmin's side yet.")
        sys.exit(1)
    _log(f"Forcing sync for the last {CATCH_UP_DAYS} days.")
    _run_catch_up_sync()


if __name__ == "__main__":
    main()
