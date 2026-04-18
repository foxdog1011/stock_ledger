from __future__ import annotations

from .models import TrumpPutReport

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


def compute_composite(**scores: int | None) -> tuple[int, str]:
    parts = {k: v for k, v in scores.items() if v is not None and k in WEIGHTS}
    if not parts:
        return (0, "No Data")

    total_weight = sum(WEIGHTS[k] for k in parts)
    raw = sum(parts[k] * WEIGHTS[k] for k in parts) / total_weight
    score = min(100, max(0, round(raw)))

    label = "Unknown"
    for lo, hi, lbl in LABELS:
        if lo <= score <= hi:
            label = lbl
            break

    return (score, label)


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
