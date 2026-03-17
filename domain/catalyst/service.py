"""Catalyst service: upcoming catalyst query."""
from __future__ import annotations

import datetime
from pathlib import Path

from .repository import list_catalysts
from domain.scenario.repository import get_scenario


def upcoming_catalysts(
    db_path: Path,
    as_of: str | None = None,
    days: int = 30,
) -> list[dict]:
    """
    Return pending catalysts whose event_date falls within [as_of, as_of+days].

    - Only status='pending' catalysts are returned.
    - Catalysts with event_date=NULL are excluded.
    - Results are sorted by event_date ASC.
    - Each entry includes a 'scenario' key: the linked scenario_plan dict or None.

    as_of defaults to today (local date) when not provided.
    """
    if as_of is None:
        as_of = datetime.date.today().isoformat()

    start = datetime.date.fromisoformat(as_of)
    end = start + datetime.timedelta(days=days)
    end_str = end.isoformat()

    all_pending = list_catalysts(db_path, status="pending")

    result = []
    for cat in all_pending:
        ed = cat.get("event_date")
        if ed is None:
            continue
        if as_of <= ed <= end_str:
            entry = dict(cat)
            entry["scenario"] = get_scenario(db_path, cat["id"])
            result.append(entry)

    result.sort(key=lambda c: c["event_date"])
    return result
