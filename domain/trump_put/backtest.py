from __future__ import annotations

from .historical import EVENTS
from .models import BacktestPair, BacktestResult


def compute_backtest(current_score: int = 0) -> BacktestResult:
    escalations = [e for e in EVENTS if e.event_type == "escalation"]
    reversals = [e for e in EVENTS if e.event_type == "reversal"]

    pairs: list[BacktestPair] = []
    for esc in escalations:
        next_rev = None
        for rev in reversals:
            if rev.date > esc.date:
                next_rev = rev
                break
        if next_rev is None:
            continue

        days = (next_rev.date - esc.date).days
        drawdown = None
        if esc.sp500 and next_rev.sp500:
            drawdown = round((next_rev.sp500 - esc.sp500) / esc.sp500 * 100, 2)

        pairs.append(BacktestPair(
            escalation_date=str(esc.date),
            reversal_date=str(next_rev.date),
            days=days,
            sp500_at_escalation=esc.sp500,
            sp500_at_reversal=next_rev.sp500,
            drawdown_pct=drawdown,
        ))

    avg_days = round(sum(p.days for p in pairs) / len(pairs), 1) if pairs else 0

    hit_rates: dict[str, dict] = {}
    for threshold in [40, 60, 80]:
        relevant = [p for p in pairs if p.days <= 30]
        total = len(relevant)
        hits = len(relevant)
        hit_rates[str(threshold)] = {
            "threshold": threshold,
            "total_escalations": total,
            "reversed_within_30d": hits,
            "hit_rate": round(hits / total * 100, 1) if total else 0,
            "avg_days": round(sum(p.days for p in relevant) / hits, 1) if hits else 0,
        }

    prediction = None
    if current_score >= 60 and pairs:
        fast_pairs = [p for p in pairs if p.days <= 14]
        if fast_pairs:
            avg_fast = round(sum(p.days for p in fast_pairs) / len(fast_pairs), 0)
            prediction = (
                f"Score at {current_score}: historically, reversals occurred "
                f"within ~{int(avg_fast)} days at similar pressure levels "
                f"({len(fast_pairs)}/{len(pairs)} cases)."
            )
    elif current_score >= 40:
        prediction = (
            f"Score at {current_score}: entering elevated zone. "
            f"Average escalation-to-reversal: {avg_days} days."
        )

    return BacktestResult(
        pairs=pairs,
        avg_days_to_reversal=avg_days,
        hit_rates=hit_rates,
        current_prediction=prediction,
    )


def to_json(result: BacktestResult) -> dict:
    return {
        "pairs": [
            {
                "escalation_date": p.escalation_date,
                "reversal_date": p.reversal_date,
                "days": p.days,
                "sp500_at_escalation": p.sp500_at_escalation,
                "sp500_at_reversal": p.sp500_at_reversal,
                "drawdown_pct": p.drawdown_pct,
            }
            for p in result.pairs
        ],
        "avg_days_to_reversal": result.avg_days_to_reversal,
        "hit_rates": result.hit_rates,
        "current_prediction": result.current_prediction,
    }
