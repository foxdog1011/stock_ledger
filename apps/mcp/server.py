"""
Stock Ledger MCP Server
=======================
Exposes portfolio management tools via the Model Context Protocol (MCP)
so AI agents (Claude Desktop, etc.) can read and write the stock ledger.

Entry point:
    python -m apps.mcp.server
    # or
    python apps/mcp/server.py

Environment variables:
    DB_PATH   Path to the SQLite database (default: /data/ledger.db)
"""

from __future__ import annotations

import math
import os
import sqlite3
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH: str = os.getenv("DB_PATH", "/data/ledger.db")
_MCP_HOST: str = os.getenv("FASTMCP_HOST", "127.0.0.1")
_MCP_PORT: int = int(os.getenv("FASTMCP_PORT", "8000"))

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Stock Ledger", host=_MCP_HOST, port=_MCP_PORT)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _ledger(db_path: str = DB_PATH):
    """Return a fresh StockLedger instance (cheap to construct)."""
    from ledger import StockLedger  # local import keeps startup fast

    return StockLedger(db_path)


# ===========================================================================
# READ TOOLS
# ===========================================================================


@mcp.tool()
def get_portfolio_snapshot(as_of: str | None = None) -> dict[str, Any]:
    """Return a high-level snapshot of the portfolio.

    Includes total equity, cash balance, aggregate market value, and the
    number of open positions.  Pass *as_of* (YYYY-MM-DD) to get a
    point-in-time view; omit it for the current state.

    Args:
        as_of: Optional date string (YYYY-MM-DD). Defaults to today.

    Returns:
        {
            "cash": float,
            "market_value": float,
            "total_equity": float,
            "position_count": int,
            "as_of": str,
        }
    """
    try:
        ledger = _ledger()
        positions = ledger.positions_with_pnl(as_of=as_of)
        bal = ledger.cash_balance(as_of=as_of)
        mv = sum(
            p["market_value"]
            for p in positions.values()
            if p.get("market_value") is not None
        )
        return {
            "cash": bal,
            "market_value": mv,
            "total_equity": bal + mv,
            "position_count": len(positions),
            "as_of": as_of or date.today().isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_portfolio_snapshot"}


@mcp.tool()
def get_positions(
    as_of: str | None = None,
    include_closed: bool = False,
) -> dict[str, Any]:
    """Return all portfolio positions with cost basis and P&L detail.

    Each entry contains: symbol, qty, avg_cost, last_price, market_value,
    unrealized_pnl, realized_pnl, and (where available) unrealized_pnl_pct.

    Args:
        as_of: Optional date string (YYYY-MM-DD). Defaults to today.
        include_closed: If True, also return positions whose qty is 0
                        (fully exited positions).

    Returns:
        {"positions": {symbol: {...}}, "count": int}
    """
    try:
        ledger = _ledger()
        raw = ledger.positions_with_pnl(as_of=as_of)
        if not include_closed:
            raw = {
                sym: data
                for sym, data in raw.items()
                if (data.get("qty") or 0) != 0
            }
        return {
            "positions": raw,
            "count": len(raw),
            "as_of": as_of or date.today().isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_positions"}


@mcp.tool()
def get_cash_balance(as_of: str | None = None) -> dict[str, Any]:
    """Return the current (or historical) cash balance.

    Args:
        as_of: Optional date string (YYYY-MM-DD). Defaults to today.

    Returns:
        {"cash": float, "as_of": str}
    """
    try:
        ledger = _ledger()
        bal = ledger.cash_balance(as_of=as_of)
        return {
            "cash": bal,
            "as_of": as_of or date.today().isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_cash_balance"}


@mcp.tool()
def get_recent_trades(
    limit: int = 20,
    symbol: str | None = None,
) -> dict[str, Any]:
    """Return recent trade records from the ledger database.

    Args:
        limit: Maximum number of trades to return (default 20).
        symbol: Filter by ticker symbol (case-insensitive). Optional.

    Returns:
        {"trades": [...], "count": int}
    """
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            if symbol:
                rows = con.execute(
                    "SELECT * FROM trades"
                    " WHERE symbol=? AND is_void=0"
                    " ORDER BY date DESC LIMIT ?",
                    (symbol.upper(), limit),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM trades"
                    " WHERE is_void=0"
                    " ORDER BY date DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        trades = [dict(r) for r in rows]
        return {"trades": trades, "count": len(trades)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_recent_trades"}


@mcp.tool()
def get_cash_transactions(limit: int = 20) -> dict[str, Any]:
    """Return recent cash ledger entries (deposits, withdrawals, dividends, etc.).

    Args:
        limit: Maximum number of entries to return (default 20).

    Returns:
        {"transactions": [...], "count": int}
    """
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.row_factory = sqlite3.Row
            rows = con.execute(
                "SELECT * FROM cash_ledger ORDER BY date DESC LIMIT ?",
                (limit,),
            ).fetchall()
        txns = [dict(r) for r in rows]
        return {"transactions": txns, "count": len(txns)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_cash_transactions"}


@mcp.tool()
def get_perf_summary(start: str, end: str) -> dict[str, Any]:
    """Return portfolio performance statistics over a date range.

    Computes metrics such as total return, annualised return, and drawdown
    by analysing daily equity values between *start* and *end*.

    Args:
        start: Start date string (YYYY-MM-DD), inclusive.
        end:   End date string (YYYY-MM-DD), inclusive.

    Returns:
        Performance summary dict with keys such as total_return,
        annualised_return, max_drawdown, sharpe_ratio (where computable).
    """
    try:
        from domain.portfolio.pnl import compute_perf_summary  # type: ignore

        ledger = _ledger()
        result = compute_perf_summary(ledger, start=start, end=end)
        return result if isinstance(result, dict) else {"summary": result}
    except ImportError:
        # Fallback: compute a simple return from daily equity series
        try:
            ledger = _ledger()
            equity_series = ledger.daily_equity(start, end)
            if not equity_series:
                return {"error": "No equity data for the given range"}
            values = list(equity_series.values())
            first, last = values[0], values[-1]
            total_return = (last - first) / first if first else None
            return {
                "start": start,
                "end": end,
                "start_equity": first,
                "end_equity": last,
                "total_return": total_return,
                "data_points": len(values),
            }
        except Exception as inner_exc:
            return {"error": str(inner_exc), "tool": "get_perf_summary"}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_perf_summary"}


@mcp.tool()
def get_risk_metrics(as_of: str | None = None) -> dict[str, Any]:
    """Return adjusted cost-basis risk metrics for all open positions.

    Uses the domain risk module to compute concentration, downside exposure,
    and adjusted cost basis per position.

    Args:
        as_of: Optional date string (YYYY-MM-DD). Defaults to today.

    Returns:
        Risk metrics dict keyed by symbol.
    """
    try:
        from domain.risk.adjusted import all_positions_adjusted_risk  # type: ignore

        ledger = _ledger()
        result = all_positions_adjusted_risk(ledger, as_of=as_of)
        return result if isinstance(result, dict) else {"risk_metrics": result}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_risk_metrics"}


@mcp.tool()
def detect_anomalies(
    symbol: str,
    days: int = 120,
    method: str = "both",
) -> dict[str, Any]:
    """Detect price/volume anomalies for a stock using statistical methods.

    Fetches historical price data from Yahoo Finance, then runs anomaly
    detection using the configured method.  For Taiwan-listed stocks supply
    the numeric ticker code (e.g. "2330"); the suffix (.TW / .TWO) is
    resolved automatically.

    Args:
        symbol: Ticker symbol.  Numeric strings are treated as Taiwan stocks.
        days:   Look-back window in trading days (default 120).
        method: Detection method — "zscore", "autoencoder", or "both".

    Returns:
        Anomaly detection results dict produced by analysis.anomaly_detector.
    """
    try:
        from analysis.anomaly_detector import detect_anomalies as _detect  # type: ignore
        import yfinance as yf  # type: ignore

        sym = symbol.upper()
        yf_sym = f"{sym}.TW" if sym.isdigit() else sym

        end_dt = date.today()
        start_dt = end_dt - timedelta(days=days + 90)

        hist = _yf_fetch(yf.Ticker(yf_sym), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)
        if hist.empty and sym.isdigit():
            hist = _yf_fetch(yf.Ticker(f"{sym}.TWO"), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)

        if hist.empty:
            return {
                "error": f"No price data found for symbol '{symbol}'",
                "symbol": sym,
            }

        rows = [
            {
                "date": idx.strftime("%Y-%m-%d"),
                "close": float(r["Close"]),
                "volume": float(r.get("Volume") or 0),
            }
            for idx, r in hist.iterrows()
        ]

        warmup_rows = rows[-(days + 80):]

        result = _detect(
            rows=warmup_rows,
            method=method,
            zscore_threshold=2.5,
            ae_threshold=2.5,
            lookback=days,
        )
        return result if isinstance(result, dict) else {"anomalies": result}
    except Exception as exc:
        return {"error": str(exc), "tool": "detect_anomalies", "symbol": symbol}


@mcp.tool()
def get_catalyst_events(
    symbol: str | None = None,
    days_ahead: int = 30,
) -> dict[str, Any]:
    """Return upcoming catalyst events (earnings, dividends, conferences, etc.).

    Args:
        symbol:     Filter by ticker symbol.  None returns all symbols.
        days_ahead: Include events within this many days from today.

    Returns:
        {"catalysts": [...], "count": int}
    """
    try:
        from domain.catalyst.repository import list_catalysts  # type: ignore

        catalysts = list_catalysts(DB_PATH)

        cutoff = date.today() + timedelta(days=days_ahead)
        today_str = date.today().isoformat()
        cutoff_str = cutoff.isoformat()

        filtered: list[dict] = []
        for cat in catalysts:
            cat_dict = dict(cat) if not isinstance(cat, dict) else cat
            cat_date = cat_dict.get("event_date") or cat_dict.get("date") or ""
            cat_sym = (cat_dict.get("symbol") or "").upper()

            if symbol and cat_sym != symbol.upper():
                continue
            if cat_date and cat_date > cutoff_str:
                continue
            if cat_date and cat_date < today_str:
                continue
            filtered.append(cat_dict)

        return {"catalysts": filtered, "count": len(filtered)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_catalyst_events"}


@mcp.tool()
def get_universe_companies() -> dict[str, Any]:
    """Return all companies tracked in the investment universe.

    Returns:
        {"companies": [...], "count": int}
    """
    try:
        from domain.universe.repository import list_companies  # type: ignore

        companies = list_companies(DB_PATH)
        companies_list = [
            dict(c) if not isinstance(c, dict) else c for c in companies
        ]
        return {"companies": companies_list, "count": len(companies_list)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_universe_companies"}


@mcp.tool()
def get_watchlists() -> dict[str, Any]:
    """Return all watchlists together with their constituent items.

    Returns:
        {"watchlists": [{id, name, items: [...]}, ...], "count": int}
    """
    try:
        from domain.watchlist.repository import (  # type: ignore
            list_watchlists,
            list_watchlist_items,
        )

        watchlists = list_watchlists(DB_PATH)
        result: list[dict] = []
        for wl in watchlists:
            wl_dict = dict(wl) if not isinstance(wl, dict) else wl
            wl_id = wl_dict.get("id") or wl_dict.get("watchlist_id")
            items = list_watchlist_items(DB_PATH, wl_id) if wl_id is not None else []
            wl_dict["items"] = [
                dict(i) if not isinstance(i, dict) else i for i in items
            ]
            result.append(wl_dict)
        return {"watchlists": result, "count": len(result)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_watchlists"}


@mcp.tool()
def get_rebalance_check(as_of: str | None = None) -> dict[str, Any]:
    """Check whether portfolio rebalancing is needed based on concentration limits.

    Computes each position's weight relative to total equity and flags any
    that exceed reasonable concentration thresholds (> 20% single name,
    etc.).

    Args:
        as_of: Optional date string (YYYY-MM-DD). Defaults to today.

    Returns:
        {
            "needs_rebalance": bool,
            "alerts": [...],
            "weights": {symbol: weight_pct},
            "as_of": str,
        }
    """
    try:
        ledger = _ledger()
        positions = ledger.positions_with_pnl(as_of=as_of)
        cash = ledger.cash_balance(as_of=as_of)

        mv = sum(
            p["market_value"]
            for p in positions.values()
            if p.get("market_value") is not None
        )
        total_equity = cash + mv

        weights: dict[str, float] = {}
        alerts: list[dict] = []

        if total_equity > 0:
            for sym, pos in positions.items():
                if (pos.get("qty") or 0) == 0:
                    continue
                pos_mv = pos.get("market_value") or 0
                weight = pos_mv / total_equity
                weights[sym] = round(weight * 100, 2)

                if weight > 0.20:
                    alerts.append(
                        {
                            "symbol": sym,
                            "weight_pct": round(weight * 100, 2),
                            "message": f"{sym} is {weight*100:.1f}% of portfolio (>20% threshold)",
                            "severity": "high" if weight > 0.30 else "medium",
                        }
                    )

            cash_weight = cash / total_equity
            if cash_weight > 0.40:
                alerts.append(
                    {
                        "symbol": "CASH",
                        "weight_pct": round(cash_weight * 100, 2),
                        "message": f"Cash is {cash_weight*100:.1f}% of portfolio (>40%)",
                        "severity": "low",
                    }
                )

        return {
            "needs_rebalance": len(alerts) > 0,
            "alerts": alerts,
            "weights": weights,
            "cash_pct": round(cash / total_equity * 100, 2) if total_equity else 0,
            "total_equity": total_equity,
            "as_of": as_of or date.today().isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_rebalance_check"}


@mcp.tool()
def get_lots(
    symbol: str,
    method: str = "fifo",
) -> dict[str, Any]:
    """Return lot-level position detail for a symbol using the specified cost method.

    Args:
        symbol: Ticker symbol (case-insensitive).
        method: Cost method — "fifo", "lifo", or "avg" (default "fifo").

    Returns:
        Lot detail dict as returned by the ledger's lots_by_method.
    """
    try:
        if method not in ("fifo", "lifo", "avg"):
            return {
                "error": f"Invalid method '{method}'. Must be 'fifo', 'lifo', or 'avg'.",
                "tool": "get_lots",
            }
        ledger = _ledger()
        return ledger.lots_by_method(symbol=symbol.upper(), method=method)
    except Exception as exc:
        return {"error": str(exc), "tool": "get_lots"}


@mcp.tool()
def get_price_alerts(symbol: str | None = None) -> dict[str, Any]:
    """List active (non-triggered) price alerts.

    Args:
        symbol: Filter by ticker symbol. None returns alerts for all symbols.

    Returns:
        {"alerts": [...], "count": int}
    """
    try:
        with sqlite3.connect(DB_PATH) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS price_alerts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    alert_type  TEXT    NOT NULL,
                    price       REAL    NOT NULL,
                    note        TEXT    DEFAULT '',
                    created_at  TEXT    NOT NULL DEFAULT (date('now')),
                    triggered   INTEGER NOT NULL DEFAULT 0,
                    triggered_at TEXT
                )
            """)
            con.row_factory = sqlite3.Row
            if symbol:
                rows = con.execute(
                    "SELECT * FROM price_alerts WHERE triggered=0 AND symbol=? ORDER BY id",
                    (symbol.upper(),),
                ).fetchall()
            else:
                rows = con.execute(
                    "SELECT * FROM price_alerts WHERE triggered=0 ORDER BY id"
                ).fetchall()
        alerts = [dict(r) for r in rows]
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_price_alerts"}


@mcp.tool()
def add_price_alert(
    symbol: str,
    alert_type: str,
    price: float,
    note: str = "",
) -> dict[str, Any]:
    """Create a stop-loss or target-price alert.

    Args:
        symbol:     Ticker symbol (case-insensitive; stored as uppercase).
        alert_type: "stop_loss" (triggers when price drops to or below target)
                    or "target" (triggers when price rises to or above target).
        price:      Alert trigger price.
        note:       Optional free-text annotation.

    Returns:
        Confirmation dict with the new alert's id and details.
    """
    try:
        if alert_type not in ("stop_loss", "target"):
            return {
                "error": "alert_type must be 'stop_loss' or 'target'.",
                "tool": "add_price_alert",
            }
        with sqlite3.connect(DB_PATH) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS price_alerts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol      TEXT    NOT NULL,
                    alert_type  TEXT    NOT NULL,
                    price       REAL    NOT NULL,
                    note        TEXT    DEFAULT '',
                    created_at  TEXT    NOT NULL DEFAULT (date('now')),
                    triggered   INTEGER NOT NULL DEFAULT 0,
                    triggered_at TEXT
                )
            """)
            cur = con.execute(
                "INSERT INTO price_alerts (symbol, alert_type, price, note) VALUES (?,?,?,?)",
                (symbol.upper(), alert_type, price, note),
            )
            new_id = cur.lastrowid
        return {
            "status": "created",
            "id": new_id,
            "symbol": symbol.upper(),
            "alert_type": alert_type,
            "price": price,
            "note": note,
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "add_price_alert"}


@mcp.tool()
def delete_price_alert(alert_id: int) -> dict[str, Any]:
    """Delete a price alert by its id.

    Args:
        alert_id: The integer id of the alert to delete.

    Returns:
        {"deleted": alert_id} on success, or an error dict if not found.
    """
    try:
        with sqlite3.connect(DB_PATH) as con:
            affected = con.execute(
                "DELETE FROM price_alerts WHERE id=?", (alert_id,)
            ).rowcount
        if affected == 0:
            return {"error": f"Alert {alert_id} not found.", "tool": "delete_price_alert"}
        return {"deleted": alert_id}
    except Exception as exc:
        return {"error": str(exc), "tool": "delete_price_alert"}


# ===========================================================================
# WRITE TOOLS
# ===========================================================================


@mcp.tool()
def add_trade(
    date: str,
    symbol: str,
    side: str,
    qty: float,
    price: float,
    commission: float = 0.0,
    tax: float = 0.0,
    note: str = "",
) -> dict[str, Any]:
    """Record a new trade in the ledger.

    Args:
        date:       Trade date (YYYY-MM-DD).
        symbol:     Ticker symbol (case-insensitive; stored as uppercase).
        side:       "buy" or "sell".
        qty:        Number of shares / units traded (positive number).
        price:      Execution price per share / unit.
        commission: Brokerage commission (default 0).
        tax:        Transaction tax / stamp duty (default 0).
        note:       Optional free-text annotation.

    Returns:
        Confirmation dict with the recorded trade details.
    """
    try:
        if side.lower() not in {"buy", "sell"}:
            return {
                "error": f"Invalid side '{side}'. Must be 'buy' or 'sell'.",
                "tool": "add_trade",
            }
        if qty <= 0:
            return {"error": "qty must be a positive number.", "tool": "add_trade"}
        if price <= 0:
            return {"error": "price must be a positive number.", "tool": "add_trade"}

        ledger = _ledger()
        ledger.add_trade(
            date=date,
            symbol=symbol.upper(),
            side=side.lower(),
            qty=qty,
            price=price,
            commission=commission,
            tax=tax,
            note=note,
        )
        return {
            "status": "recorded",
            "date": date,
            "symbol": symbol.upper(),
            "side": side.lower(),
            "qty": qty,
            "price": price,
            "commission": commission,
            "tax": tax,
            "note": note,
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "add_trade"}


@mcp.tool()
def add_cash(
    date: str,
    amount: float,
    note: str = "",
) -> dict[str, Any]:
    """Record a cash deposit or withdrawal.

    Use a positive *amount* for deposits (money in) and a negative *amount*
    for withdrawals (money out).

    Args:
        date:   Transaction date (YYYY-MM-DD).
        amount: Cash amount.  Positive = deposit, negative = withdrawal.
        note:   Optional free-text description.

    Returns:
        Confirmation dict with the recorded transaction details.
    """
    try:
        if amount == 0:
            return {
                "error": "amount must be non-zero.",
                "tool": "add_cash",
            }

        ledger = _ledger()
        ledger.add_cash(date=date, amount=amount, note=note)
        return {
            "status": "recorded",
            "date": date,
            "amount": amount,
            "type": "deposit" if amount > 0 else "withdrawal",
            "note": note,
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "add_cash"}


# ===========================================================================
# Research tools (My-TW-Coverage integration)
# ===========================================================================


def _research_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@mcp.tool()
def get_company_research(ticker: str) -> dict[str, Any]:
    """Get fundamental research profile for a Taiwan stock.

    Returns company description, sector, industry, supply chain relationships,
    customer/supplier links, and investment themes sourced from My-TW-Coverage.

    Args:
        ticker: 4-digit Taiwan stock ticker (e.g. "2330" for TSMC).

    Returns:
        Company profile with supply_chain, customers, suppliers, and themes lists.
    """
    try:
        with _research_db() as con:
            company = con.execute(
                "SELECT ticker, name, sector, industry, market_cap, ev, description "
                "FROM research_companies WHERE ticker = ?",
                (ticker,),
            ).fetchone()
            if company is None:
                return {"error": f"Ticker '{ticker}' not found in research database"}

            supply_chain = con.execute(
                "SELECT direction, entity, role_note FROM research_supply_chain "
                "WHERE ticker = ? ORDER BY direction, entity",
                (ticker,),
            ).fetchall()

            customers = con.execute(
                "SELECT counterpart, is_customer, note FROM research_customers "
                "WHERE ticker = ? ORDER BY counterpart",
                (ticker,),
            ).fetchall()

            themes = con.execute(
                "SELECT theme FROM research_themes WHERE ticker = ? ORDER BY theme",
                (ticker,),
            ).fetchall()

        return {
            "ticker": company["ticker"],
            "name": company["name"],
            "sector": company["sector"],
            "industry": company["industry"],
            "market_cap_million_twd": company["market_cap"],
            "ev_million_twd": company["ev"],
            "description": company["description"],
            "supply_chain": [
                {"direction": r["direction"], "entity": r["entity"], "role_note": r["role_note"]}
                for r in supply_chain
            ],
            "customers": [
                {"counterpart": r["counterpart"], "is_customer": bool(r["is_customer"]), "note": r["note"]}
                for r in customers
            ],
            "themes": [r["theme"] for r in themes],
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_company_research"}


@mcp.tool()
def find_supply_chain(ticker: str) -> dict[str, Any]:
    """Find upstream and downstream supply chain companies for a Taiwan stock.

    Also returns related companies — other tickers whose supply chain mentions
    this company, revealing indirect ecosystem relationships.

    Args:
        ticker: 4-digit Taiwan stock ticker (e.g. "2330").

    Returns:
        upstream, downstream lists and related_companies with ticker cross-references.
    """
    try:
        with _research_db() as con:
            name_row = con.execute(
                "SELECT name FROM research_companies WHERE ticker = ?", (ticker,)
            ).fetchone()
            if name_row is None:
                return {"error": f"Ticker '{ticker}' not found in research database"}
            company_name = name_row["name"]

            sc_rows = con.execute(
                "SELECT direction, entity, role_note FROM research_supply_chain "
                "WHERE ticker = ? ORDER BY direction, entity",
                (ticker,),
            ).fetchall()

            related_rows = con.execute(
                """
                SELECT DISTINCT sc.ticker, rc.name, rc.industry
                FROM research_supply_chain sc
                JOIN research_companies rc ON rc.ticker = sc.ticker
                WHERE sc.ticker != ?
                  AND (sc.entity LIKE ? OR sc.entity LIKE ?)
                ORDER BY rc.name
                """,
                (ticker, f"%{ticker}%", f"%{company_name}%"),
            ).fetchall()

        return {
            "ticker": ticker,
            "name": company_name,
            "upstream": [
                {"entity": r["entity"], "role_note": r["role_note"]}
                for r in sc_rows if r["direction"] == "upstream"
            ],
            "downstream": [
                {"entity": r["entity"], "role_note": r["role_note"]}
                for r in sc_rows if r["direction"] == "downstream"
            ],
            "related_companies": [
                {"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]}
                for r in related_rows
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "find_supply_chain"}


@mcp.tool()
def screen_by_theme(theme: str) -> dict[str, Any]:
    """List all Taiwan stocks tagged with an investment theme.

    Themes include: AI_伺服器, ABF_載板, CoWoS, HBM, NVIDIA, EUV, 5G, CPO,
    Apple, and others from the My-TW-Coverage database.

    Args:
        theme: Theme name to filter by (e.g. "AI_伺服器", "HBM", "5G").

    Returns:
        List of companies in the theme with ticker, name, and industry.
    """
    try:
        with _research_db() as con:
            rows = con.execute(
                """
                SELECT rc.ticker, rc.name, rc.industry
                FROM research_themes rt
                JOIN research_companies rc ON rc.ticker = rt.ticker
                WHERE rt.theme = ?
                ORDER BY rc.name
                """,
                (theme,),
            ).fetchall()

            if not rows:
                # Return available themes as hint
                available = con.execute(
                    "SELECT theme, COUNT(*) as cnt FROM research_themes "
                    "GROUP BY theme ORDER BY cnt DESC"
                ).fetchall()
                return {
                    "error": f"Theme '{theme}' not found",
                    "available_themes": [r["theme"] for r in available],
                }

        return {
            "theme": theme,
            "total": len(rows),
            "companies": [
                {"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]}
                for r in rows
            ],
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "screen_by_theme"}


# ===========================================================================
# Benchmark comparison tool
# ===========================================================================


@mcp.tool()
def compare_benchmark(
    bench: str = "0050",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    """Compare portfolio performance against a benchmark index.

    Computes cumulative return comparison, tracking error, correlation,
    and information ratio between the portfolio and a benchmark.

    Available benchmarks: 0050 (Taiwan 50 ETF), TAIEX (Taiwan Index),
    0056 (High Dividend ETF), SPY, QQQ.
    Note: bootstrap the benchmark data first via POST /benchmark/bootstrap
    if you haven't done so.

    Args:
        bench: Benchmark ticker — "0050", "TAIEX", "0056", "SPY", "QQQ", etc.
        start: Start date YYYY-MM-DD (default: 1 year ago).
        end:   End date YYYY-MM-DD (default: today).

    Returns:
        Dict with metrics (excess_return_pct, tracking_error, correlation,
        information_ratio) and most-recent comparison data point.
    """
    try:
        import math
        import pandas as pd
        from ledger.equity import equity_curve as _portfolio_curve

        today = date.today()
        end_str   = end   or today.isoformat()
        start_str = start or (today - timedelta(days=365)).isoformat()

        ledger = _ledger()

        # Fetch portfolio equity curve (monthly)
        port_df = _portfolio_curve(ledger, start=start_str, end=end_str, freq="ME")
        if port_df is None or port_df.empty:
            return {"error": "No portfolio equity data in range", "tool": "compare_benchmark"}

        port_df.index = pd.to_datetime(port_df.index)
        valid_mask = port_df["total_equity"] > 0
        if not valid_mask.any():
            return {"error": "Portfolio has no equity in requested range", "tool": "compare_benchmark"}

        first_valid = port_df.index[valid_mask][0]
        port_df = port_df[port_df.index >= first_valid].copy()
        base_equity = port_df["total_equity"].iloc[0]
        if base_equity == 0:
            return {"error": "Portfolio starting equity is zero", "tool": "compare_benchmark"}
        port_df["cum_return_pct"] = (port_df["total_equity"] / base_equity - 1) * 100

        # Fetch benchmark prices from DB
        with sqlite3.connect(DB_PATH) as con:
            rows = con.execute(
                "SELECT date, close FROM prices WHERE ticker=? AND date BETWEEN ? AND ? ORDER BY date",
                (bench.upper(), start_str, end_str),
            ).fetchall()

        if not rows:
            return {
                "error": f"No benchmark data for '{bench}' — run POST /benchmark/bootstrap first",
                "tool": "compare_benchmark",
            }

        bench_s = pd.Series(
            {pd.Timestamp(r[0]): float(r[1]) for r in rows},
            dtype=float,
        ).resample("ME").last().dropna()

        bench_aligned = bench_s[bench_s.index >= first_valid]
        if bench_aligned.empty:
            return {"error": f"No benchmark data for '{bench}' after portfolio start", "tool": "compare_benchmark"}

        base_bench = bench_aligned.iloc[0]
        bench_cum  = (bench_aligned / base_bench - 1) * 100

        aligned = pd.DataFrame({"portfolio": port_df["cum_return_pct"], "bench": bench_cum}).dropna()
        if aligned.empty:
            return {"error": "No overlapping dates between portfolio and benchmark", "tool": "compare_benchmark"}

        aligned["excess"] = aligned["portfolio"] - aligned["bench"]
        latest = aligned.iloc[-1]

        # Metrics
        ann = 12  # monthly
        metrics: dict[str, Any] = {
            "excess_return_pct": round(float(latest["excess"]), 2),
            "portfolio_cum_return_pct": round(float(latest["portfolio"]), 2),
            "bench_cum_return_pct": round(float(latest["bench"]), 2),
        }
        try:
            port_p  = port_df["total_equity"].pct_change().dropna() * 100
            bench_p = bench_aligned.pct_change().dropna() * 100
            pf = pd.DataFrame({"p": port_p, "b": bench_p}).dropna()
            if len(pf) >= 2:
                excess_p = pf["p"] - pf["b"]
                te = float(excess_p.std()) * math.sqrt(ann)
                if not math.isnan(te):
                    metrics["tracking_error_annualized"] = round(te, 4)
                corr = float(pf["p"].corr(pf["b"]))
                if not math.isnan(corr):
                    metrics["correlation"] = round(corr, 4)
                if metrics.get("tracking_error_annualized", 0) > 0:
                    ir = float(excess_p.mean()) * ann / metrics["tracking_error_annualized"]
                    if not math.isnan(ir):
                        metrics["information_ratio"] = round(ir, 4)
        except Exception:
            pass

        return {
            "bench": bench.upper(),
            "start": start_str,
            "end": end_str,
            "metrics": metrics,
            "interpretation": (
                "outperforming" if metrics["excess_return_pct"] > 0 else "underperforming"
            ),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "compare_benchmark"}


# ===========================================================================
# Market data tools (yfinance-backed)
# ===========================================================================


def _yf_symbol(symbol: str) -> str:
    """Convert Taiwan numeric ticker to Yahoo Finance format."""
    sym = symbol.upper().strip()
    if sym.isdigit():
        return f"{sym}.TW"
    return sym


def _yf_fetch(yf_ticker, method: str, retries: int = 2, **kwargs):
    """Call a yfinance method with simple retry on transient failures."""
    import time
    last_exc: Exception = RuntimeError("no attempts")
    for attempt in range(retries + 1):
        try:
            return getattr(yf_ticker, method)(**kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(1)
    raise last_exc


@mcp.tool()
def get_quote(symbol: str) -> dict[str, Any]:
    """Get a comprehensive real-time quote for any stock.

    Returns current price, change, volume, PE ratio, 52-week range,
    market cap, and dividend yield.  Taiwan numeric tickers (e.g. "2330")
    are resolved automatically.

    Args:
        symbol: Ticker symbol — e.g. "AAPL", "2330", "0050".

    Returns:
        Quote dict with price, change_pct, volume, pe_ratio, market_cap, etc.
    """
    try:
        import yfinance as yf

        yf_sym = _yf_symbol(symbol)
        ticker = yf.Ticker(yf_sym)
        try:
            fast = ticker.fast_info
            # Validate it's a real object (not None/empty) by checking a key attr
            _ = fast.last_price
        except Exception:
            fast = None
        if fast is None and symbol.isdigit():
            yf_sym = f"{symbol}.TWO"
            ticker = yf.Ticker(yf_sym)
            fast = ticker.fast_info
        info = ticker.info or {}

        price = getattr(fast, "last_price", None) or info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = getattr(fast, "previous_close", None) or info.get("previousClose") or info.get("regularMarketPreviousClose")
        change = (price - prev_close) if (price and prev_close) else None
        change_pct = (change / prev_close * 100) if (change is not None and prev_close) else None

        return {
            "symbol": symbol.upper(),
            "yf_symbol": yf_sym,
            "price": round(price, 2) if price else None,
            "change": round(change, 2) if change is not None else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "volume": getattr(fast, "three_month_average_volume", None) or info.get("volume"),
            "market_cap": getattr(fast, "market_cap", None) or info.get("marketCap"),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "52w_high": getattr(fast, "year_high", None) or info.get("fiftyTwoWeekHigh"),
            "52w_low": getattr(fast, "year_low", None) or info.get("fiftyTwoWeekLow"),
            "dividend_yield": info.get("dividendYield"),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "as_of": date.today().isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_quote", "symbol": symbol}


@mcp.tool()
def get_technical_indicators(symbol: str, days: int = 120) -> dict[str, Any]:
    """Compute technical indicators for a stock using recent price history.

    Calculates Moving Averages (MA5/20/60), RSI-14, MACD (12/26/9),
    and Bollinger Bands (20-day, ±2σ).  Useful for trend analysis and
    entry/exit signal generation.

    Args:
        symbol: Ticker symbol — e.g. "AAPL", "2330".
        days:   Number of trading days of history to use (default 120).

    Returns:
        Dict with ma, rsi, macd, bollinger keys plus latest close price.
    """
    try:
        import yfinance as yf
        import pandas as pd

        yf_sym = _yf_symbol(symbol)
        end_dt = date.today()
        start_dt = end_dt - timedelta(days=days + 120)  # extra for warmup

        hist = _yf_fetch(yf.Ticker(yf_sym), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)
        if hist.empty and symbol.isdigit():
            hist = _yf_fetch(yf.Ticker(f"{symbol}.TWO"), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)
        if hist.empty:
            return {"error": f"No price data for '{symbol}'", "tool": "get_technical_indicators"}

        close = hist["Close"]
        latest = float(close.iloc[-1])

        # Moving averages
        ma = {}
        for period in (5, 10, 20, 60):
            if len(close) >= period:
                ma[f"ma{period}"] = round(float(close.rolling(period).mean().iloc[-1]), 2)

        # RSI-14
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - (100 / (1 + rs))
        rsi = round(float(rsi_series.iloc[-1]), 2) if not rsi_series.empty else None

        # MACD (12, 26, 9)
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        macd = {
            "macd": round(float(macd_line.iloc[-1]), 4),
            "signal": round(float(signal_line.iloc[-1]), 4),
            "histogram": round(float(histogram.iloc[-1]), 4),
            "trend": "bullish" if macd_line.iloc[-1] > signal_line.iloc[-1] else "bearish",
        }

        # Bollinger Bands (20, 2σ)
        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_pct = (close - bb_lower) / (bb_upper - bb_lower)
        bollinger = {
            "upper": round(float(bb_upper.iloc[-1]), 2),
            "mid": round(float(bb_mid.iloc[-1]), 2),
            "lower": round(float(bb_lower.iloc[-1]), 2),
            "pct_b": round(float(bb_pct.iloc[-1]), 3),
            "position": "overbought" if bb_pct.iloc[-1] > 1 else ("oversold" if bb_pct.iloc[-1] < 0 else "normal"),
        }

        return {
            "symbol": symbol.upper(),
            "latest_close": round(latest, 2),
            "ma": ma,
            "rsi14": rsi,
            "rsi_signal": "overbought" if (rsi or 0) > 70 else ("oversold" if (rsi or 100) < 30 else "neutral"),
            "macd": macd,
            "bollinger": bollinger,
            "as_of": date.today().isoformat(),
            "data_points": len(close),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_technical_indicators", "symbol": symbol}


@mcp.tool()
def get_news(symbol: str, count: int = 5) -> dict[str, Any]:
    """Fetch recent news articles for a stock.

    Returns the latest news headlines, publishers, and publication times
    for the given ticker.  Useful for catalyst monitoring and sentiment
    awareness before entering or exiting a position.

    Args:
        symbol: Ticker symbol — e.g. "AAPL", "2330".
        count:  Number of articles to return (default 5, max 10).

    Returns:
        {"symbol": ..., "articles": [{title, publisher, link, published}], "count": int}
    """
    try:
        import yfinance as yf

        yf_sym = _yf_symbol(symbol)
        ticker = yf.Ticker(yf_sym)
        try:
            raw_news = ticker.news or []
        except Exception:
            raw_news = []

        articles = []
        for item in raw_news[: min(count, 10)]:
            content = item.get("content", {})
            articles.append({
                "title": content.get("title") or item.get("title", ""),
                "publisher": (content.get("provider") or {}).get("displayName") or item.get("publisher", ""),
                "link": (content.get("canonicalUrl") or {}).get("url") or item.get("link", ""),
                "published": content.get("pubDate") or item.get("providerPublishTime", ""),
            })

        return {"symbol": symbol.upper(), "articles": articles, "count": len(articles)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_news", "symbol": symbol}


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport in ("sse", "streamable-http"):
        mcp.run(transport=transport)
    else:
        mcp.run(transport="stdio")
