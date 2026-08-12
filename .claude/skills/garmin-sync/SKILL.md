---
description: Sync Garmin data into this repo's local dashboard cache (data/history.db) — on-demand refresh, checking whether today's automatic sync has run, or a full historical backfill. Use when the user asks to sync/refresh/update/backfill Garmin data, asks whether today's data is in yet, or asks about the daily auto-sync job.
---

# Garmin sync

This repo never queries Garmin live from the dashboard — `src/web/metrics.py`
(today) and `src/web/trends.py` (history) both read from the local SQLite
cache at `data/history.db`. This skill is how that cache gets populated or
refreshed. See `CLAUDE.md`'s Architecture section for the full picture.

Garmin has no push/webhook for individual accounts, so "the moment it's
ready" is approximated by a `launchd` job that invokes
`src/history/daily_sync.py` every 20 minutes between 5:30–11:00am, which
no-ops unless today's sleep data has actually landed on Garmin's side.

## Sync now, on demand

```bash
source .venv/bin/activate
python -m src.history.daily_sync --force   # last 2 days, bypasses the time-window/already-synced guards
```

Fails with a clear message (exit 1) if Garmin doesn't have today's sleep
data yet rather than syncing partial/stale data.

## Check whether the automatic daily job is working

```bash
cat data/daily_sync.log                     # empty until it actually syncs something (silent no-op otherwise)
launchctl list | grep dailysync              # "-" = loaded but hasn't fired since load; a number = last exit code
```

If it's not listed as loaded, reinstall it:

```bash
cp scripts/com.personalhealthagent.dailysync.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.personalhealthagent.dailysync.plist
```

## Full historical backfill (or re-backfill a specific window)

```bash
python -m src.history.sync --days 365                        # a year back from today
python -m src.history.sync --start 2025-08-01 --end 2025-08-31
```

Most metrics sync in a handful of bulk-range API calls; recovery score has
no bulk endpoint, so that part loops one call per day (~0.4s apart) — a
full year takes several minutes. Safe to `Ctrl+C` and resume; it re-fetches
and overwrites rather than appending, and commits every 10 recovery-score
days so progress isn't lost.

## First-time setup (no Garmin login cached yet)

```bash
python -m src.tools.garmin   # prompts for email/password/MFA interactively, caches the OAuth token
```

Do this in a real terminal, not by having Claude type the password —
credentials shouldn't pass through the conversation.
