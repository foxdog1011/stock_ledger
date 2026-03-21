"""Price chart + technical indicators endpoint.

Returns historical OHLCV from Yahoo Finance plus server-side computed
MA20, MA60, RSI-14, and KD (stochastic 9,3,3).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _tw_yf_ticker(symbol: str) -> str:
    if symbol.isdigit():
        return f"{symbol}.TW"
    return symbol


def _fetch_closes(symbol: str, days: int, as_of: Optional[str] = None) -> tuple[list[str], list[float]]:
    """Return (dates, closes) from Yahoo Finance in ascending order."""
    try:
        import yfinance as yf

        warmup = 80
        end = date.fromisoformat(as_of) if as_of else date.today()
        start = end - timedelta(days=days + warmup + 90)

        yf_sym = _tw_yf_ticker(symbol)
        hist = yf.Ticker(yf_sym).history(start=str(start), end=str(end), auto_adjust=True)

        if hist.empty and symbol.isdigit():
            hist = yf.Ticker(f"{symbol}.TWO").history(start=str(start), end=str(end), auto_adjust=True)

        if hist.empty:
            return [], []

        dates = [idx.strftime("%Y-%m-%d") for idx in hist.index]
        closes = [float(row["Close"]) for _, row in hist.iterrows()]

        if as_of:
            pairs = [(d, c) for d, c in zip(dates, closes) if d <= as_of]
            if pairs:
                dates, closes = zip(*pairs)  # type: ignore[assignment]
                dates, closes = list(dates), list(closes)
            else:
                return [], []

        return dates, closes

    except Exception:
        return [], []


def _moving_average(values: list[float], n: int) -> list[Optional[float]]:
    result: list[Optional[float]] = []
    for i, _ in enumerate(values):
        if i + 1 < n:
            result.append(None)
        else:
            result.append(sum(values[i + 1 - n: i + 1]) / n)
    return result


def _rsi(closes: list[float], period: int = 14) -> list[Optional[float]]:
    result: list[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return result
    gains = []
    losses = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    # First RSI uses simple average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(closes)):
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = round(100.0 - 100.0 / (1.0 + rs), 2)
        if i < len(closes) - 1:
            g = gains[i]
            lo = losses[i]
            avg_gain = (avg_gain * (period - 1) + g) / period
            avg_loss = (avg_loss * (period - 1) + lo) / period
    return result


def _kd(closes: list[float], k_period: int = 9, d_smooth: int = 3) -> tuple[list[Optional[float]], list[Optional[float]]]:
    """Stochastic KD. Uses close as both high and low approximation (single-price series)."""
    k_vals: list[Optional[float]] = []
    raw_k: list[float] = []
    for i, c in enumerate(closes):
        if i + 1 < k_period:
            k_vals.append(None)
            raw_k.append(50.0)
        else:
            window = closes[i + 1 - k_period: i + 1]
            lo = min(window)
            hi = max(window)
            if hi == lo:
                raw_k.append(50.0)
                k_vals.append(50.0)
            else:
                val = (c - lo) / (hi - lo) * 100
                raw_k.append(val)
                k_vals.append(round(val, 2))

    # D = 3-period SMA of raw_k
    d_vals: list[Optional[float]] = []
    for i in range(len(raw_k)):
        if i + 1 < k_period + d_smooth - 1:
            d_vals.append(None)
        else:
            d_vals.append(round(sum(raw_k[i + 1 - d_smooth: i + 1]) / d_smooth, 2))

    return k_vals, d_vals


@router.get("/chart/{symbol}", summary="Price history + technical indicators")
def get_chart(
    symbol: str,
    days: int = Query(120, ge=30, le=500, description="Number of calendar days of history"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD cutoff (default: today)"),
) -> dict:
    """
    Returns OHLC-equivalent (close only) price series with:
    - MA20 / MA60
    - RSI-14
    - K / D (stochastic 9,3,3)
    """
    sym = symbol.upper()
    dates, closes = _fetch_closes(sym, days, as_of)

    if not dates:
        raise HTTPException(status_code=404, detail=f"No price data for {sym}")

    ma20 = _moving_average(closes, 20)
    ma60 = _moving_average(closes, 60)
    rsi = _rsi(closes)
    k, d = _kd(closes)

    # Only return the requested window (trim warm-up)
    trim = max(0, len(dates) - days)
    result = []
    for i in range(trim, len(dates)):
        result.append({
            "date": dates[i],
            "close": closes[i],
            "ma20": ma20[i],
            "ma60": ma60[i],
            "rsi": rsi[i],
            "k": k[i],
            "d": d[i],
        })

    return {
        "symbol": sym,
        "count": len(result),
        "data": result,
    }
