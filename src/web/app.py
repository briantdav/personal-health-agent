"""FastAPI app serving the daily health dashboard.

Run with: uvicorn src.web.app:app --reload
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.web import journal
from src.web.metrics import get_dashboard_metrics
from src.web.trends import get_trends

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Personal Health Agent")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def greeting(now: datetime | None = None) -> str:
    """"Good morning, Brian" (or just "Good morning" if USER_NAME is unset).
    Page-chrome, not Garmin data, so it lives here rather than in metrics.py."""
    hour = (now or datetime.now()).hour
    period = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
    name = os.getenv("USER_NAME", "").strip()
    return f"Good {period}, {name}" if name else f"Good {period}"


@app.get("/")
def dashboard(request: Request):
    metrics = get_dashboard_metrics()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "metrics": metrics,
            "greeting": greeting(),
            "journal_questions": journal.QUESTIONS,
            "journal_values": journal.get_values(),
            "journal_already_submitted": journal.already_submitted(),
        },
    )


@app.post("/journal")
async def journal_submit(request: Request):
    form = dict(await request.form())
    entry_date = form.pop("entry_date", None) or date.today().isoformat()
    journal.save_entry(entry_date, form)
    return JSONResponse({"ok": True, "date": entry_date})


@app.get("/api/metrics")
def api_metrics() -> dict:
    return get_dashboard_metrics()


@app.get("/trends")
def trends_page(request: Request, days: int = 365):
    data = get_trends(days)
    return templates.TemplateResponse(
        request,
        "trends.html",
        {"trends": data, "days": days, "trends_json": json.dumps(data)},
    )


@app.get("/api/trends")
def api_trends(days: int = 365) -> dict:
    return get_trends(days)
