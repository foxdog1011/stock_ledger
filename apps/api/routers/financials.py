"""Financial statements, valuation metrics, dividends & TDCC endpoints.

Fetches from FinMind API and stores in local SQLite tables.
Datasets used:
- TaiwanStockFinancialStatements (income/balance/cashflow)
- TaiwanStockPER (P/E, P/B, dividend yield)
- TaiwanStockDividend (dividend history)
- TaiwanStockHoldingSharesPerDay (TDCC shareholder distribution)
"""
from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
import urllib.request
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import DB_PATH

router = APIRouter()

_FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


# ── FinMind fetch helper ─────────────────────────────────────────────────────

def _fetch_finmind(dataset: str, symbol: str, start_date: str = "2020-01-01") -> list[dict]:
    """Generic FinMind fetch. Raises ValueError on failure."""
    token = os.getenv("FINMIND_TOKEN", "").strip()
    params: dict = {
        "dataset": dataset,
        "data_id": symbol,
        "start_date": start_date,
    }
    if token:
        params["token"] = token

    url = f"{_FINMIND_URL}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise ValueError(f"FinMind request failed: {exc}") from exc

    if data.get("status") != 200:
        raise ValueError(f"FinMind error: {data.get('msg', 'unknown')}")

    return data.get("data", [])


# ── Financial Statements Endpoints ───────────────────────────────────────────

@router.get("/financials/{symbol}", summary="Get financial statements")
def get_financials(
    symbol: str,
    type: str = Query("income", description="income|balance|cashflow"),
    limit: int = Query(20, ge=1, le=60),
) -> dict:
    """Return stored financial statement data for a symbol."""
    from domain.financials.repository import get_financial_statements
    sym = symbol.upper()
    result = get_financial_statements(DB_PATH, sym, type, limit)
    return {"symbol": sym, "statement_type": type, "count": len(result), "data": result}


@router.post("/financials/{symbol}/fetch", summary="Fetch financial statements from FinMind")
def fetch_financials(
    symbol: str,
    start_date: str = Query("2020-01-01", description="Start date YYYY-MM-DD"),
) -> dict:
    """Fetch income statement, balance sheet, and cash flow from FinMind."""
    from domain.financials.repository import store_financial_rows
    sym = symbol.upper()
    totals = {}

    dataset_map = {
        "income": "TaiwanStockFinancialStatements",
        "balance": "TaiwanStockBalanceSheet",
        "cashflow": "TaiwanStockCashFlowsStatement",
    }

    for stmt_type, dataset in dataset_map.items():
        try:
            rows = _fetch_finmind(dataset, sym, start_date)
            inserted = store_financial_rows(DB_PATH, sym, stmt_type, rows)
            totals[stmt_type] = {"fetched": len(rows), "stored": inserted}
        except ValueError as exc:
            totals[stmt_type] = {"error": str(exc)}

    if all("error" in v for v in totals.values()):
        raise HTTPException(status_code=502, detail=f"All FinMind fetches failed: {totals}")

    return {"symbol": sym, "results": totals}


# ── Valuation Metrics Endpoints ──────────────────────────────────────────────

@router.get("/valuation/{symbol}", summary="Get valuation metrics (PER/PBR)")
def get_valuation(
    symbol: str,
    limit: int = Query(60, ge=1, le=365),
) -> dict:
    """Return stored PER/PBR/DividendYield for a symbol."""
    from domain.financials.repository import get_valuation_metrics
    sym = symbol.upper()
    data = get_valuation_metrics(DB_PATH, sym, limit)
    if not data:
        return {"symbol": sym, "count": 0, "data": [], "summary": None}

    # Compute summary stats
    pers = [d["per"] for d in data if d["per"] is not None and d["per"] > 0]
    pbrs = [d["pbr"] for d in data if d["pbr"] is not None and d["pbr"] > 0]

    summary = {
        "latest_per": data[0]["per"] if data else None,
        "latest_pbr": data[0]["pbr"] if data else None,
        "latest_dividend_yield": data[0]["dividend_yield"] if data else None,
        "per_avg": round(sum(pers) / len(pers), 2) if pers else None,
        "per_min": round(min(pers), 2) if pers else None,
        "per_max": round(max(pers), 2) if pers else None,
        "pbr_avg": round(sum(pbrs) / len(pbrs), 2) if pbrs else None,
        "pbr_min": round(min(pbrs), 2) if pbrs else None,
        "pbr_max": round(max(pbrs), 2) if pbrs else None,
    }

    return {"symbol": sym, "count": len(data), "data": data, "summary": summary}


@router.post("/valuation/{symbol}/fetch", summary="Fetch PER/PBR from FinMind")
def fetch_valuation(
    symbol: str,
    start_date: str = Query("2020-01-01", description="Start date YYYY-MM-DD"),
) -> dict:
    """Fetch PER/PBR/DividendYield from FinMind TaiwanStockPER dataset."""
    from domain.financials.repository import store_valuation_rows
    sym = symbol.upper()
    try:
        rows = _fetch_finmind("TaiwanStockPER", sym, start_date)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not rows:
        raise HTTPException(status_code=404, detail=f"No PER/PBR data for {sym}")

    inserted = store_valuation_rows(DB_PATH, sym, rows)
    return {"symbol": sym, "fetched": len(rows), "stored": inserted}


# ── Dividend Endpoints ───────────────────────────────────────────────────────

@router.get("/dividends/{symbol}", summary="Get dividend history")
def get_dividends(
    symbol: str,
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    """Return stored dividend history for a symbol."""
    from domain.financials.repository import get_dividend_history
    sym = symbol.upper()
    data = get_dividend_history(DB_PATH, sym, limit)

    # Compute summary
    total_cash = sum(d["cash_dividend"] or 0 for d in data)
    total_stock = sum(d["stock_dividend"] or 0 for d in data)

    return {
        "symbol": sym,
        "count": len(data),
        "data": data,
        "summary": {
            "total_cash_dividend": round(total_cash, 2),
            "total_stock_dividend": round(total_stock, 2),
            "years_covered": len(data),
        },
    }


@router.post("/dividends/{symbol}/fetch", summary="Fetch dividend history from FinMind")
def fetch_dividends(
    symbol: str,
    start_date: str = Query("2015-01-01", description="Start date YYYY-MM-DD"),
) -> dict:
    """Fetch dividend data from FinMind TaiwanStockDividend dataset."""
    from domain.financials.repository import store_dividend_rows
    sym = symbol.upper()
    try:
        rows = _fetch_finmind("TaiwanStockDividend", sym, start_date)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not rows:
        raise HTTPException(status_code=404, detail=f"No dividend data for {sym}")

    inserted = store_dividend_rows(DB_PATH, sym, rows)
    return {"symbol": sym, "fetched": len(rows), "stored": inserted}


# ── TDCC Endpoints ───────────────────────────────────────────────────────────

@router.get("/tdcc/{symbol}", summary="Get TDCC shareholder distribution")
def get_tdcc(
    symbol: str,
    dates: int = Query(1, ge=1, le=10, description="Number of latest dates"),
) -> dict:
    """Return TDCC shareholding distribution data."""
    from domain.financials.repository import get_tdcc_distribution
    sym = symbol.upper()
    data = get_tdcc_distribution(DB_PATH, sym, dates)
    return {"symbol": sym, "count": len(data), "data": data}


@router.post("/tdcc/{symbol}/fetch", summary="Fetch TDCC data from FinMind")
def fetch_tdcc(
    symbol: str,
    start_date: str = Query("2024-01-01", description="Start date YYYY-MM-DD"),
) -> dict:
    """Fetch TDCC shareholding distribution from FinMind."""
    from domain.financials.repository import store_tdcc_rows
    sym = symbol.upper()
    try:
        rows = _fetch_finmind("TaiwanStockHoldingSharesPerDay", sym, start_date)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not rows:
        raise HTTPException(status_code=404, detail=f"No TDCC data for {sym}")

    inserted = store_tdcc_rows(DB_PATH, sym, rows)
    return {"symbol": sym, "fetched": len(rows), "stored": inserted}


# ── Peer Comparison Endpoint ─────────────────────────────────────────────────

@router.get("/peers/{symbol}", summary="Peer comparison by industry")
def get_peers(
    symbol: str,
    limit: int = Query(10, ge=1, le=30),
) -> dict:
    """Compare a stock against industry peers using research + valuation data."""
    sym = symbol.upper()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        # 1. Get the target company's industry
        target = conn.execute(
            "SELECT ticker, name, sector, industry, market_cap, ev "
            "FROM research_companies WHERE ticker = ?",
            (sym,),
        ).fetchone()

        if not target:
            raise HTTPException(status_code=404, detail=f"Company {sym} not found in research DB")

        industry = target["industry"]

        # 2. Get all peers in same industry
        peers = conn.execute(
            "SELECT ticker, name, sector, industry, market_cap, ev "
            "FROM research_companies WHERE industry = ? ORDER BY market_cap DESC LIMIT ?",
            (industry, limit + 1),
        ).fetchall()

        # 3. For each peer, fetch latest valuation & revenue if available
        peer_data = []
        for p in peers:
            ticker = p["ticker"]
            entry = dict(p)

            # Latest valuation
            val = conn.execute(
                "SELECT per, pbr, dividend_yield FROM valuation_metrics "
                "WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            entry["per"] = val["per"] if val else None
            entry["pbr"] = val["pbr"] if val else None
            entry["dividend_yield"] = val["dividend_yield"] if val else None

            # Latest revenue YoY (table may not exist yet)
            try:
                rev = conn.execute(
                    "SELECT revenue, yoy_pct FROM monthly_revenue "
                    "WHERE symbol = ? ORDER BY year_month DESC LIMIT 1",
                    (ticker,),
                ).fetchone()
                entry["latest_revenue"] = rev["revenue"] if rev else None
                entry["revenue_yoy_pct"] = rev["yoy_pct"] if rev else None
            except sqlite3.OperationalError:
                entry["latest_revenue"] = None
                entry["revenue_yoy_pct"] = None

            # Mark if this is the target
            entry["is_target"] = ticker == sym

            peer_data.append(entry)

        # 4. Compute industry averages
        pers = [p["per"] for p in peer_data if p["per"] and p["per"] > 0]
        pbrs = [p["pbr"] for p in peer_data if p["pbr"] and p["pbr"] > 0]
        yoys = [p["revenue_yoy_pct"] for p in peer_data if p["revenue_yoy_pct"] is not None]

        industry_avg = {
            "per_avg": round(sum(pers) / len(pers), 2) if pers else None,
            "pbr_avg": round(sum(pbrs) / len(pbrs), 2) if pbrs else None,
            "revenue_yoy_avg": round(sum(yoys) / len(yoys), 2) if yoys else None,
        }

        return {
            "symbol": sym,
            "industry": industry,
            "peer_count": len(peer_data),
            "industry_averages": industry_avg,
            "peers": peer_data,
        }
    finally:
        conn.close()


# ── Batch Fetch (All-in-One) ─────────────────────────────────────────────────

@router.post("/fundamentals/{symbol}/fetch-all", summary="Fetch all fundamental data for a symbol")
def fetch_all_fundamentals(
    symbol: str,
    start_date: str = Query("2020-01-01", description="Start date YYYY-MM-DD"),
) -> dict:
    """One-click fetch: financial statements + PER/PBR + dividends + TDCC."""
    from domain.financials.repository import (
        store_financial_rows,
        store_valuation_rows,
        store_dividend_rows,
        store_tdcc_rows,
    )
    sym = symbol.upper()
    results = {}

    # Financial statements
    for stmt_type, dataset in [
        ("income", "TaiwanStockFinancialStatements"),
        ("balance", "TaiwanStockBalanceSheet"),
        ("cashflow", "TaiwanStockCashFlowsStatement"),
    ]:
        try:
            rows = _fetch_finmind(dataset, sym, start_date)
            stored = store_financial_rows(DB_PATH, sym, stmt_type, rows)
            results[stmt_type] = {"fetched": len(rows), "stored": stored}
        except ValueError as exc:
            results[stmt_type] = {"error": str(exc)}

    # PER/PBR
    try:
        rows = _fetch_finmind("TaiwanStockPER", sym, start_date)
        stored = store_valuation_rows(DB_PATH, sym, rows)
        results["valuation"] = {"fetched": len(rows), "stored": stored}
    except ValueError as exc:
        results["valuation"] = {"error": str(exc)}

    # Dividends
    try:
        rows = _fetch_finmind("TaiwanStockDividend", sym, "2015-01-01")
        stored = store_dividend_rows(DB_PATH, sym, rows)
        results["dividends"] = {"fetched": len(rows), "stored": stored}
    except ValueError as exc:
        results["dividends"] = {"error": str(exc)}

    # TDCC
    try:
        rows = _fetch_finmind("TaiwanStockHoldingSharesPerDay", sym, "2024-01-01")
        stored = store_tdcc_rows(DB_PATH, sym, rows)
        results["tdcc"] = {"fetched": len(rows), "stored": stored}
    except ValueError as exc:
        results["tdcc"] = {"error": str(exc)}

    return {"symbol": sym, "results": results}
