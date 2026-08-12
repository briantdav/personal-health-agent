# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Personal AI Health Agent that analyzes Garmin/Whoop/Coros data along with a morning intake journal to derive insights and suggest training and nutrition protocol based on current health and fitness goals.

## Current state

Garmin data ingestion, a daily dashboard (with a morning-journal habit-tracker modal), a year-of-history trends page, and an automatic daily Garmin sync (via `launchd`, see Architecture) exist; `src/agent.py` (the intended orchestrator/recommendation entrypoint) is still an empty placeholder, as is Whoop/Coros integration, nutrition tracking, and turning journal + Garmin data into actual insights. The planned shape for that last piece: the daily *sync* stays a scheduled/deterministic job (no LLM involved, what's already built), but journal/Garmin → insights will need to be a *user-triggered* flow (e.g. calling the Claude API right after the journal form submits) rather than another scheduled job, since it depends on text only the user can write each morning.

## Commands

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

pytest tests/ -v                        # run the test suite
pytest tests/test_metrics.py -v         # run a single test file
uvicorn src.web.app:app --reload        # run the dashboard at http://127.0.0.1:8000 (/ and /trends)
python -m src.tools.garmin              # print today's raw Garmin snapshot as JSON (auth smoke test)
python -m src.history.sync --days 365   # backfill data/history.db for the /trends page (see below — slow)
python -m src.history.daily_sync --force  # on-demand equivalent of the automatic daily sync
```

First run of anything that touches Garmin will prompt interactively for email/password/MFA (or read `GARMIN_EMAIL`/`GARMIN_PASSWORD` from `.env` — copy `.env.example`). OAuth tokens are then cached to `~/.garminconnect` (or `GARMINTOKENS`) so subsequent runs don't re-prompt.

## Architecture

**Garmin has no self-serve API for individuals** — the Connect Developer Health API requires applying as a legal entity. `src/tools/garmin.py` works around this with the unofficial [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) library, logging in as your own Garmin Connect account the way the mobile app does. This is the pattern for any future per-source integration (Whoop/Coros): a thin wrapper module in `src/tools/` around whatever unofficial or official client exists, exposing plain functions keyed by date rather than raw API responses.

Layers, in order of raw → shaped → presented:

1. **`src/tools/garmin.py`** — raw Garmin Connect data.
   - Single-day functions (`get_sleep`, `get_hrv`, `get_training_readiness`, ...) accept an optional `date | str | None`, normalized via `to_iso_date`. `get_daily_health_snapshot()` aggregates everything for one day, catching `GARMIN_ERRORS` per-endpoint so one flaky endpoint doesn't take the rest down — reuse that tuple (and that catch-per-field pattern) for any new aggregate rather than catching bare `Exception`.
   - Bulk-range functions (`get_sleep_range`, `get_rhr_range`, `get_hrv_range`, `get_vo2max_range`, `get_body_battery_range`, `get_activities_range`) exist because Garmin has genuine range endpoints for these — one call covers up to ~a year. **Training readiness/recovery has no range endpoint**; pulling its history means one call per day (see `src/history/sync.py`).
2. **`src/history/`** — the local cache the trends page reads from, so a year of daily data across ~10 metrics doesn't mean hitting Garmin (slowly, and rate-limit-riskily) on every page load.
   - `db.py` — SQLite (`data/history.db`, gitignored), one row per calendar date, columns nullable (a day with no logged activity is `NULL`, not `0`). `upsert_day()` merges fields from different syncers without clobbering columns it wasn't given.
   - `sync.py` — orchestrates a backfill over an arbitrary date range: bulk-range calls for most metrics, plus the slow paced per-day loop for recovery (commits every 10 days, so `Ctrl+C` mid-backfill doesn't lose progress). Run via `python -m src.history.sync`.
   - `daily_sync.py` — **the automatic daily sync**. Garmin has no push/webhook for individual accounts (the official Health API partner program that supports push is business/legal-entity only), so this approximates one: a `launchd` job (installed from `scripts/com.personalhealthagent.dailysync.plist` into `~/Library/LaunchAgents/`) invokes it every 20 minutes between 5:30–11:00am. Each invocation is a cheap, idempotent no-op unless it's both in-window *and* today isn't synced yet *and* Garmin actually has today's sleep data — so frequent invocation is fine, and there's no long-lived polling process to keep alive across sleep/wake. Logs to `data/daily_sync.log` (silent when it no-ops). Manual on-demand equivalent: `python -m src.history.daily_sync --force`. See the `garmin-sync` skill (`.claude/skills/garmin-sync/`) for the full on-demand/troubleshooting command set.
3. **`src/journal/`** — the morning journal habit tracker, storage-only (mirrors `src/history/` but for user-entered data, not Garmin-synced). `db.py` owns a `journal_entries` table in the *same* `data/history.db` file (different table — habits are joinable against Garmin metrics by date later, without being conflated with synced data). `save_entry()` is a plain upsert primitive, same merge semantics as `history/db.py`'s `upsert_day`.
4. **`src/web/journal.py`** — one `QUESTIONS` list (key, label, `bool`/`number`/`time`, optional `show_if` for a conditional field like "how many drinks?" only mattering if "drink alcohol?" is yes) drives the modal form, the submit parser, *and* storage, instead of hardcoding ~14 near-identical fields in multiple places. `parse_form()` makes the "submitted" semantics explicit: an unchecked HTML checkbox is simply absent from form data, so its absence means `False`, not "unanswered" — and a `show_if` field gets cleared to `None` server-side if its parent isn't true, even if a stale value came through, so editing "drink alcohol? No" on a resubmit can't leave yesterday's drink count behind.
5. **`src/web/metrics.py`** — today's dashboard view model: unit conversions (meters→miles, seconds→hours) and status bucketing (`_recovery_status`). `get_todays_training_plan()` is a placeholder — where `src/agent.py`'s real recommendation logic should eventually plug in.
6. **`src/web/trends.py`** — reads `src/history/db.py`, fills date gaps with `None`, forward-fills VO2 max (Garmin only emits a new reading occasionally, not daily), and rolls up into weekly/monthly series. Volume metrics (`miles`, `workout_hours`, in `SUM_METRICS`) aggregate as a **sum** ("weekly mileage"); everything else averages — mislabeling a runner's weekly mileage as a daily average would be actively misleading.
7. **`src/web/app.py`** — FastAPI app.
   - `/` + `/api/metrics` — today's dashboard (stat tiles + training-plan card), plus the journal modal (`dashboard.html` renders it inline from `journal_questions`/`journal_values`, hidden by default). Its JS auto-opens the modal on load unless today's already been submitted (`journal_already_submitted`) or dismissed this session (`localStorage["journal-dismissed-<date>"]`) — reopen anytime via the 📝 header icon. Submits via `fetch` to `POST /journal` (no page reload); needs `python-multipart` installed for form parsing.
   - `/trends` + `/api/trends` — small-multiple line charts (`src/web/static/trends.js`, vanilla SVG, no charting library), one per metric, with a Daily/Weekly/Monthly toggle and a collapsible data table (the WCAG-clean fallback). Shows an empty-state pointing at the sync command if `data/history.db` hasn't been populated yet.
   - Styling in `src/web/static/style.css` follows this repo's data-viz conventions: light/dark via `data-theme` + `prefers-color-scheme`, status colors reserved for state (never a categorical color), single-hue accent line + recessive hairline gridlines for charts. Watch the `[hidden]` gotcha if adding more overlays/modals: an author-stylesheet class rule like `.modal-overlay { display: flex }` beats the browser's default `[hidden] { display: none }` unless you add an explicit `.modal-overlay[hidden] { display: none }` override (higher specificity) — already done for the journal modal.

`data/` (including `history.db`) is gitignored except `.gitkeep` — never commit real data there.
