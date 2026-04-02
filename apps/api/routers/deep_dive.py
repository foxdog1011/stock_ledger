"""Stock Deep Dive aggregator endpoint.

GET /api/deep-dive/{symbol}
    Aggregates company profile, supply chain, position, watchlist, price,
    revenue, institutional flow, margin trading, anomalies and catalysts
    into a single response for the deep-dive page.

GET /api/deep-dive/{symbol}/ai-analysis
    Sends the aggregated data to an AI model (Claude or OpenAI) and returns
    a structured investment analysis JSON.
"""
from __future__ import annotations

import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter

from ..config import DB_PATH

router = APIRouter()


# ── DB connection helper ───────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


# ── Section fetchers ───────────────────────────────────────────────────────────

def _fetch_company(symbol: str) -> Optional[dict]:
    """Fetch company profile from research_companies table."""
    try:
        with _connect() as con:
            row = con.execute(
                "SELECT ticker, name, sector, industry, market_cap, ev, description "
                "FROM research_companies WHERE ticker = ? LIMIT 1",
                (symbol,),
            ).fetchone()
        if not row:
            return None
        return {
            "ticker": row["ticker"],
            "name": row["name"],
            "sector": row["sector"],
            "industry": row["industry"],
            "market_cap": row["market_cap"],
            "ev": row["ev"],
            "description": row["description"],
        }
    except Exception:
        return None


def _fetch_themes(symbol: str) -> list[str]:
    """Fetch investment themes for the symbol."""
    try:
        with _connect() as con:
            rows = con.execute(
                "SELECT theme FROM research_themes WHERE ticker = ? ORDER BY theme",
                (symbol,),
            ).fetchall()
        return [r["theme"] for r in rows]
    except Exception:
        return []


def _fetch_supply_chain(symbol: str) -> Optional[dict]:
    """Fetch supply chain upstream/downstream entries from research_supply_chain."""
    try:
        with _connect() as con:
            rows = con.execute(
                "SELECT direction, entity, role_note "
                "FROM research_supply_chain WHERE ticker = ? ORDER BY direction, entity",
                (symbol,),
            ).fetchall()

        if not rows:
            return None

        def _resolve(con: sqlite3.Connection, entity: str) -> dict:
            """Try to resolve entity to a known ticker/name."""
            import re
            stripped = entity.strip()
            m = re.match(r'^(\d{4})', stripped)
            ticker = None
            name = None
            if m:
                r = con.execute(
                    "SELECT ticker, name FROM research_companies WHERE ticker = ? LIMIT 1",
                    (m.group(1),),
                ).fetchone()
                if r:
                    ticker, name = r["ticker"], r["name"]
            if not ticker:
                r = con.execute(
                    "SELECT ticker, name FROM research_companies WHERE name = ? LIMIT 1",
                    (stripped,),
                ).fetchone()
                if r:
                    ticker, name = r["ticker"], r["name"]
            return {"ticker": ticker or stripped, "name": name or stripped}

        upstream = []
        downstream = []
        with _connect() as con:
            for row in rows:
                resolved = _resolve(con, row["entity"])
                entry = {
                    "ticker": resolved["ticker"],
                    "name": resolved["name"],
                    "role_note": row["role_note"],
                }
                if row["direction"] == "upstream":
                    upstream.append(entry)
                else:
                    downstream.append(entry)

        return {"upstream": upstream, "downstream": downstream}
    except Exception:
        return None


def _fetch_position(symbol: str) -> Optional[dict]:
    """Fetch current position if held (net qty > 0)."""
    try:
        with _connect() as con:
            row = con.execute(
                """
                SELECT symbol,
                    SUM(CASE WHEN side='buy' THEN qty ELSE -qty END) AS net_qty,
                    SUM(CASE WHEN side='buy' THEN qty*price + commission + tax ELSE 0 END) /
                        NULLIF(SUM(CASE WHEN side='buy' THEN qty ELSE 0 END), 0) AS avg_cost
                FROM trades
                WHERE symbol = ? AND is_void = 0
                GROUP BY symbol
                HAVING net_qty > 0
                """,
                (symbol,),
            ).fetchone()

            if not row:
                return None

            net_qty = row["net_qty"]
            avg_cost = row["avg_cost"]

            # Get last known price
            price_row = con.execute(
                "SELECT close FROM quotes WHERE symbol = ? ORDER BY date DESC LIMIT 1",
                (symbol,),
            ).fetchone()

        last_price = float(price_row["close"]) if price_row else None
        unrealized_pnl = None
        unrealized_pnl_pct = None
        if last_price and avg_cost:
            unrealized_pnl = round((last_price - avg_cost) * net_qty, 2)
            unrealized_pnl_pct = round((last_price - avg_cost) / avg_cost * 100, 2)

        return {
            "symbol": symbol,
            "qty": net_qty,
            "avg_cost": round(avg_cost, 4) if avg_cost else None,
            "last_price": last_price,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
        }
    except Exception:
        return None


def _fetch_watchlists(symbol: str) -> list[str]:
    """Return names of watchlists containing this symbol."""
    try:
        with _connect() as con:
            rows = con.execute(
                """
                SELECT wl.name
                FROM watchlist_items wi
                JOIN watchlist_lists wl ON wl.id = wi.list_id
                WHERE wi.symbol = ?
                ORDER BY wl.name
                """,
                (symbol,),
            ).fetchall()
        return [r["name"] for r in rows]
    except Exception:
        return []


def _fetch_catalysts(symbol: str) -> list[dict]:
    """Return catalyst events for this symbol."""
    try:
        from domain.catalyst.repository import list_catalysts as _list
        items = _list(DB_PATH, symbol=symbol)
        return items if isinstance(items, list) else []
    except Exception:
        return []


def _fetch_price(symbol: str) -> Optional[dict]:
    """Fetch current price + MA20/MA60/RSI from yfinance using chart.py helpers."""
    try:
        from .chart import _fetch_closes, _moving_average, _rsi

        dates, closes = _fetch_closes(symbol, 120)
        if not dates or not closes:
            return None

        ma20_series = _moving_average(closes, 20)
        ma60_series = _moving_average(closes, 60)
        rsi_series = _rsi(closes)

        current = closes[-1]
        ma20 = ma20_series[-1]
        ma60 = ma60_series[-1]
        rsi = rsi_series[-1]

        # Return last 30 data points for the chart
        tail = 30
        return {
            "current": current,
            "ma20": ma20,
            "ma60": ma60,
            "rsi": rsi,
            "dates": dates[-tail:],
            "closes": closes[-tail:],
        }
    except Exception:
        return None


def _fetch_revenue(symbol: str) -> Optional[dict]:
    """Fetch monthly revenue last 12 months from DB, trigger fetch if empty."""
    try:
        from .revenue import _ensure_table, _fetch_finmind_revenue, _store_and_compute

        _ensure_table()
        with _connect() as con:
            rows = con.execute(
                "SELECT year_month, revenue, yoy_pct, mom_pct "
                "FROM monthly_revenue WHERE symbol = ? "
                "ORDER BY year_month DESC LIMIT 12",
                (symbol,),
            ).fetchall()

        if not rows:
            # Try to fetch from FinMind
            import datetime
            start_year = datetime.date.today().year - 2
            records = _fetch_finmind_revenue(symbol, f"{start_year}-01-01")
            if records:
                _store_and_compute(symbol, records)
                with _connect() as con:
                    rows = con.execute(
                        "SELECT year_month, revenue, yoy_pct, mom_pct "
                        "FROM monthly_revenue WHERE symbol = ? "
                        "ORDER BY year_month DESC LIMIT 12",
                        (symbol,),
                    ).fetchall()

        if not rows:
            return None

        data = [
            {
                "year_month": r["year_month"],
                "revenue": r["revenue"],
                "yoy_pct": r["yoy_pct"],
                "mom_pct": r["mom_pct"],
            }
            for r in rows
        ]

        # Compute trend: compare avg YoY of last 3 months vs previous 3 months
        trend = "stable"
        yoy_values = [d["yoy_pct"] for d in data if d["yoy_pct"] is not None]
        if len(yoy_values) >= 6:
            recent_avg = sum(yoy_values[:3]) / 3
            prev_avg = sum(yoy_values[3:6]) / 3
            if recent_avg > prev_avg + 2:
                trend = "accelerating"
            elif recent_avg < prev_avg - 2:
                trend = "decelerating"

        return {"data": list(reversed(data)), "trend": trend}
    except Exception:
        return None


def _fetch_institutional(symbol: str) -> Optional[dict]:
    """Fetch institutional flow last 20 trading days."""
    try:
        from .chip import _fetch_chip_range

        end = date.today()
        start = end - timedelta(days=35)  # buffer for weekends/holidays
        rows = _fetch_chip_range(symbol, str(start), str(end))

        if not rows:
            return None

        data = [
            {
                "date": r["date"],
                "foreign_net": r["foreign"]["net"],
                "trust_net": r["investment_trust"]["net"],
                "dealer_net": r["dealer"]["net"],
                "total_net": r["total_net"],
            }
            for r in rows[-20:]
        ]
        return {"data": data}
    except Exception:
        return None


def _fetch_margin(symbol: str) -> Optional[dict]:
    """Fetch margin trading last 30 days."""
    try:
        from ..providers.twse_margin import fetch_margin_trading

        rows = fetch_margin_trading(symbol, days=30)
        if not rows:
            return None

        data = [
            {
                "date": r["date"],
                "margin_balance": r["margin_balance"],
                "short_balance": r["short_balance"],
            }
            for r in rows
        ]
        return {"data": data}
    except Exception:
        return None


def _fetch_anomalies(symbol: str) -> list[dict]:
    """Fetch recent anomalies using the anomaly detection module."""
    try:
        from .anomaly import _load_prices
        from analysis.anomaly_detector import detect_anomalies

        rows = _load_prices(symbol, 90)
        if len(rows) < 25:
            return []

        result = detect_anomalies(
            rows=rows,
            method="both",
            zscore_threshold=2.5,
            ae_threshold=2.5,
            lookback=90,
        )
        all_anomalies = result.get("zscore_anomalies", []) + result.get("ae_anomalies", [])
        # Return last 10 most recent anomalies
        all_anomalies.sort(key=lambda x: x["date"], reverse=True)
        return all_anomalies[:10]
    except Exception:
        return []


# ── Main aggregator endpoint ───────────────────────────────────────────────────

@router.get("/deep-dive/{symbol}", summary="Stock deep dive — aggregated data")
def get_deep_dive(symbol: str) -> dict:
    """
    Aggregate all data sources for a stock symbol into a single response.

    Sources:
    - SQLite research DB: company profile, supply chain, themes
    - SQLite ledger DB: position, watchlist membership, catalysts
    - yfinance: price, MA20, MA60, RSI (last 30 days)
    - FinMind: monthly revenue (last 12 months)
    - TWSE/FinMind chip: institutional flow (last 20 days)
    - FinMind margin: margin trading (last 30 days)
    - anomaly detector: recent anomalies

    Each section degrades gracefully to null/empty if the data source fails.
    """
    sym = symbol.upper()

    # Synchronous DB fetches (fast, no network)
    company = _fetch_company(sym)
    themes = _fetch_themes(sym)
    supply_chain = _fetch_supply_chain(sym)
    position = _fetch_position(sym)
    watchlists = _fetch_watchlists(sym)
    catalysts = _fetch_catalysts(sym)

    # Parallel external API calls
    price: Optional[dict] = None
    revenue: Optional[dict] = None
    institutional: Optional[dict] = None
    margin: Optional[dict] = None
    anomalies: list[dict] = []

    tasks = {
        "price": lambda: _fetch_price(sym),
        "revenue": lambda: _fetch_revenue(sym),
        "institutional": lambda: _fetch_institutional(sym),
        "margin": lambda: _fetch_margin(sym),
        "anomalies": lambda: _fetch_anomalies(sym),
    }

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        results: dict = {}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception:
                results[name] = None if name != "anomalies" else []

    price = results.get("price")
    revenue = results.get("revenue")
    institutional = results.get("institutional")
    margin = results.get("margin")
    anomalies = results.get("anomalies") or []

    return {
        "symbol": sym,
        "company": company,
        "themes": themes,
        "supply_chain": supply_chain,
        "position": position,
        "watchlists": watchlists,
        "price": price,
        "revenue": revenue,
        "institutional": institutional,
        "margin": margin,
        "anomalies": anomalies,
        "catalysts": catalysts,
    }


# ── AI Analysis endpoint ───────────────────────────────────────────────────────

@router.get("/deep-dive/{symbol}/ai-analysis", summary="AI-powered stock analysis")
def get_ai_analysis(symbol: str) -> dict:
    """
    Call the deep-dive aggregator and send data to Claude (Anthropic) or
    OpenAI for a structured investment analysis.

    Returns a JSON object with:
    - overall_score (1-10)
    - buy_signal (bool)
    - theme_analysis (str)
    - fundamental_analysis (str)
    - timing_analysis (str)
    - risks (list[str])
    - summary (str, 2-3 sentences, actionable)

    Requires ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.
    Falls back to {"error": "No AI API key configured"} if neither is set.
    """
    sym = symbol.upper()
    data = get_deep_dive(sym)

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()

    if not anthropic_key and not openai_key:
        return {"error": "No AI API key configured"}

    # Build a compact summary of data for the prompt
    prompt_data: dict = {
        "symbol": sym,
        "company": data.get("company"),
        "themes": data.get("themes"),
        "position": data.get("position"),
        "price": {
            "current": data["price"]["current"] if data.get("price") else None,
            "ma20": data["price"]["ma20"] if data.get("price") else None,
            "ma60": data["price"]["ma60"] if data.get("price") else None,
            "rsi": data["price"]["rsi"] if data.get("price") else None,
        } if data.get("price") else None,
        "revenue_trend": data["revenue"]["trend"] if data.get("revenue") else None,
        "revenue_last3": data["revenue"]["data"][-3:] if data.get("revenue") and data["revenue"].get("data") else [],
        "institutional_last5": data["institutional"]["data"][-5:] if data.get("institutional") and data["institutional"].get("data") else [],
        "margin_last5": data["margin"]["data"][-5:] if data.get("margin") and data["margin"].get("data") else [],
        "anomaly_count": len(data.get("anomalies", [])),
        "recent_anomalies": data.get("anomalies", [])[:3],
        "catalyst_count": len(data.get("catalysts", [])),
    }

    prompt = f"""You are a Taiwan stock analyst. Analyze {sym} based on the following data and return a JSON object with exactly these keys:
- overall_score: integer 1-10
- buy_signal: boolean
- theme_analysis: string describing investment theme outlook
- fundamental_analysis: string describing revenue and business fundamentals
- timing_analysis: string describing price action and technical indicators
- risks: array of strings (2-5 risk factors)
- summary: string, 2-3 sentences max, actionable

Data:
{json.dumps(prompt_data, ensure_ascii=False, indent=2)}

Return ONLY valid JSON, no markdown, no explanation."""

    if anthropic_key:
        return _call_anthropic(prompt, anthropic_key)
    else:
        return _call_openai(prompt, openai_key)


def _call_anthropic(prompt: str, api_key: str) -> dict:
    """Call Claude API via anthropic library."""
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "AI returned invalid JSON"}
    except Exception as exc:
        return {"error": str(exc)}


def _call_openai(prompt: str, api_key: str) -> dict:
    """Call OpenAI API."""
    try:
        import urllib.request as req_lib

        payload = json.dumps({
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
            "response_format": {"type": "json_object"},
        }).encode()

        request = req_lib.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with req_lib.urlopen(request, timeout=30) as resp:
            result = json.loads(resp.read())

        text = result["choices"][0]["message"]["content"]
        return json.loads(text)
    except json.JSONDecodeError:
        return {"error": "AI returned invalid JSON"}
    except Exception as exc:
        return {"error": str(exc)}
