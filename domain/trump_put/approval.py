from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[float, str, float]] = {}
_lock = threading.Lock()
_TTL = 21600  # 6 hours

_538_URL = (
    "https://projects.fivethirtyeight.com/polls/favorability/"
    "donald-trump/polls.json"
)
_RCP_URL = (
    "https://www.realclearpolling.com/api/polls/favorability/"
    "donald-trump"
)


def fetch() -> tuple[float, str] | None:
    with _lock:
        if "approval" in _cache:
            val, as_of, ts = _cache["approval"]
            if time.time() - ts < _TTL:
                return (val, as_of)

    result = _try_538() or _try_rcp()

    if result:
        val, as_of = result
        with _lock:
            _cache["approval"] = (val, as_of, time.time())
    return result


def _try_538() -> tuple[float, str] | None:
    try:
        req = urllib.request.Request(_538_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        if not data:
            return None
        latest = data[0]
        pct = float(latest.get("pct_estimate", latest.get("pct", 0)))
        date_str = latest.get("end_date", latest.get("created_at", ""))[:10]
        if pct > 0:
            return (pct, date_str)
    except Exception:
        logger.debug("FiveThirtyEight approval fetch failed", exc_info=True)
    return None


def _try_rcp() -> tuple[float, str] | None:
    try:
        req = urllib.request.Request(_RCP_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        spread = data.get("spread", {})
        if "approve" in spread:
            return (float(spread["approve"]), spread.get("date", "")[:10])
    except Exception:
        logger.debug("RCP approval fetch failed", exc_info=True)
    return None
