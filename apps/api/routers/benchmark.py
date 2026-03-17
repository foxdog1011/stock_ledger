"""Benchmark comparison + bootstrap endpoints.

Uses the `prices` table as the benchmark data source.
Bootstrap fetches historical data from Yahoo Finance chart API
(no API key required) and stores it in the prices table.
"""
from __future__ import annotations

import datetime
import json
import math
import sqlite3
import urllib.request
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_ledger
from ledger import StockLedger
from ledger.equity import equity_curve as _portfolio_curve

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

_VALID_FREQS = {"D", "W", "ME", "QE", "YE"}
# Approximate trading periods per year for each frequency
_ANN = {"D": 252, "W": 52, "ME": 12, "QE": 4, "YE": 1}

# Default benchmarks available for bootstrap
_DEFAULT_BENCHES = ["0050", "TAIEX"]

# Map from benchmark ticker (stored in DB) → Yahoo Finance symbol
_YAHOO_MAP: dict[str, str] = {
    "0050":  "0050.TW",
    "0051":  "0051.TW",
    "0056":  "0056.TW",
    "006208": "006208.TW",
    "TAIEX": "^TWII",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    ),
    "Accept": "application/json",
}


# ── Bootstrap log table ────────────────────────────────────────────────────────

def _ensure_bootstrap_log(db_path: str) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS benchmark_bootstrap_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at      TEXT NOT NULL DEFAULT (datetime('now')),
                provider    TEXT,
                start_date  TEXT,
                end_date    TEXT,
                inserted    INTEGER DEFAULT 0,
                skipped     INTEGER DEFAULT 0,
                errors_count INTEGER DEFAULT 0,
                message     TEXT
            )
        """)
        conn.commit()


def _log_bootstrap(
    db_path: str,
    provider: str,
    start_date: str,
    end_date: str,
    inserted: int,
    skipped: int,
    errors_count: int,
    message: str,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO benchmark_bootstrap_log"
            " (provider, start_date, end_date, inserted, skipped, errors_count, message)"
            " VALUES (?,?,?,?,?,?,?)",
            (provider, start_date, end_date, inserted, skipped, errors_count, message),
        )
        conn.commit()


# ── Yahoo Finance historical fetch ─────────────────────────────────────────────

def _yahoo_history(
    bench: str,
    start: str,
    end: str,
) -> list[tuple[str, float]]:
    """
    Fetch daily OHLCV from Yahoo Finance chart API for [start, end].

    Returns list of (date_str, close) tuples, sorted ascending.
    """
    yahoo_sym = _YAHOO_MAP.get(bench, bench)

    # Convert dates to Unix timestamps
    dt_start = datetime.datetime.strptime(start, "%Y-%m-%d")
    dt_end   = datetime.datetime.strptime(end,   "%Y-%m-%d") + datetime.timedelta(days=1)
    p1 = int(dt_start.timestamp())
    p2 = int(dt_end.timestamp())

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}"
        f"?interval=1d&period1={p1}&period2={p2}"
    )

    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(f"Yahoo Finance request failed for {yahoo_sym}: {exc}") from exc

    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(
            f"Unexpected Yahoo Finance response format for {yahoo_sym}"
        ) from exc

    if not timestamps:
        return []

    pairs: list[tuple[str, float]] = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        date_str = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d")
        if start <= date_str <= end:
            pairs.append((date_str, float(close)))

    return sorted(pairs, key=lambda x: x[0])


def _upsert_prices(
    db_path: str,
    bench: str,
    pairs: list[tuple[str, float]],
) -> tuple[int, int]:
    """Insert or skip (date, symbol, close) rows. Returns (inserted, skipped)."""
    inserted = 0
    skipped = 0
    with sqlite3.connect(db_path) as conn:
        for date_str, close in pairs:
            existing = conn.execute(
                "SELECT 1 FROM prices WHERE date=? AND symbol=?",
                (date_str, bench),
            ).fetchone()
            if existing:
                skipped += 1
            else:
                conn.execute(
                    "INSERT INTO prices (date, symbol, close) VALUES (?,?,?)",
                    (date_str, bench, close),
                )
                inserted += 1
        conn.commit()
    return inserted, skipped


# ── Comparison helpers (shared with series/compare endpoints) ──────────────────

def _fetch_prices(ledger: StockLedger, bench: str, start: str, end: str) -> pd.Series:
    """Return a daily pd.Series of closing prices for *bench* in [start, end]."""
    db_path = str(ledger.db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT date, close FROM prices"
            " WHERE symbol=? AND date BETWEEN ? AND ? ORDER BY date",
            (bench, start, end),
        ).fetchall()
    if not rows:
        return pd.Series(dtype=float, name="close")
    dates, closes = zip(*rows)
    return pd.Series(list(closes), index=pd.to_datetime(list(dates)), name="close")


def _last_quote_date(ledger: StockLedger, bench: str) -> str | None:
    db_path = str(ledger.db_path)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT MAX(date) FROM prices WHERE symbol=?", (bench,)
        ).fetchone()
    return row[0] if row else None


def _resample(s: pd.Series, freq: str) -> pd.Series:
    if s.empty:
        return s
    return s.resample(freq).last().dropna()


def _nan_to_none(v: float) -> Optional[float]:
    """Return None for NaN/±inf; otherwise round to 4 dp."""
    f = float(v)
    return None if not math.isfinite(f) else round(f, 4)


# ── Request schemas ────────────────────────────────────────────────────────────

class BootstrapIn(BaseModel):
    benches: list[str] = _DEFAULT_BENCHES
    start: str = "2016-01-01"
    end: Optional[str] = None       # defaults to today
    provider: str = "yahoo"         # only "yahoo" implemented; placeholder for future


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/bootstrap", summary="Bootstrap historical benchmark price data")
def benchmark_bootstrap(
    body: BootstrapIn = BootstrapIn(),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Fetch historical daily closing prices for each benchmark ticker from
    Yahoo Finance and store them in the `prices` table.

    Supported tickers (mapped to Yahoo Finance symbols automatically):

    | Ticker  | Yahoo symbol |
    |---------|--------------|
    | 0050    | 0050.TW      |
    | TAIEX   | ^TWII        |
    | SPY     | SPY          |
    | QQQ     | QQQ          |
    | (other) | passed as-is |

    Existing rows are **skipped** (not overwritten), so re-running is safe.
    """
    db_path = str(ledger.db_path)
    _ensure_bootstrap_log(db_path)

    today = datetime.date.today().isoformat()
    end_date = body.end or today

    total_inserted = 0
    total_skipped  = 0
    errors: list[dict] = []

    for bench in body.benches:
        try:
            pairs = _yahoo_history(bench, body.start, end_date)
            ins, skip = _upsert_prices(db_path, bench, pairs)
            total_inserted += ins
            total_skipped  += skip
        except Exception as exc:
            errors.append({"bench": bench, "message": str(exc)})

    msg = (
        f"Bootstrap complete: {total_inserted} inserted, "
        f"{total_skipped} skipped, {len(errors)} error(s)."
    )
    _log_bootstrap(
        db_path,
        provider=body.provider,
        start_date=body.start,
        end_date=end_date,
        inserted=total_inserted,
        skipped=total_skipped,
        errors_count=len(errors),
        message=msg,
    )

    return {
        "benches": body.benches,
        "start": body.start,
        "end": end_date,
        "provider": body.provider,
        "inserted": total_inserted,
        "skipped": total_skipped,
        "errors": errors,
    }


@router.get("/bootstrap/status", summary="Last benchmark bootstrap run")
def bootstrap_status(
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """Return the most recent benchmark bootstrap log entry."""
    db_path = str(ledger.db_path)
    _ensure_bootstrap_log(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM benchmark_bootstrap_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row:
        return {
            "last_run_at": None,
            "provider": None,
            "from": None,
            "to": None,
            "inserted": None,
            "skipped": None,
            "errors_count": None,
        }
    return {
        "last_run_at": row["run_at"],
        "provider":    row["provider"],
        "from":        row["start_date"],
        "to":          row["end_date"],
        "inserted":    row["inserted"],
        "skipped":     row["skipped"],
        "errors_count": row["errors_count"],
    }


@router.get("/series", summary="Benchmark price & cumulative return series")
def benchmark_series(
    bench: str = Query(..., description="Benchmark ticker stored in prices table, e.g. 0050 or SPY"),
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
    freq:  str = Query("ME", description="Pandas offset: D | W | ME | QE | YE"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Return benchmark price series resampled to *freq*, with cumulative return %.

    ```json
    {
      "bench": "0050",
      "records": [{"date": "2024-01-31", "close": 145.2, "cum_return_pct": 0.0}, ...],
      "missing_days": 0,
      "last_quote_date": "2024-12-31"
    }
    ```
    """
    if freq not in _VALID_FREQS:
        raise HTTPException(
            status_code=422,
            detail=f"freq must be one of {sorted(_VALID_FREQS)}, got '{freq}'",
        )

    raw = _fetch_prices(ledger, bench, start, end)
    last_qd = _last_quote_date(ledger, bench)

    if raw.empty:
        return {
            "bench": bench, "freq": freq, "start": start, "end": end,
            "records": [], "missing_days": None, "last_quote_date": last_qd,
        }

    resampled = _resample(raw, freq)
    cum_ret = (resampled / resampled.iloc[0] - 1) * 100

    expected = pd.date_range(start=start, end=end, freq=freq)
    missing_days = int((~expected.isin(resampled.index)).sum())

    records = [
        {
            "date": _ts_to_date_str(ts),
            "close": round(float(p), 4),
            "cum_return_pct": _nan_to_none(float(c)),
        }
        for ts, p, c in zip(resampled.index, resampled, cum_ret)
    ]

    return {
        "bench": bench, "freq": freq, "start": start, "end": end,
        "records": records,
        "missing_days": missing_days,
        "last_quote_date": last_qd,
    }


def _ts_to_date_str(ts: object) -> str:
    """Convert pd.Timestamp or datetime.date to 'YYYY-MM-DD' string safely."""
    s = str(ts)
    return s[:10]


@router.get("/compare", summary="Portfolio vs benchmark cumulative return comparison")
def benchmark_compare(
    bench: str = Query(..., description="Benchmark ticker"),
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
    freq:  str = Query("ME", description="D | W | ME | QE | YE"),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Align portfolio equity curve with benchmark series and compute comparison metrics.

    **records** — aligned date series with:
    - `portfolio_cum_return_pct`
    - `bench_cum_return_pct`
    - `excess_cum_return_pct`  (portfolio − benchmark)

    **metrics** — scalar statistics:
    - `excess_return_pct`          — cumulative excess return at end date
    - `tracking_error_annualized`  — std of per-period excess returns × √(ann factor)
    - `correlation`                — Pearson correlation of per-period returns
    - `information_ratio`          — annualised mean excess return / tracking error
    """
    if freq not in _VALID_FREQS:
        raise HTTPException(
            status_code=422,
            detail=f"freq must be one of {sorted(_VALID_FREQS)}, got '{freq}'",
        )

    try:
        port_df = _portfolio_curve(ledger, start=start, end=end, freq=freq)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Portfolio curve error: {exc}")

    _empty = {"bench": bench, "freq": freq, "start": start, "end": end,
              "records": [], "metrics": None, "detail": None}

    if port_df.empty:
        return {**_empty, "detail": "No portfolio equity data in range"}

    # equity_curve() returns datetime.date index; normalize to pd.Timestamp
    # so it aligns correctly with the benchmark Series (which uses pd.Timestamp).
    port_df.index = pd.to_datetime(port_df.index)

    # Auto-trim to first date where total_equity > 0.
    # This handles the common case of querying from e.g. 2016 when trades
    # only started in 2024: equity is 0 before the first deposit/trade,
    # making cum_return_pct NaN/inf for those early dates.
    valid_mask = port_df["total_equity"] > 0
    if not valid_mask.any():
        return {**_empty, "detail": "Portfolio has no equity (all zero) in requested range"}
    first_valid = port_df.index[valid_mask][0]
    port_df = port_df[port_df.index >= first_valid].copy()

    # Recompute cum_return_pct from the first valid date (starts at 0%).
    base_equity = port_df["total_equity"].iloc[0]
    if base_equity == 0:
        return {**_empty, "detail": "Portfolio starting equity is zero"}
    port_df["cum_return_pct"] = (port_df["total_equity"] / base_equity - 1) * 100

    raw = _fetch_prices(ledger, bench, start, end)
    if raw.empty:
        return {**_empty, "detail": f"No price data for '{bench}' in range — run bootstrap first"}

    bench_rs = _resample(raw, freq)
    if bench_rs.empty:
        return {**_empty, "detail": f"Benchmark '{bench}' resampled series is empty"}

    # Rebase benchmark to the same start date as the portfolio (first_valid).
    # Without this, benchmark cum_return_pct reflects gains since 2016
    # while the portfolio only starts in e.g. 2024 — making comparison meaningless.
    bench_rs_aligned = bench_rs[bench_rs.index >= first_valid]
    if bench_rs_aligned.empty:
        return {**_empty, "detail": f"No benchmark data for '{bench}' on or after {_ts_to_date_str(first_valid)}"}

    base_bench = bench_rs_aligned.iloc[0]
    if base_bench == 0:
        return {**_empty, "detail": f"Benchmark '{bench}' price is zero at portfolio start date"}

    bench_cum = (bench_rs_aligned / base_bench - 1) * 100

    port_cum = port_df["cum_return_pct"]
    aligned  = pd.DataFrame({"portfolio": port_cum, "bench": bench_cum}).dropna()

    if aligned.empty:
        return {**_empty, "detail": "No overlapping dates between portfolio and benchmark"}

    aligned["excess"] = aligned["portfolio"] - aligned["bench"]

    records = [
        {
            "date": _ts_to_date_str(ts),
            "portfolio_cum_return_pct": _nan_to_none(float(p)),
            "bench_cum_return_pct":     _nan_to_none(float(b)),
            "excess_cum_return_pct":    _nan_to_none(float(e)),
        }
        for ts, p, b, e in zip(
            aligned.index, aligned["portfolio"], aligned["bench"], aligned["excess"]
        )
    ]

    # ── Metrics (fully guarded — never raises) ─────────────────────────────────
    ann = _ANN.get(freq, 252)
    excess_return_pct:         float | None = None
    tracking_error_annualized: float | None = None
    correlation:               float | None = None
    information_ratio:         float | None = None

    try:
        excess_return_pct = _nan_to_none(float(aligned["excess"].iloc[-1]))
    except Exception:
        pass

    try:
        # Derive period returns from equity / aligned-benchmark price levels.
        # Using pct_change on the rebased series avoids inf from pre-portfolio era.
        port_period  = port_df["total_equity"].pct_change().dropna() * 100
        port_period  = port_period[port_period.apply(lambda x: math.isfinite(float(x)))]
        bench_period = bench_rs_aligned.pct_change().dropna() * 100
        period_df    = pd.DataFrame({"p": port_period, "b": bench_period}).dropna()

        if len(period_df) >= 2:
            excess_periods = period_df["p"] - period_df["b"]

            te_raw = excess_periods.std()
            if te_raw is not None and not math.isnan(float(te_raw)):
                te = float(te_raw) * math.sqrt(ann)
                tracking_error_annualized = round(te, 4) if not math.isnan(te) else None

            corr_raw = period_df["p"].corr(period_df["b"])
            if corr_raw is not None and not math.isnan(float(corr_raw)):
                correlation = round(float(corr_raw), 4)

            if tracking_error_annualized and tracking_error_annualized > 0:
                mean_excess_ann = float(excess_periods.mean()) * ann
                if not math.isnan(mean_excess_ann):
                    information_ratio = round(
                        mean_excess_ann / tracking_error_annualized, 4
                    )
    except Exception:
        pass  # metrics stay None — records are still returned

    metrics = {
        "excess_return_pct":         excess_return_pct,
        "tracking_error_annualized": tracking_error_annualized,
        "correlation":               correlation,
        "information_ratio":         information_ratio,
    }

    return {
        "bench": bench, "freq": freq, "start": start, "end": end,
        "records": records, "metrics": metrics, "detail": None,
    }
