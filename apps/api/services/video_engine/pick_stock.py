"""Stock picking logic for n8n video automation slots."""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date as _date, timedelta as _td

from domain.calendar.planner import _generate_title

from apps.api.services.video_engine.models import ChipSummary, PickStockResponse

logger = logging.getLogger(__name__)

# ── Slot configuration ───────────────────────────────────────────────────────
# Slot -> (scoring_key, title_template, reason_template)

SLOT_CONFIG: dict[str, tuple[str, str, str]] = {
    "morning": (
        "foreign_net",
        "shorts",
        "外資淨買賣最大 ({value:,.0f})",
    ),
    "afternoon": (
        "abs_volume",
        "shorts",
        "法人成交量最大 ({value:,.0f})",
    ),
    "long_tuesday": (
        "momentum",
        "momentum",
        "三大法人淨買超動能最強 ({value:,.0f})",
    ),
    "long_friday": (
        "abs_volume",
        "abs_volume",
        "法人成交量最大 ({value:,.0f})",
    ),
    "sat_am": (
        "foreign_net",
        "shorts",
        "外資淨買賣最大 ({value:,.0f})",
    ),
    "sat_pm": (
        "abs_volume",
        "shorts",
        "法人成交量最大 ({value:,.0f})",
    ),
    "sun_am": (
        "momentum",
        "shorts",
        "三大法人淨買超動能最強 ({value:,.0f})",
    ),
    "sun_pm": (
        "abs_volume",
        "shorts",
        "法人成交量最大 ({value:,.0f})",
    ),
}


def score_symbols_with_fallback(
    symbols: list[str],
    max_lookback: int = 5,
) -> tuple[list[dict], str, bool]:
    """Score symbols, falling back to previous trading days if today has no data.

    Returns (scored_list, data_date, is_fallback).
    """
    for offset in range(max_lookback):
        target = _date.today() - _td(days=offset)
        target_str = target.isoformat()

        scored: list[dict] = []
        for sym in symbols:
            end = target_str
            start = (target - _td(days=15)).isoformat()
            url = f"http://localhost:8000/api/chip/{sym}/range?start={start}&end={end}"
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"Accept": "application/json"}),
                    timeout=15,
                ) as resp:
                    chip = json.loads(resp.read())
            except Exception:
                continue

            if not chip or not chip.get("daily"):
                continue

            daily = chip["daily"]

            totals = [d.get("total_net", 0) for d in daily]
            foreign = [d.get("foreign", {}).get("net", 0) for d in daily]
            trust = [d.get("investment_trust", {}).get("net", 0) for d in daily]
            dealer = [d.get("dealer", {}).get("net", 0) for d in daily]

            abs_volume = sum(abs(t) for t in totals)
            momentum = sum(totals)
            mean_total = (
                sum(totals[:-1]) / max(1, len(totals) - 1) if len(totals) > 1 else 0
            )
            reversal = abs(totals[-1] - mean_total) if totals else 0
            trust_surge = max(abs(t) for t in trust) if trust else 0

            scored.append({
                "symbol": sym,
                "abs_volume": abs_volume,
                "momentum": momentum,
                "reversal": reversal,
                "trust_surge": trust_surge,
                "foreign_net": sum(foreign),
                "trust_net": sum(trust),
                "dealer_net": sum(dealer),
                "daily": daily,
            })

        if scored:
            is_fallback = offset > 0
            return scored, target_str, is_fallback

    return [], _date.today().isoformat(), False


def build_chip_summary(pick: dict) -> ChipSummary:
    """Extract chip summary from a scored pick dict."""
    return ChipSummary(
        foreign_net=pick.get("foreign_net", 0),
        trust_net=pick.get("trust_net", 0),
        dealer_net=pick.get("dealer_net", 0),
    )


def build_pick_response(
    pick: dict,
    template_type: str,
    reason: str,
    data_date: str,
    is_fallback: bool,
) -> PickStockResponse:
    """Build a PickStockResponse from a scored pick."""
    title = _generate_title(template_type, pick["symbol"], pick)
    return PickStockResponse(
        symbol=pick["symbol"],
        title=title,
        pick_reason=reason,
        chip_summary=build_chip_summary(pick),
        data_date=data_date,
        is_holiday_fallback=is_fallback,
    )
