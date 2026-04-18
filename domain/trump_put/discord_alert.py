from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request

from .models import TrumpPutReport
from .formatter import format_discord

logger = logging.getLogger(__name__)

_last_alert_time: float = 0
_lock = threading.Lock()
_COOLDOWN = 21600  # 6 hours


def _get_webhook() -> str | None:
    return os.environ.get("DISCORD_TRUMP_PUT_WEBHOOK", "").strip() or None


def should_alert(score: int, prev_score: int | None = None) -> bool:
    if score < 40:
        return False
    if prev_score is not None and prev_score >= 40:
        return False
    with _lock:
        if time.time() - _last_alert_time < _COOLDOWN:
            return False
    return True


def send_alert(report: TrumpPutReport) -> bool:
    global _last_alert_time
    webhook = _get_webhook()
    if not webhook:
        logger.warning("DISCORD_TRUMP_PUT_WEBHOOK not configured")
        return False

    text = format_discord(report)

    payload = json.dumps({"content": text}).encode()
    req = urllib.request.Request(
        webhook,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                with _lock:
                    _last_alert_time = time.time()
                logger.info("Discord alert sent (score=%d)", report.composite_score)
                return True
            logger.warning("Discord webhook returned %d", resp.status)
    except Exception:
        logger.exception("Failed to send Discord alert")
    return False


def send_alert_async(report: TrumpPutReport) -> None:
    threading.Thread(target=send_alert, args=(report,), daemon=True).start()
