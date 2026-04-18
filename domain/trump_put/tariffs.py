from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_FILE = Path(__file__).parent / "tariff_data.json"


def load_tariffs(
    country: str | None = None,
    status: str | None = None,
) -> list[dict]:
    try:
        data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load tariff data")
        return []

    if country:
        c = country.lower()
        data = [t for t in data if c in t.get("target", "").lower()]
    if status:
        data = [t for t in data if t.get("status") == status]

    return data


def get_summary() -> dict:
    tariffs = load_tariffs()
    active = [t for t in tariffs if t.get("status") in ("effective", "reduced")]
    paused = [t for t in tariffs if t.get("status") == "paused"]
    struck = [t for t in tariffs if t.get("status") in ("struck_down", "exempted", "expired")]

    return {
        "total_events": len(tariffs),
        "currently_active": len(active),
        "paused": len(paused),
        "removed_or_expired": len(struck),
        "last_updated": tariffs[-1]["date"] if tariffs else None,
    }
