"""Morning journal habit tracker — one config list drives the modal form
(rendered inside dashboard.html), the submit handler, and storage, instead
of hardcoding ~14 near-identical fields in each place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date
from typing import Any

from src.journal import db


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    kind: str  # "bool" | "number" | "time"
    show_if: str | None = None  # only meaningful when this other bool question is True


QUESTIONS: list[Question] = [
    Question("water_cups", "How many cups of water?", "number"),
    Question("took_creatine", "Take creatine?", "bool"),
    Question("hit_protein_goal", "Hit protein goal?", "bool"),
    Question("read_before_bed", "Read before bed?", "bool"),
    Question("read_devotional", "Read Bible and devotional in the morning?", "bool"),
    Question("stretched_before_bed", "Stretching before bed?", "bool"),
    Question("cold_plunge", "Cold plunge?", "bool"),
    Question("sauna_or_hot_tub", "Sauna/hot tub use?", "bool"),
    Question("took_magnesium", "Take magnesium?", "bool"),
    Question("drank_alcohol", "Drink alcohol?", "bool"),
    Question("drink_count", "How many drinks?", "number", show_if="drank_alcohol"),
    Question("last_drink_time", "Time of last drink", "time", show_if="drank_alcohol"),
    Question("used_phone_in_bed", "Use phone in bed?", "bool"),
    Question("worked_late", "Work late?", "bool"),
    Question("meditated_or_prayed", "Meditate/pray?", "bool"),
    Question("last_meal_time", "Time of last meal", "time"),
]

BOOL_KEYS = {q.key for q in QUESTIONS if q.kind == "bool"}
NUMBER_KEYS = {q.key for q in QUESTIONS if q.kind == "number"}
TIME_KEYS = {q.key for q in QUESTIONS if q.kind == "time"}


def parse_form(form: dict[str, str]) -> dict[str, Any]:
    """Raw submitted form data -> typed values ready for storage.

    HTML checkboxes only appear in form data when checked, so a bool
    question's absence means False, not "unanswered" — the whole form is
    always submitted as one unit, so every question gets an explicit value.
    """
    fields: dict[str, Any] = {}
    for key in BOOL_KEYS:
        fields[key] = 1 if key in form else 0

    for key in NUMBER_KEYS:
        raw = (form.get(key) or "").strip()
        fields[key] = float(raw) if raw else None

    for key in TIME_KEYS:
        raw = (form.get(key) or "").strip()
        fields[key] = raw or None

    # Conditional fields only make sense when their parent is true —
    # clear stale values otherwise (e.g. an old drink count left over
    # from before today's entry was edited back to "no alcohol").
    for q in QUESTIONS:
        if q.show_if and not fields.get(q.show_if):
            fields[q.key] = None

    return fields


def save_entry(entry_date: str, form: dict[str, str]) -> None:
    db.save_entry(entry_date, **parse_form(form))


def get_values(entry_date: str | None = None) -> dict[str, Any]:
    """Existing values for the form, or all-blank defaults for a fresh entry."""
    existing = db.get_entry(entry_date or _date.today().isoformat()) or {}
    return {q.key: existing.get(q.key) for q in QUESTIONS}


def already_submitted(entry_date: str | None = None) -> bool:
    return db.get_entry(entry_date or _date.today().isoformat()) is not None
