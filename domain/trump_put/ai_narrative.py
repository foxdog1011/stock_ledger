from __future__ import annotations

import logging
import os
import threading
import time

from .models import TrumpPutReport

logger = logging.getLogger(__name__)

_cache: dict[str, tuple[str, float]] = {}
_lock = threading.Lock()
_TTL = 600  # 10 minutes


def generate(report: TrumpPutReport) -> str | None:
    cache_key = str(report.composite_score)
    with _lock:
        if cache_key in _cache:
            text, ts = _cache[cache_key]
            if time.time() - ts < _TTL:
                return text

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None

    indicators = []
    for ind in [report.sp500, report.tnx, report.vix, report.dxy, report.approval]:
        if ind:
            indicators.append(f"- {ind.name}: {ind.value:.2f} (zone: {ind.zone}, score: {ind.score}/100)")

    events_text = ""
    if report.nearby_events:
        events_text = "\nRecent historical parallels:\n"
        for ev in report.nearby_events[:4]:
            sp = f" S&P {ev.sp500:,.0f}" if ev.sp500 else ""
            events_text += f"- {ev.date}{sp}: {ev.description} [{ev.event_type}]\n"

    prompt = f"""You are a macro analyst tracking the "Trump Put" — the theory that Trump softens trade/military policy when markets drop to pain thresholds.

Current readings:
{chr(10).join(indicators)}

Composite score: {report.composite_score}/100 ({report.composite_label})
{events_text}
Write 2-3 concise sentences analyzing current market pressure on the Trump administration. Be specific about which indicators drive the score. Reference a historical parallel if relevant. No disclaimers."""

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.7,
        )
        text = resp.choices[0].message.content.strip()
        with _lock:
            _cache[cache_key] = (text, time.time())
        return text
    except Exception:
        logger.exception("AI narrative generation failed")
        return None
