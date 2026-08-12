"""FastAPI app serving the daily health dashboard.

Run with: uvicorn src.web.app:app --reload
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.web.metrics import get_dashboard_metrics
from src.web.trends import get_trends

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Personal Health Agent")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/")
def dashboard(request: Request):
    metrics = get_dashboard_metrics()
    return templates.TemplateResponse(request, "dashboard.html", {"metrics": metrics})


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
