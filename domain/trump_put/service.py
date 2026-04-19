from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from .models import IndicatorReading, TrumpPutReport
from . import fetcher, thresholds, scoring, historical, approval, ai_narrative, discord_alert, backtest

logger = logging.getLogger(__name__)

_TAIPEI = timezone(timedelta(hours=8))

_INDICATORS = [
    ("sp500", "S&P 500"),
    ("tnx", "10Y Treasury"),
    ("vix", "VIX"),
    ("dxy", "US Dollar Index"),
]

_prev_score: int | None = None


def _fetch_indicator_history(indicator: str) -> list[float]:
    """Fetch historical closing prices for rolling Z-score computation."""
    try:
        history = fetcher.fetch_history(indicator, period="1y")
        return [entry["close"] for entry in history if "close" in entry]
    except Exception:
        logger.debug("Failed to fetch history for %s", indicator, exc_info=True)
        return []


def generate_report() -> TrumpPutReport:
    global _prev_score

    data = fetcher.fetch_all()

    readings: dict[str, IndicatorReading | None] = {
        "sp500": None, "tnx": None, "vix": None, "dxy": None, "approval": None,
    }

    for key, display in _INDICATORS:
        pair = data.get(key)
        if pair is None:
            continue
        value, as_of = pair
        zone, score = thresholds.classify(key, value)
        readings[key] = IndicatorReading(
            symbol=key, name=display,
            value=value, as_of=as_of,
            zone=zone, score=score,
        )

    approval_pair = approval.fetch()
    if approval_pair:
        value, as_of = approval_pair
        zone, score = thresholds.classify("approval", value)
        readings["approval"] = IndicatorReading(
            symbol="approval", name="Trump Approval",
            value=value, as_of=as_of,
            zone=zone, score=score,
        )

    # Fetch new data sources (credit spread and trade-weighted USD)
    extra_data = fetcher.fetch_credit_and_usd()
    credit_reading: IndicatorReading | None = None
    twexb_reading: IndicatorReading | None = None

    if "credit_spread" in extra_data:
        value, as_of = extra_data["credit_spread"]
        zone, score = thresholds.classify("credit_spread", value)
        credit_reading = IndicatorReading(
            symbol="credit_spread", name="HY Credit Spread",
            value=value, as_of=as_of,
            zone=zone, score=score,
        )

    if "twexb" in extra_data:
        value, as_of = extra_data["twexb"]
        zone, score = thresholds.classify("twexb", value)
        twexb_reading = IndicatorReading(
            symbol="twexb", name="Trade Weighted USD",
            value=value, as_of=as_of,
            zone=zone, score=score,
        )

    scores = {k: r.score for k, r in readings.items() if r is not None}
    comp_score, comp_label = scoring.compute_composite(**scores)

    # Compute rolling Z-score composite from historical data
    rolling_z: tuple[int, str] | None = None
    try:
        indicator_histories: dict[str, list[float]] = {}
        for key in ("sp500", "tnx", "vix", "dxy"):
            history = _fetch_indicator_history(key)
            if history:
                indicator_histories[key] = history
        if indicator_histories:
            rolling_z = scoring.compute_rolling_z_composite(indicator_histories)
    except Exception:
        logger.debug("Rolling Z-score computation failed", exc_info=True)

    sp500_val = readings["sp500"].value if readings["sp500"] else None
    nearby = historical.get_nearby_events(sp500=sp500_val, limit=5)

    bt = backtest.compute_backtest(comp_score)
    bt_json = backtest.to_json(bt)

    report = TrumpPutReport(
        timestamp=datetime.now(_TAIPEI),
        sp500=readings["sp500"],
        tnx=readings["tnx"],
        vix=readings["vix"],
        dxy=readings["dxy"],
        approval=readings["approval"],
        composite_score=comp_score,
        composite_label=comp_label,
        narrative="",
        nearby_events=nearby,
        thresholds=thresholds.get_all_thresholds(),
        backtest=bt_json,
        rolling_z_composite=rolling_z,
        credit_spread=credit_reading,
        twexb=twexb_reading,
    )

    narrative = ai_narrative.generate(report) or scoring.generate_narrative(report)

    report = TrumpPutReport(
        timestamp=report.timestamp,
        sp500=report.sp500,
        tnx=report.tnx,
        vix=report.vix,
        dxy=report.dxy,
        approval=report.approval,
        composite_score=report.composite_score,
        composite_label=report.composite_label,
        narrative=narrative,
        nearby_events=report.nearby_events,
        thresholds=report.thresholds,
        backtest=report.backtest,
        rolling_z_composite=report.rolling_z_composite,
        credit_spread=report.credit_spread,
        twexb=report.twexb,
    )

    if discord_alert.should_alert(comp_score, _prev_score):
        discord_alert.send_alert_async(report)
    _prev_score = comp_score

    return report
