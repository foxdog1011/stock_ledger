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

# ── Volume enrichment via yfinance ────────────────────────────────────────────

def _try_enrich_volume(rows: list[dict], symbol: str) -> list[dict]:
    """Attempt to fill in volume from Yahoo Finance when DB has no volume data.

    Falls back silently if yfinance is not installed or the fetch fails.
    Only enriches when the majority of rows have volume == 0.
    """
    if not rows:
        return rows

    zero_count = sum(1 for r in rows if r["volume"] == 0)
    if zero_count < len(rows) * 0.8:
        # Volume data already exists in DB — no enrichment needed
        return rows

    try:
        import yfinance as yf  # optional dependency

        start = rows[0]["date"]
        end_date = rows[-1]["date"]

        # Add 5-day buffer for market closures
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start, end=end_date, auto_adjust=True)

        if hist.empty:
            return rows

        # Build date → volume lookup
        vol_map: dict[str, float] = {}
        for idx, row_hist in hist.iterrows():
            date_str = idx.strftime("%Y-%m-%d")
            vol_map[date_str] = float(row_hist.get("Volume", 0) or 0)

        enriched = []
        for r in rows:
            v = vol_map.get(r["date"], r["volume"])
            enriched.append({**r, "volume": v})
        return enriched

    except Exception:
        # Any failure — just return original rows without volume
        return rows


def _load_prices(symbol: str, days: int, as_of: Optional[str] = None) -> list[dict]:
    """Load price rows, joining volume from chip_data if available."""
    warmup = 80  # extra rows for rolling window warm-up
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        limit = days + warmup

        # Check if chip_data table exists for volume enrichment
        has_chip = bool(con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='chip_data'"
        ).fetchone())

        if has_chip:
            vol_join = "LEFT JOIN chip_data c ON c.symbol=p.symbol AND c.date=p.date"
            vol_col = "COALESCE(c.volume, 0) as volume"
        else:
            vol_join = ""
            vol_col = "0 as volume"

        base_sql = (
            f"SELECT p.date, p.close, {vol_col} FROM prices p {vol_join} "
            "WHERE p.symbol=? "
        )
        if as_of:
            rows = con.execute(
                base_sql + "AND p.date<=? ORDER BY p.date DESC LIMIT ?",
                (symbol, as_of, limit),
            ).fetchall()
        else:
            rows = con.execute(
                base_sql + "ORDER BY p.date DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()

    if not rows:
        return []

    return [{"date": r["date"], "close": float(r["close"]), "volume": float(r["volume"] or 0)}
            for r in reversed(rows)]


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
            raw_rows = _load_prices(sym, days)
            if len(raw_rows) < 25:
                continue
            rows = _try_enrich_volume(raw_rows, sym)
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

    Volume is enriched from Yahoo Finance when DB has no volume data.

    Returns:
    - `zscore_anomalies`: list of Z-score flagged dates
    - `ae_anomalies`: list of Autoencoder reconstruction-error anomalies
    - `summary`: human-readable digest
    - `latest_features`: current feature snapshot
    - `sklearn_available`: whether Autoencoder was available
    - `volume_enriched`: whether yfinance volume was used
    """
    if method not in ("zscore", "autoencoder", "both"):
        raise HTTPException(
            status_code=400,
            detail="method must be one of: zscore, autoencoder, both",
        )

    sym = symbol.upper()
    raw_rows = _load_prices(sym, days, as_of)

    if not raw_rows:
        raise HTTPException(status_code=404, detail=f"No price data for {sym}")

    if len(raw_rows) < 25:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient data: only {len(raw_rows)} rows, need at least 25",
        )

    # Enrich volume from Yahoo Finance if DB has none
    rows = _try_enrich_volume(raw_rows, sym)
    volume_enriched = rows is not raw_rows or any(
        rows[i]["volume"] != raw_rows[i]["volume"] for i in range(len(rows))
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
        "volume_enriched": volume_enriched,
        **result,
    }
