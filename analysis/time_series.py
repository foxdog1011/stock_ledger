"""Feature engineering for time-series anomaly detection.

Takes a list of {date, close, volume} dicts (chronological) and returns
an enriched feature set used by anomaly_detector.py.
"""
from __future__ import annotations

import math
from typing import Optional


def _rolling_mean(values: list[float], window: int) -> list[Optional[float]]:
    result: list[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            result.append(None)
        else:
            result.append(sum(values[i + 1 - window: i + 1]) / window)
    return result


def _rolling_std(values: list[float], window: int) -> list[Optional[float]]:
    result: list[Optional[float]] = []
    for i in range(len(values)):
        if i + 1 < window:
            result.append(None)
        else:
            chunk = values[i + 1 - window: i + 1]
            mean = sum(chunk) / window
            variance = sum((x - mean) ** 2 for x in chunk) / window
            result.append(math.sqrt(variance))
    return result


def _bollinger_bands(
    closes: list[float], window: int = 20, k: float = 2.0
) -> tuple[list[Optional[float]], list[Optional[float]]]:
    means = _rolling_mean(closes, window)
    stds = _rolling_std(closes, window)
    upper = [m + k * s if m is not None else None for m, s in zip(means, stds)]
    lower = [m - k * s if m is not None else None for m, s in zip(means, stds)]
    return upper, lower


def build_features(rows: list[dict]) -> list[dict]:
    """Enrich raw price rows with derived features.

    Args:
        rows: list of dicts with at least {date, close, volume} in
              chronological order.

    Returns:
        list of dicts with additional feature columns.
    """
    closes = [float(r["close"]) for r in rows]
    volumes = [float(r.get("volume") or 0) for r in rows]

    ma5 = _rolling_mean(closes, 5)
    ma20 = _rolling_mean(closes, 20)
    vol_ma20 = _rolling_mean(volumes, 20)
    std20 = _rolling_std(closes, 20)
    upper_bb, lower_bb = _bollinger_bands(closes)

    result = []
    for i, row in enumerate(rows):
        c = closes[i]
        v = volumes[i]

        pct_change = (c / closes[i - 1] - 1) if i > 0 else 0.0

        vol_ratio = (v / vol_ma20[i]) if (vol_ma20[i] and vol_ma20[i] > 0) else None

        # Distance from MA20 in standard deviations (z-score vs rolling window)
        zscore_20 = None
        if ma20[i] is not None and std20[i] and std20[i] > 0:
            zscore_20 = (c - ma20[i]) / std20[i]

        # Bollinger band position: 0 = lower band, 1 = upper band
        bb_pct = None
        if upper_bb[i] is not None and lower_bb[i] is not None:
            band_width = upper_bb[i] - lower_bb[i]
            if band_width and band_width > 0:
                bb_pct = (c - lower_bb[i]) / band_width

        # Volatility: 5-day rolling std of pct_change (approximate)
        volatility_5 = None
        if i >= 5:
            recent_changes = [
                (closes[j] / closes[j - 1] - 1) for j in range(i - 4, i + 1)
            ]
            mean_rc = sum(recent_changes) / 5
            volatility_5 = math.sqrt(
                sum((x - mean_rc) ** 2 for x in recent_changes) / 5
            )

        result.append({
            "date": row["date"],
            "close": c,
            "volume": v,
            "ma5": ma5[i],
            "ma20": ma20[i],
            "vol_ma20": vol_ma20[i],
            "price_change_pct": round(pct_change * 100, 4),
            "volume_ratio": round(vol_ratio, 4) if vol_ratio is not None else None,
            "zscore_20": round(zscore_20, 4) if zscore_20 is not None else None,
            "bb_pct": round(bb_pct, 4) if bb_pct is not None else None,
            "volatility_5": round(volatility_5 * 100, 4) if volatility_5 is not None else None,
            "upper_bb": upper_bb[i],
            "lower_bb": lower_bb[i],
        })

    return result
