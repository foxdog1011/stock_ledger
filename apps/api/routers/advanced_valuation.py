"""Advanced valuation endpoints: DCF model, P/E Band, Beta, MOPS news.

Phase 3 features for institutional-grade research.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import DB_PATH
from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


# ══════════════════════════════════════════════════════════════════════════════
# 1. DCF (Discounted Cash Flow) Model
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/dcf/{symbol}", summary="DCF valuation model")
def dcf_valuation(
    symbol: str,
    wacc: float = Query(0.09, ge=0.01, le=0.30, description="Weighted avg cost of capital"),
    terminal_growth: float = Query(0.02, ge=0.0, le=0.05, description="Terminal growth rate"),
    projection_years: int = Query(5, ge=3, le=10, description="Projection period"),
    fcf_growth_rate: float = Query(None, description="Override FCF growth rate (auto-detect if None)"),
) -> dict:
    """
    Simple DCF model based on historical free cash flow.

    Uses latest available FCF from financial statements, projects forward,
    and discounts back to present value. Returns implied share price.
    """
    sym = symbol.upper()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        # Get historical operating cash flow and capex
        ocf_rows = conn.execute(
            """SELECT date, value FROM financial_statements
               WHERE symbol=? AND type='cashflow'
               AND origin_name LIKE '%營業活動%'
               ORDER BY date DESC LIMIT 5""",
            (sym,),
        ).fetchall()

        # Try to get shares outstanding from market cap + price
        company = conn.execute(
            "SELECT market_cap FROM research_companies WHERE ticker=?", (sym,),
        ).fetchone()

        latest_price_row = conn.execute(
            "SELECT per, pbr FROM valuation_metrics WHERE symbol=? AND pbr > 0 ORDER BY date DESC LIMIT 1",
            (sym,),
        ).fetchone()

        # Get net debt (total debt - cash) from balance sheet
        debt_row = conn.execute(
            """SELECT date, origin_name, value FROM financial_statements
               WHERE symbol=? AND type='balance'
               AND (origin_name LIKE '%負債%' OR origin_name LIKE '%現金%' OR origin_name LIKE '%約當現金%')
               ORDER BY date DESC LIMIT 20""",
            (sym,),
        ).fetchall()

    finally:
        conn.close()

    if not ocf_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No cash flow data for {sym}. Run POST /api/financials/{sym}/fetch first.",
        )

    # Extract FCF values (OCF as proxy since capex breakdown varies)
    fcf_values = [r["value"] for r in ocf_rows if r["value"] is not None]
    if not fcf_values:
        raise HTTPException(status_code=404, detail=f"No valid FCF data for {sym}")

    latest_fcf = fcf_values[0]

    # Auto-detect growth rate from historical data
    if fcf_growth_rate is None:
        if len(fcf_values) >= 2 and fcf_values[-1] != 0:
            n = len(fcf_values) - 1
            if fcf_values[-1] > 0 and latest_fcf > 0:
                fcf_growth_rate = (latest_fcf / fcf_values[-1]) ** (1 / n) - 1
            else:
                fcf_growth_rate = 0.05  # default 5%
        else:
            fcf_growth_rate = 0.05

    # Cap growth rate at reasonable bounds
    fcf_growth_rate = max(-0.1, min(0.3, fcf_growth_rate))

    # Project FCF
    projected_fcf = []
    for year in range(1, projection_years + 1):
        fcf = latest_fcf * (1 + fcf_growth_rate) ** year
        pv = fcf / (1 + wacc) ** year
        projected_fcf.append({
            "year": year,
            "fcf": round(fcf / 1e6, 2),  # in millions
            "pv": round(pv / 1e6, 2),
        })

    # Terminal value
    terminal_fcf = latest_fcf * (1 + fcf_growth_rate) ** projection_years * (1 + terminal_growth)
    terminal_value = terminal_fcf / (wacc - terminal_growth) if wacc > terminal_growth else 0
    pv_terminal = terminal_value / (1 + wacc) ** projection_years

    # Enterprise value
    pv_fcf_sum = sum(p["pv"] for p in projected_fcf) * 1e6
    enterprise_value = pv_fcf_sum + pv_terminal

    # Estimate shares outstanding from market cap
    shares_outstanding = None
    equity_value = enterprise_value  # simplified (no net debt adjustment for now)
    implied_price = None

    if company and company["market_cap"]:
        market_cap_ntd = company["market_cap"] * 1e6  # market_cap is in millions
        # Get a recent price to estimate shares
        try:
            import yfinance as yf
            ticker = f"{sym}.TW" if sym.isdigit() else sym
            hist = yf.Ticker(ticker).history(period="5d")
            if hist.empty and sym.isdigit():
                hist = yf.Ticker(f"{sym}.TWO").history(period="5d")
            if not hist.empty:
                recent_price = float(hist["Close"].iloc[-1])
                shares_outstanding = market_cap_ntd / recent_price
                implied_price = round(equity_value / shares_outstanding, 2) if shares_outstanding else None
        except Exception:
            pass

    # Parse net debt from balance sheet
    net_debt = None
    if debt_row:
        latest_date = debt_row[0]["date"]
        total_liab = sum(r["value"] or 0 for r in debt_row if r["date"] == latest_date and "負債" in r["origin_name"] and "總" in r["origin_name"])
        cash = sum(r["value"] or 0 for r in debt_row if r["date"] == latest_date and ("現金" in r["origin_name"] or "約當" in r["origin_name"]))
        if total_liab > 0:
            net_debt = total_liab - cash

    return {
        "symbol": sym,
        "model": "DCF",
        "assumptions": {
            "wacc": wacc,
            "terminal_growth": terminal_growth,
            "fcf_growth_rate": round(fcf_growth_rate, 4),
            "projection_years": projection_years,
            "latest_fcf_millions": round(latest_fcf / 1e6, 2),
        },
        "projected_fcf": projected_fcf,
        "terminal_value_millions": round(terminal_value / 1e6, 2),
        "pv_terminal_millions": round(pv_terminal / 1e6, 2),
        "enterprise_value_millions": round(enterprise_value / 1e6, 2),
        "net_debt_millions": round(net_debt / 1e6, 2) if net_debt else None,
        "shares_outstanding": round(shares_outstanding) if shares_outstanding else None,
        "implied_share_price": implied_price,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. P/E Band (河流圖 data)
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/pe-band/{symbol}", summary="P/E Band (河流圖) data")
def pe_band(
    symbol: str,
    years: int = Query(5, ge=1, le=10, description="Years of history"),
) -> dict:
    """
    Generate P/E Band (河流圖) data.

    Returns historical price overlaid with P/E band lines computed from
    trailing EPS × historical P/E percentiles (cheap/fair/expensive).
    """
    sym = symbol.upper()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        # Get historical PER data
        start_date = (date.today() - timedelta(days=years * 365)).isoformat()
        per_rows = conn.execute(
            """SELECT date, per, pbr FROM valuation_metrics
               WHERE symbol=? AND date >= ? AND per > 0
               ORDER BY date""",
            (sym, start_date),
        ).fetchall()

        if not per_rows:
            raise HTTPException(
                status_code=404,
                detail=f"No PER data for {sym}. Run POST /api/valuation/{sym}/fetch first.",
            )

        # Get EPS data from financial statements
        eps_rows = conn.execute(
            """SELECT date, value FROM financial_statements
               WHERE symbol=? AND type='income' AND origin_name LIKE '%每股盈餘%'
               ORDER BY date DESC""",
            (sym,),
        ).fetchall()

    finally:
        conn.close()

    # Compute PER percentiles
    pers = [r["per"] for r in per_rows if r["per"] and r["per"] > 0]
    if not pers:
        raise HTTPException(status_code=404, detail=f"Insufficient PER data for {sym}")

    pers_sorted = sorted(pers)
    n = len(pers_sorted)

    def percentile(p: float) -> float:
        idx = p * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return pers_sorted[lo] * (1 - frac) + pers_sorted[hi] * frac

    bands = {
        "p10_cheap": round(percentile(0.10), 2),
        "p25_undervalued": round(percentile(0.25), 2),
        "p50_fair": round(percentile(0.50), 2),
        "p75_overvalued": round(percentile(0.75), 2),
        "p90_expensive": round(percentile(0.90), 2),
    }

    # Build trailing 4Q EPS by date
    eps_by_quarter = {}
    for r in eps_rows:
        eps_by_quarter[r["date"]] = r["value"]

    # Get the latest trailing 4Q EPS
    quarterly_eps = sorted(eps_by_quarter.items(), reverse=True)
    trailing_eps = None
    if len(quarterly_eps) >= 4:
        trailing_eps = sum(v for _, v in quarterly_eps[:4] if v)
    elif quarterly_eps:
        trailing_eps = quarterly_eps[0][1] * 4 if quarterly_eps[0][1] else None

    # Generate band price lines using trailing EPS
    band_prices = None
    if trailing_eps and trailing_eps > 0:
        band_prices = {
            k: round(v * trailing_eps, 2)
            for k, v in bands.items()
        }

    # Time series data with actual PER
    time_series = []
    for r in per_rows:
        entry = {"date": r["date"], "per": r["per"]}
        if r["per"] and trailing_eps and trailing_eps > 0:
            entry["implied_price"] = round(r["per"] * trailing_eps, 2)
        time_series.append(entry)

    # Sample to max 250 points for performance
    if len(time_series) > 250:
        step = len(time_series) // 250
        time_series = time_series[::step]

    return {
        "symbol": sym,
        "years": years,
        "data_points": len(time_series),
        "trailing_eps": round(trailing_eps, 2) if trailing_eps else None,
        "per_bands": bands,
        "band_prices": band_prices,
        "per_stats": {
            "mean": round(sum(pers) / len(pers), 2),
            "median": round(percentile(0.50), 2),
            "std": round((sum((p - sum(pers) / len(pers)) ** 2 for p in pers) / len(pers)) ** 0.5, 2),
            "current": pers_sorted[-1] if pers_sorted else None,
        },
        "time_series": time_series,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 3. Beta Coefficient
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/beta/{symbol}", summary="Calculate Beta coefficient")
def calculate_beta(
    symbol: str,
    bench: str = Query("0050", description="Benchmark symbol (e.g., 0050, TAIEX)"),
    days: int = Query(252, ge=60, le=756, description="Trading days for calculation"),
) -> dict:
    """
    Calculate Beta coefficient vs a benchmark.

    Beta = Cov(stock, benchmark) / Var(benchmark)
    Uses daily returns from Yahoo Finance.
    """
    sym = symbol.upper()

    try:
        import yfinance as yf

        end = date.today()
        start = end - timedelta(days=int(days * 1.5))  # extra buffer for non-trading days

        # Stock data
        stock_ticker = f"{sym}.TW" if sym.isdigit() else sym
        stock_hist = yf.Ticker(stock_ticker).history(start=str(start), end=str(end))
        if stock_hist.empty and sym.isdigit():
            stock_hist = yf.Ticker(f"{sym}.TWO").history(start=str(start), end=str(end))

        # Benchmark data
        bench_map = {
            "0050": "0050.TW", "TAIEX": "^TWII", "SPY": "SPY",
            "0056": "0056.TW", "006208": "006208.TW",
        }
        bench_yf = bench_map.get(bench, f"{bench}.TW" if bench.isdigit() else bench)
        bench_hist = yf.Ticker(bench_yf).history(start=str(start), end=str(end))

        if stock_hist.empty or bench_hist.empty:
            raise HTTPException(status_code=404, detail=f"Insufficient price data for {sym} or {bench}")

        # Compute daily returns
        stock_returns = stock_hist["Close"].pct_change().dropna()
        bench_returns = bench_hist["Close"].pct_change().dropna()

        # Align dates
        common = stock_returns.index.intersection(bench_returns.index)
        if len(common) < 30:
            raise HTTPException(status_code=404, detail="Insufficient overlapping trading days")

        sr = stock_returns.loc[common].values
        br = bench_returns.loc[common].values

        # Beta = Cov(s, b) / Var(b)
        cov = sum((s - sum(sr) / len(sr)) * (b - sum(br) / len(br)) for s, b in zip(sr, br)) / len(sr)
        var_b = sum((b - sum(br) / len(br)) ** 2 for b in br) / len(br)
        beta = cov / var_b if var_b > 0 else None

        # Alpha (Jensen's alpha, annualized)
        avg_stock = sum(sr) / len(sr) * 252
        avg_bench = sum(br) / len(br) * 252
        alpha = avg_stock - beta * avg_bench if beta else None

        # Correlation
        std_s = (sum((s - sum(sr) / len(sr)) ** 2 for s in sr) / len(sr)) ** 0.5
        std_b = var_b ** 0.5
        correlation = cov / (std_s * std_b) if std_s > 0 and std_b > 0 else None

        # R-squared
        r_squared = correlation ** 2 if correlation else None

        return {
            "symbol": sym,
            "benchmark": bench,
            "trading_days": len(common),
            "beta": round(beta, 4) if beta else None,
            "alpha_annualized": round(alpha, 4) if alpha else None,
            "correlation": round(correlation, 4) if correlation else None,
            "r_squared": round(r_squared, 4) if r_squared else None,
            "interpretation": _interpret_beta(beta) if beta else None,
        }

    except ImportError:
        raise HTTPException(status_code=500, detail="yfinance not installed")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error calculating beta: {exc}")


def _interpret_beta(beta: float) -> str:
    if beta > 1.5:
        return "高度波動，遠超市場風險"
    elif beta > 1.0:
        return "波動性高於市場"
    elif beta > 0.8:
        return "與市場波動相近"
    elif beta > 0.5:
        return "波動性低於市場，偏防禦型"
    else:
        return "極低波動，高度防禦型"


# ══════════════════════════════════════════════════════════════════════════════
# 4. MOPS 重大訊息 (Material Information)
# ══════════════════════════════════════════════════════════════════════════════

def _ensure_mops_table() -> None:
    """Create mops_news table if not exists."""
    with sqlite3.connect(str(DB_PATH)) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS mops_news (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT NOT NULL,
                date        TEXT NOT NULL,
                title       TEXT NOT NULL,
                url         TEXT,
                fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(symbol, date, title)
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_mops_symbol ON mops_news(symbol)")
        con.commit()


def _fetch_mops_news(symbol: str) -> list[dict]:
    """Fetch material information from MOPS (公開資訊觀測站).

    Uses the MOPS Ajax endpoint for 重大訊息.
    """
    url = "https://mops.twse.com.tw/mops/web/ajax_t05st01"
    data = urllib.parse.urlencode({
        "encodeURIComponent": 1,
        "step": 1,
        "firstin": 1,
        "off": 1,
        "keyword4": "",
        "code1": "",
        "TYPEK2": "",
        "checkbtn": "",
        "queryName": "co_id",
        "inpuType": "co_id",
        "TYPEK": "all",
        "co_id": symbol,
    }).encode()

    try:
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://mops.twse.com.tw/mops/web/t05st01",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise ValueError(f"MOPS request failed: {exc}") from exc

    # Parse HTML table (simple regex extraction)
    import re
    results = []
    # Find table rows with date and title
    row_pattern = re.compile(
        r"<td[^>]*>\s*(\d{3}/\d{2}/\d{2})\s*</td>"  # ROC date
        r".*?<td[^>]*>(.*?)</td>",  # title
        re.DOTALL,
    )

    for match in row_pattern.finditer(html):
        roc_date = match.group(1).strip()
        title = re.sub(r"<[^>]+>", "", match.group(2)).strip()
        if not title:
            continue

        # Convert ROC date to ISO
        parts = roc_date.split("/")
        if len(parts) == 3:
            try:
                y = int(parts[0]) + 1911
                iso_date = f"{y}-{parts[1]}-{parts[2]}"
            except ValueError:
                continue
        else:
            continue

        results.append({"date": iso_date, "title": title})

    return results[:50]  # limit to 50 most recent


@router.get("/mops/{symbol}", summary="Get MOPS material information")
def get_mops_news(
    symbol: str,
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    """Return stored MOPS material information for a symbol."""
    _ensure_mops_table()
    sym = symbol.upper()
    with sqlite3.connect(str(DB_PATH)) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            "SELECT date, title, url FROM mops_news WHERE symbol=? ORDER BY date DESC LIMIT ?",
            (sym, limit),
        ).fetchall()
    return {"symbol": sym, "count": len(rows), "data": [dict(r) for r in rows]}


@router.post("/mops/{symbol}/fetch", summary="Fetch MOPS material information")
def fetch_mops_news(symbol: str) -> dict:
    """Fetch latest material information from MOPS (公開資訊觀測站)."""
    _ensure_mops_table()
    sym = symbol.upper()

    try:
        news = _fetch_mops_news(sym)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not news:
        return {"symbol": sym, "fetched": 0, "message": "No material information found"}

    inserted = 0
    with sqlite3.connect(str(DB_PATH)) as con:
        for item in news:
            try:
                con.execute(
                    "INSERT OR IGNORE INTO mops_news (symbol, date, title) VALUES (?,?,?)",
                    (sym, item["date"], item["title"]),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass
        con.commit()

    return {"symbol": sym, "fetched": len(news), "new_stored": inserted, "sample": news[:3]}


# ══════════════════════════════════════════════════════════════════════════════
# 5. Dividend Yield + Payout Analysis
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/dividend-analysis/{symbol}", summary="Dividend yield & payout analysis")
def dividend_analysis(
    symbol: str,
) -> dict:
    """
    Comprehensive dividend analysis: yield history, payout ratio, growth rate.
    """
    sym = symbol.upper()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    try:
        # Dividend history
        divs = conn.execute(
            "SELECT date, cash_dividend, stock_dividend FROM dividend_history "
            "WHERE symbol=? ORDER BY date DESC",
            (sym,),
        ).fetchall()

        if not divs:
            raise HTTPException(status_code=404, detail=f"No dividend data for {sym}")

        # EPS history for payout ratio
        eps_rows = conn.execute(
            """SELECT date, value FROM financial_statements
               WHERE symbol=? AND type='income' AND origin_name LIKE '%每股盈餘%'
               ORDER BY date DESC LIMIT 8""",
            (sym,),
        ).fetchall()

        # Latest price for yield calculation
        val = conn.execute(
            "SELECT date, per, pbr FROM valuation_metrics WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (sym,),
        ).fetchone()

    finally:
        conn.close()

    div_data = [dict(d) for d in divs]
    cash_divs = [d["cash_dividend"] or 0 for d in div_data]

    # Growth rate
    growth_rate = None
    if len(cash_divs) >= 2 and cash_divs[-1] > 0 and cash_divs[0] > 0:
        n = len(cash_divs) - 1
        growth_rate = round(((cash_divs[0] / cash_divs[-1]) ** (1 / n) - 1) * 100, 2)

    # Payout ratio (latest cash dividend / trailing EPS)
    payout_ratio = None
    if eps_rows and cash_divs:
        trailing_eps = sum(r["value"] or 0 for r in eps_rows[:4])
        if trailing_eps > 0:
            payout_ratio = round(cash_divs[0] / trailing_eps * 100, 2)

    return {
        "symbol": sym,
        "dividends": div_data,
        "summary": {
            "years_of_data": len(div_data),
            "latest_cash_dividend": cash_divs[0] if cash_divs else None,
            "avg_cash_dividend": round(sum(cash_divs) / len(cash_divs), 2) if cash_divs else None,
            "dividend_growth_cagr_pct": growth_rate,
            "payout_ratio_pct": payout_ratio,
        },
    }
