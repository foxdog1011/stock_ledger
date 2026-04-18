from __future__ import annotations

from datetime import date

from .models import HistoricalEvent

EVENTS: list[HistoricalEvent] = [
    HistoricalEvent(date(2025, 1, 20), 6049.0, 4.58,
                    "Trump inauguration; tariff threats begin", "marker"),
    HistoricalEvent(date(2025, 2, 1), 6040.0, 4.54,
                    "25% tariffs on Canada/Mexico announced", "escalation"),
    HistoricalEvent(date(2025, 2, 4), 5994.0, 4.49,
                    "Canada/Mexico tariffs paused 1 month after market drop", "reversal"),
    HistoricalEvent(date(2025, 3, 4), 5778.0, 4.24,
                    "25% tariffs on Canada/Mexico take effect", "escalation"),
    HistoricalEvent(date(2025, 4, 2), 5670.0, 4.20,
                    "Liberation Day: sweeping reciprocal tariffs announced", "escalation"),
    HistoricalEvent(date(2025, 4, 4), 5074.0, 3.99,
                    "S&P crashes ~10% in 2 days; VIX closes 45.31", "marker"),
    HistoricalEvent(date(2025, 4, 7), 5062.0, 4.22,
                    "S&P intraday low ~5,062; VIX hits 60 intraday", "marker"),
    HistoricalEvent(date(2025, 4, 8), 5120.0, 4.50,
                    "10Y yield spikes to 4.5%; bond market stress", "marker"),
    HistoricalEvent(date(2025, 4, 9), 5457.0, 4.34,
                    "90-day tariff pause (except China); S&P +9.52%. "
                    "Bessent warned Trump about bond market.", "reversal"),
    HistoricalEvent(date(2025, 4, 14), 5450.0, 4.38,
                    "Electronics/smartphones exempted from tariffs", "reversal"),
    HistoricalEvent(date(2025, 6, 27), 6173.0, None,
                    "S&P recovers all Liberation Day losses; new ATH", "marker"),
    HistoricalEvent(date(2026, 1, 28), 7002.0, None,
                    "S&P first touches 7,000 intraday", "marker"),
    HistoricalEvent(date(2026, 2, 1), None, None,
                    "Supreme Court strikes down most IEEPA-based tariffs (6-3)",
                    "reversal"),
    # ── Iran War (2026) ──
    HistoricalEvent(date(2026, 2, 28), 7000.0, None,
                    "Operation Epic Fury: US-Israeli strikes on Iran (after market close). "
                    "Trump escalated from S&P ATH.", "escalation"),
    HistoricalEvent(date(2026, 3, 5), None, None,
                    "Strait of Hormuz closure; Brent oil +15% to $83", "escalation"),
    HistoricalEvent(date(2026, 3, 17), None, None,
                    "Trump admits markets influenced Iran strike decision, "
                    "citing 'record equity prices' as opening", "marker"),
    HistoricalEvent(date(2026, 3, 23), None, None,
                    "Trump postpones strikes via Truth Social minutes before market open; "
                    "S&P +1.15%. Suspicious $500M oil futures placed 15 min prior.",
                    "reversal"),
    HistoricalEvent(date(2026, 3, 27), None, 4.46,
                    "Worst quarter since 2022; 10Y yield hits 4.46%", "marker"),
    HistoricalEvent(date(2026, 3, 31), None, None,
                    "Iran signals willingness to end war; S&P +2.9%, "
                    "oil -16% to $94", "reversal"),
    HistoricalEvent(date(2026, 4, 7), None, None,
                    "Ceasefire announced; markets rally", "reversal"),
    HistoricalEvent(date(2026, 4, 15), 7023.0, 4.28,
                    "S&P reclaims 7,003; Trump says war 'very close to over', "
                    "'stock market is going to boom'", "marker"),
]


def get_nearby_events(sp500: float | None = None,
                      tnx: float | None = None,
                      limit: int = 5) -> list[HistoricalEvent]:
    if sp500 is None:
        return EVENTS[-limit:]

    scored: list[tuple[float, HistoricalEvent]] = []
    for ev in EVENTS:
        if ev.sp500 is None:
            scored.append((9999, ev))
            continue
        scored.append((abs(ev.sp500 - sp500), ev))

    scored.sort(key=lambda x: x[0])
    return [ev for _, ev in scored[:limit]]
