from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class IndicatorReading:
    symbol: str
    name: str
    value: float
    as_of: str
    zone: str
    score: int  # 0-100 component score


@dataclass(frozen=True)
class HistoricalEvent:
    date: date
    sp500: float | None
    tnx: float | None
    description: str
    event_type: str  # "reversal" | "escalation" | "marker"


@dataclass(frozen=True)
class TrumpPutReport:
    timestamp: datetime
    sp500: IndicatorReading | None
    tnx: IndicatorReading | None
    vix: IndicatorReading | None
    dxy: IndicatorReading | None
    approval: IndicatorReading | None
    composite_score: int  # 0-100
    composite_label: str
    narrative: str
    nearby_events: list[HistoricalEvent]
    thresholds: dict[str, list[dict]]
    backtest: dict | None = None


@dataclass(frozen=True)
class BacktestPair:
    escalation_date: str
    reversal_date: str
    days: int
    sp500_at_escalation: float | None
    sp500_at_reversal: float | None
    drawdown_pct: float | None


@dataclass(frozen=True)
class BacktestResult:
    pairs: list[BacktestPair]
    avg_days_to_reversal: float
    hit_rates: dict[str, dict]
    current_prediction: str | None
