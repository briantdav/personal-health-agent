"""Tests for the FastAPI dashboard app (src/web/app.py).

Patches get_dashboard_metrics/get_trends so no network calls or real
credentials are needed to run the suite. Journal routes hit the real
src/journal storage against an isolated tmp-path DB instead, since that's
cheap and exercises the actual save/read path end to end.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("HISTORY_DB_PATH", str(tmp_path / "test_history.db"))

FAKE_METRICS = {
    "date": "2026-08-12",
    "miles": 4.2,
    "sleep_hours": 7.5,
    "workout_hours": 0.75,
    "recovery_score": 82,
    "recovery_level": "HIGH",
    "recovery_status": "good",
    "training_plan": {"summary": "Rest day.", "details": None},
}


@patch("src.web.app.get_dashboard_metrics", return_value=FAKE_METRICS)
def test_dashboard_renders_metrics(mock_metrics):
    response = client.get("/")

    assert response.status_code == 200
    assert "4.2" in response.text
    assert "Rest day." in response.text


@patch("src.web.app.get_dashboard_metrics", return_value=FAKE_METRICS)
def test_api_metrics_returns_json(mock_metrics):
    response = client.get("/api/metrics")

    assert response.status_code == 200
    assert response.json() == FAKE_METRICS


FAKE_TRENDS = {
    "metrics": {"miles": "Miles", "sleep_score": "Sleep score"},
    "sum_metrics": ["miles"],
    "has_data": True,
    "daily": [{"date": "2026-08-11", "miles": 10.01, "sleep_score": 76}],
    "weekly": [{"period": "2026-W32", "miles": 10.01, "sleep_score": 76}],
    "monthly": [{"period": "2026-08", "miles": 10.01, "sleep_score": 76}],
}


@patch("src.web.app.get_trends", return_value=FAKE_TRENDS)
def test_trends_page_renders_charts_and_table(mock_trends):
    response = client.get("/trends?days=90")

    assert response.status_code == 200
    assert "10.01" in response.text
    assert "Sleep score" in response.text
    mock_trends.assert_called_once_with(90)


@patch("src.web.app.get_trends", return_value={**FAKE_TRENDS, "has_data": False, "daily": [], "weekly": [], "monthly": []})
def test_trends_page_shows_empty_state_without_data(mock_trends):
    response = client.get("/trends")

    assert response.status_code == 200
    assert "python -m src.history.sync" in response.text


@patch("src.web.app.get_trends", return_value=FAKE_TRENDS)
def test_api_trends_returns_json(mock_trends):
    response = client.get("/api/trends?days=30")

    assert response.status_code == 200
    assert response.json() == FAKE_TRENDS
    mock_trends.assert_called_once_with(30)


@patch("src.web.app.get_dashboard_metrics", return_value=FAKE_METRICS)
def test_dashboard_renders_journal_modal_with_all_questions(mock_metrics):
    response = client.get("/")

    assert response.status_code == 200
    assert 'id="journal-modal"' in response.text
    assert "How many cups of water?" in response.text
    assert "Time of last drink" in response.text


def test_journal_submit_saves_and_is_reflected_on_next_dashboard_load():
    response = client.post(
        "/journal",
        data={
            "entry_date": "2026-08-12",
            "water_cups": "6",
            "took_creatine": "on",
            "drank_alcohol": "on",
            "drink_count": "2",
            "last_drink_time": "21:30",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "date": "2026-08-12"}

    from src.web import journal

    values = journal.get_values("2026-08-12")
    assert values["water_cups"] == 6.0
    assert values["took_creatine"] == 1
    assert values["drink_count"] == 2.0
    assert journal.already_submitted("2026-08-12") is True


def test_journal_submit_unchecked_boxes_save_as_false():
    response = client.post("/journal", data={"entry_date": "2026-08-12", "water_cups": "4"})

    assert response.status_code == 200

    from src.web import journal

    values = journal.get_values("2026-08-12")
    assert values["took_creatine"] == 0
    assert values["drank_alcohol"] == 0
