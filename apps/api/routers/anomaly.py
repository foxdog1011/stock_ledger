"""Time-series anomaly detection endpoint.

GET /api/anomaly/{symbol}
  - method: zscore | autoencoder | both (default: both)
  - days: lookback window (default 120)
  - zscore_threshold: default 2.5
  - ae_threshold: PCA Autoencoder std-deviation threshold (default 2.5)
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import DB_PATH
from analysis.anomaly_detector import detect_anomalies


router = APIRouter()


def _tw_yf_ticker(symbol: str) -> str:
    """Convert a Taiwan stock symbol to Yahoo Finance ticker format."""
    if symbol.isdigit():
        return f"{symbol}.TW"
    return symbol


def _fetch_yfinance_history(symbol: str, days: int) -> list[dict]:
    """Fetch historical OHLCV from Yahoo Finance.

    Supports US stocks and Taiwan stocks (.TW/.TWO suffix appended automatically).
    Returns rows in ascending date order, never raises.
    """
    try:
        import yfinance as yf
        from datetime import date, timedelta

        yf_sym = _tw_yf_ticker(symbol)
        end = date.today()
        start = end - timedelta(days=days + 90)  # buffer for weekends/holidays

        ticker = yf.Ticker(yf_sym)
        hist = ticker.history(start=str(start), end=str(end), auto_adjust=True)

        # Fallback to .TWO for OTC-listed stocks
        if hist.empty and symbol.isdigit():
            ticker = yf.Ticker(f"{symbol}.TWO")
            hist = ticker.history(start=str(start), end=str(end), auto_adjust=True)

        if hist.empty:
            return []

        rows = []
        for idx, row in hist.iterrows():
            rows.append({
                "date": idx.strftime("%Y-%m-%d"),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume", 0) or 0),
            })
        # Return only the requested window
        return rows[-days:] if len(rows) > days else rows

    except Exception:
        return []


def _load_prices(symbol: str, days: int, as_of: Optional[str] = None) -> list[dict]:
    """Fetch price history for anomaly detection directly from Yahoo Finance.

    Yahoo Finance covers both US stocks and Taiwan stocks (appends .TW/.TWO
    automatically), so we no longer depend on the local DB having historical
    data backfilled.  The as_of parameter filters results to a specific date
    cutoff for back-testing scenarios.
    """
    warmup = 80  # extra rows for rolling window warm-up
    rows = _fetch_yfinance_history(symbol, days + warmup)

    if as_of and rows:
        rows = [r for r in rows if r["date"] <= as_of]

    return rows


def _active_position_symbols() -> list[str]:
    """Return symbols with qty > 0 from current positions."""
    with sqlite3.connect(DB_PATH) as con:
        rows = con.execute(
            "SELECT DISTINCT symbol FROM trades WHERE side='buy' "
            "EXCEPT SELECT DISTINCT symbol FROM trades WHERE side='sell' "
            "AND qty >= (SELECT COALESCE(SUM(qty),0) FROM trades t2 WHERE t2.symbol=trades.symbol AND t2.side='buy')"
        ).fetchall()
        # Simpler approach: get symbols that have net qty > 0
        rows = con.execute(
            "SELECT symbol, "
            "SUM(CASE WHEN side='buy' THEN qty ELSE -qty END) as net_qty "
            "FROM trades WHERE is_void=0 GROUP BY symbol HAVING net_qty > 0"
        ).fetchall()
    return [r[0] for r in rows]


@router.get("/anomaly/batch", summary="Batch scan all active positions for anomalies")
def get_anomaly_batch(
    days: int = Query(120, ge=20, le=500),
    zscore_threshold: float = Query(2.5, ge=1.0, le=5.0),
    ae_threshold: float = Query(2.5, ge=1.0, le=5.0),
) -> dict:
    """
    Scan all currently held positions for anomalies.

    Returns a compact summary suitable for the positions page badges
    and the overview dashboard widget.
    """
    symbols = _active_position_symbols()
    results = []

    for sym in symbols:
        try:
            rows = _load_prices(sym, days)
            if len(rows) < 25:
                continue
            result = detect_anomalies(
                rows=rows,
                method="both",
                zscore_threshold=zscore_threshold,
                ae_threshold=ae_threshold,
                lookback=days,
            )
            all_anomalies = result["zscore_anomalies"] + result["ae_anomalies"]
            if not all_anomalies:
                continue

            # Most recent anomaly
            latest = max(all_anomalies, key=lambda x: x["date"])
            has_high = any(a["severity"] == "high" for a in all_anomalies)

            results.append({
                "symbol": sym,
                "anomaly_count": len(all_anomalies),
                "has_high_severity": has_high,
                "latest_date": latest["date"],
                "latest_reason": latest["reason"],
                "latest_severity": latest["severity"],
                "zscore_count": len(result["zscore_anomalies"]),
                "ae_count": len(result["ae_anomalies"]),
            })
        except Exception:
            continue

    results.sort(key=lambda x: (x["has_high_severity"], x["anomaly_count"]), reverse=True)

    return {
        "scanned": len(symbols),
        "with_anomalies": len(results),
        "results": results,
    }


@router.get("/anomaly/{symbol}", summary="Time-series anomaly detection")
def get_anomaly(
    symbol: str,
    days: int = Query(120, ge=20, le=500, description="Lookback window in calendar days"),
    method: str = Query("both", description="zscore | autoencoder | both"),
    zscore_threshold: float = Query(2.5, ge=1.0, le=5.0, description="Z-score threshold"),
    ae_threshold: float = Query(2.5, ge=1.0, le=5.0, description="Autoencoder RE threshold (std devs above mean)"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD cutoff (default: today)"),
) -> dict:
    """
    Detect price/volume anomalies using Z-score and/or PCA Autoencoder.

    **Method 1 — Z-score (rolling 20-day):**
    Flags when close price deviates > `zscore_threshold` σ from the 20-day mean.

    **Method 2 — PCA Autoencoder (reconstruction error, data-driven threshold):**
    Compresses 6 features (close, volume_ratio, price_change_pct, volatility_5,
    zscore_20, bb_pct) to 2 principal components and reconstructs. Points where
    reconstruction error > mean(RE) + ae_threshold * std(RE) are flagged.
    No fixed contamination ratio — threshold adapts to the actual data distribution.
    Requires scikit-learn (gracefully disabled if not installed).

    Price and volume data is fetched directly from Yahoo Finance (supports both
    US stocks and Taiwan stocks via .TW/.TWO suffix).

    Returns:
    - `zscore_anomalies`: list of Z-score flagged dates
    - `ae_anomalies`: list of Autoencoder reconstruction-error anomalies
    - `summary`: human-readable digest
    - `latest_features`: current feature snapshot
    - `sklearn_available`: whether Autoencoder was available
    """
    if method not in ("zscore", "autoencoder", "both"):
        raise HTTPException(
            status_code=400,
            detail="method must be one of: zscore, autoencoder, both",
        )

    sym = symbol.upper()
    rows = _load_prices(sym, days, as_of)

    if not rows:
        raise HTTPException(status_code=404, detail=f"No price data for {sym}")

    if len(rows) < 25:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data: only {len(rows)} rows, need at least 25",
        )

    result = detect_anomalies(
        rows=rows,
        method=method,
        zscore_threshold=zscore_threshold,
        ae_threshold=ae_threshold,
        lookback=days,
    )

    return {
        "symbol": sym,
        "days": days,
        "method": method,
        "total_rows": len(rows),
        **result,
    }
