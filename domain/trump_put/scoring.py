from __future__ import annotations

import logging
import math

from .models import TrumpPutReport

logger = logging.getLogger(__name__)

WEIGHTS = {
    "sp500": 0.30,
    "tnx": 0.25,
    "vix": 0.15,
    "dxy": 0.15,
    "approval": 0.15,
}

LABELS = [
    (0, 20, "Dormant"),
    (21, 40, "Watchful"),
    (41, 60, "Elevated"),
    (61, 80, "High Alert"),
    (81, 100, "Activated"),
]

_ROLLING_WINDOW = 252  # trading days in one year


def _label_for_score(score: int) -> str:
    for lo, hi, lbl in LABELS:
        if lo <= score <= hi:
            return lbl
    return "Unknown"


def compute_composite(**scores: int | None) -> tuple[int, str]:
    parts = {k: v for k, v in scores.items() if v is not None and k in WEIGHTS}
    if not parts:
        return (0, "No Data")

    total_weight = sum(WEIGHTS[k] for k in parts)
    raw = sum(parts[k] * WEIGHTS[k] for k in parts) / total_weight
    score = min(100, max(0, round(raw)))

    return (score, _label_for_score(score))


def rolling_z_score(
    values: list[float],
    window: int = _ROLLING_WINDOW,
) -> float | None:
    """Compute the Z-score of the last value relative to a rolling window.

    Returns None if fewer than 2 data points are available in the window.
    """
    if len(values) < 2:
        return None

    # Use last `window` values (or all if fewer available)
    series = values[-window:]
    n = len(series)
    current = series[-1]

    mean = sum(series) / n
    variance = sum((x - mean) ** 2 for x in series) / n
    std = math.sqrt(variance)

    if std < 1e-10:
        return 0.0

    return (current - mean) / std


def compute_rolling_z_composite(
    indicator_histories: dict[str, list[float]],
) -> tuple[int, str] | None:
    """Compute a composite score using rolling Z-scores across indicators.

    Each indicator's Z-score is mapped to a 0-100 scale and weighted.
    Returns (score, label) or None if insufficient data.

    Z-score mapping (absolute value, higher = more stress):
      0.0-0.5 -> 0-15   (normal)
      0.5-1.0 -> 15-35  (mild)
      1.0-1.5 -> 35-55  (elevated)
      1.5-2.0 -> 55-75  (high)
      2.0-3.0 -> 75-90  (extreme)
      3.0+    -> 90-100  (crisis)
    """
    z_scores: dict[str, float] = {}

    for indicator, history in indicator_histories.items():
        if indicator not in WEIGHTS:
            continue
        z = rolling_z_score(history)
        if z is not None:
            z_scores[indicator] = z

    if not z_scores:
        return None

    def _z_to_score(z: float, indicator: str) -> int:
        """Map Z-score to 0-100. For S&P, negative Z = stress. For others, positive Z = stress."""
        # S&P falling is bad (negative Z = stress), others rising is bad (positive Z = stress)
        stress_z = -z if indicator == "sp500" else z
        # Approval falling is bad (negative Z = stress)
        if indicator == "approval":
            stress_z = -z

        abs_z = max(0.0, stress_z)  # only care about stress direction

        if abs_z < 0.5:
            return round(abs_z / 0.5 * 15)
        if abs_z < 1.0:
            return round(15 + (abs_z - 0.5) / 0.5 * 20)
        if abs_z < 1.5:
            return round(35 + (abs_z - 1.0) / 0.5 * 20)
        if abs_z < 2.0:
            return round(55 + (abs_z - 1.5) / 0.5 * 20)
        if abs_z < 3.0:
            return round(75 + (abs_z - 2.0) / 1.0 * 15)
        return min(100, round(90 + (abs_z - 3.0) / 1.0 * 10))

    total_weight = sum(WEIGHTS[k] for k in z_scores)
    weighted_sum = sum(
        _z_to_score(z, k) * WEIGHTS[k] for k, z in z_scores.items()
    )
    score = min(100, max(0, round(weighted_sum / total_weight)))

    return (score, _label_for_score(score))


def generate_narrative(report: TrumpPutReport) -> str:
    parts: list[str] = []

    if report.sp500:
        parts.append(f"S&P 500 at {report.sp500.value:,.2f} ({report.sp500.zone})")
    if report.tnx:
        parts.append(f"10Y yield at {report.tnx.value:.3f}% ({report.tnx.zone})")
    if report.vix:
        parts.append(f"VIX at {report.vix.value:.2f} ({report.vix.zone})")
    if report.dxy:
        parts.append(f"DXY at {report.dxy.value:.2f} ({report.dxy.zone})")
    if report.approval:
        parts.append(f"Approval at {report.approval.value:.1f}% ({report.approval.zone})")

    indicator_text = "; ".join(parts) if parts else "No market data available"

    if report.composite_score >= 80:
        outlook = "Trump Put is near activation — policy reversal historically imminent at these levels."
    elif report.composite_score >= 60:
        outlook = "Approaching pain thresholds. Bond market stress would likely trigger policy softening."
    elif report.composite_score >= 40:
        outlook = "Elevated but not critical. Markets are weakening; watch 10Y yield closely."
    elif report.composite_score >= 20:
        outlook = "Markets under mild pressure but well above crisis levels."
    else:
        outlook = "Markets calm. Trump Put is dormant — no policy pressure expected."

    return f"{indicator_text}. {outlook}"
