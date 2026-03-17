"""Portfolio P&L computation using Weighted Average Cost (WAC).

Public API
----------
position_pnl(ledger, symbol, as_of) -> dict
all_positions_pnl(ledger, as_of, open_only=True) -> list[dict]
position_detail(ledger, symbol, as_of) -> dict

Design notes
------------
- All functions accept a ``StockLedger`` instance as the first argument and
  return plain dicts/lists.  No FastAPI, Pydantic, or HTTP concerns here.
- DB access uses ``get_connection(ledger.db_path)``; connections are opened
  per-call (read-only, no commit needed) and always closed in a finally block.
- ``StockLedger`` is imported only under ``TYPE_CHECKING`` to avoid a circular
  import (ledger.ledger → domain.portfolio.pnl → ledger.ledger).
  The shims in ``StockLedger`` use function-local imports for the same reason.
"""
from __future__ import annotations

from datetime import date as Date
from typing import TYPE_CHECKING

from ledger.db import get_connection

if TYPE_CHECKING:
    from ledger import StockLedger


def position_pnl(
    ledger: "StockLedger",
    symbol: str,
    as_of: str | Date | None = None,
) -> dict:
    """
    Detailed P&L for *symbol* using the Weighted Average Cost method.

    Buy commission is included in the cost basis (per share).
    Sell commission is deducted from realized proceeds.

    Returns
    -------
    dict
        symbol, qty, avg_cost, realized_pnl, unrealized_pnl,
        last_price, price_source, market_value
    """
    as_of = str(as_of) if as_of else str(Date.today())

    conn = get_connection(ledger.db_path)
    try:
        rows = conn.execute(
            "SELECT side, qty, price, commission, tax FROM trades "
            "WHERE symbol = ? AND date <= ? AND is_void = 0 ORDER BY date, id",
            (symbol.upper(), as_of),
        ).fetchall()
    finally:
        conn.close()

    shares = 0.0
    avg_cost = 0.0      # per share, includes buy commission + tax
    realized = 0.0

    for t in rows:
        qty = t["qty"]
        price = t["price"]
        comm = t["commission"]
        tax = t["tax"]

        if t["side"] == "buy":
            cost_per_share = (qty * price + comm + tax) / qty
            avg_cost = (shares * avg_cost + qty * cost_per_share) / (shares + qty)
            shares += qty
        else:
            realized += (price - avg_cost) * qty - comm - tax
            shares -= qty

    lps = ledger.last_price_with_source(symbol, as_of)
    px, source = lps["price"], lps["price_source"]
    unrealized = (
        round((px - avg_cost) * shares, 2)
        if (px is not None and shares > 0)
        else None
    )

    return {
        "symbol": symbol.upper(),
        "qty": shares,
        "avg_cost": round(avg_cost, 4) if shares > 0 else None,
        "realized_pnl": round(realized, 2),
        "unrealized_pnl": unrealized,
        "last_price": px,
        "price_source": source,
        "market_value": round(px * shares, 2) if (px is not None and shares > 0) else None,
    }


def all_positions_pnl(
    ledger: "StockLedger",
    as_of: str | Date | None = None,
    open_only: bool = True,
) -> list[dict]:
    """
    Return ``position_pnl`` for every symbol that has ever had a trade.

    Parameters
    ----------
    open_only : bool
        If ``True`` (default), only symbols with qty > 0 are returned.

    Output order: sorted by symbol (ascending), matching the ORDER BY in the
    SQL query.
    """
    as_of = str(as_of) if as_of else str(Date.today())

    conn = get_connection(ledger.db_path)
    try:
        symbols = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT symbol FROM trades "
                "WHERE date <= ? AND is_void = 0 ORDER BY symbol",
                (as_of,),
            ).fetchall()
        ]
    finally:
        conn.close()

    results = [position_pnl(ledger, sym, as_of=as_of) for sym in symbols]
    if open_only:
        results = [r for r in results if r["qty"] > 0]
    return results


def position_detail(
    ledger: "StockLedger",
    symbol: str,
    as_of: str | Date | None = None,
) -> dict:
    """
    Extended position detail: base P&L + cost_summary + running_wac + wac_series.
    """
    as_of = str(as_of) if as_of else str(Date.today())
    sym = symbol.upper()

    pnl = position_pnl(ledger, sym, as_of=as_of)

    conn = get_connection(ledger.db_path)
    try:
        rows = conn.execute(
            "SELECT id, date, side, qty, price, commission, tax, note FROM trades "
            "WHERE symbol = ? AND date <= ? AND is_void = 0 ORDER BY date, id",
            (sym, as_of),
        ).fetchall()
    finally:
        conn.close()
    trades = [dict(r) for r in rows]
    buys = [t for t in trades if t["side"] == "buy"]

    if buys:
        cost_summary = {
            "buy_count": len(buys),
            "buy_qty_total": sum(t["qty"] for t in buys),
            "buy_cost_total_including_fees": round(
                sum(t["qty"] * t["price"] + t["commission"] + t["tax"] for t in buys), 2
            ),
            "min_buy_price": min(t["price"] for t in buys),
            "max_buy_price": max(t["price"] for t in buys),
            "first_buy_date": buys[0]["date"],
            "last_buy_date":  buys[-1]["date"],
        }
    else:
        cost_summary = None

    shares = 0.0
    avg_cost = 0.0
    running_wac: list[dict] = []
    wac_series: list[dict] = []
    _last_buy_data: dict | None = None  # tracks prev/new state around each buy

    for t in trades:
        qty   = t["qty"]
        price = t["price"]
        comm  = t["commission"]
        tax   = t["tax"]
        if t["side"] == "buy":
            cost_per_share = (qty * price + comm + tax) / qty
            new_avg = (shares * avg_cost + qty * cost_per_share) / (shares + qty)
            _last_buy_data = {
                "trade":         t,
                "prev_qty":      shares,
                "prev_avg_cost": avg_cost,
                "new_qty":       shares + qty,
                "new_avg_cost":  new_avg,
            }
            avg_cost = new_avg
            shares += qty
        else:
            shares -= qty

        entry = {
            "trade_id":       t["id"],
            "date":           t["date"],
            "side":           t["side"],
            "qty":            qty,
            "price":          price,
            "commission":     comm,
            "tax":            tax,
            "qty_after":      round(shares, 6),
            "avg_cost_after": round(avg_cost, 4) if shares > 0 else None,
        }
        running_wac.append(entry)
        if shares > 0:
            wac_series.append({"date": t["date"], "avg_cost": round(avg_cost, 4)})

    px  = pnl.get("last_price")
    avg = pnl.get("avg_cost")
    pnl_pct = (
        round((px - avg) / avg * 100, 2)
        if (px and avg and pnl["qty"] > 0) else None
    )

    # ── last_buy + cost_impact ──────────────────────────────────────
    last_buy: dict | None = None
    cost_impact: dict | None = None
    if _last_buy_data:
        lb_t      = _last_buy_data["trade"]
        prev_qty  = _last_buy_data["prev_qty"]
        prev_avg  = _last_buy_data["prev_avg_cost"]
        new_qty   = _last_buy_data["new_qty"]
        new_avg   = _last_buy_data["new_avg_cost"]
        buy_fees  = lb_t["commission"] + lb_t["tax"]
        delta_avg = new_avg - prev_avg
        delta_pct = (delta_avg / prev_avg * 100) if prev_avg != 0 else None

        px_val = pnl.get("last_price")
        impact_unreal = None
        if px_val is not None:
            impact_unreal = round(
                (px_val - new_avg) * new_qty - (px_val - prev_avg) * prev_qty, 2
            )

        last_buy = {
            "trade_id":   lb_t["id"],
            "date":       lb_t["date"],
            "qty":        lb_t["qty"],
            "price":      lb_t["price"],
            "commission": lb_t["commission"],
            "tax":        lb_t["tax"],
        }
        cost_impact = {
            "prev_qty":            round(prev_qty, 6),
            "prev_avg_cost":       round(prev_avg, 4) if prev_qty > 0 else None,
            "buy_qty":             lb_t["qty"],
            "buy_price":           lb_t["price"],
            "buy_fees":            round(buy_fees, 2),
            "new_qty":             round(new_qty, 6),
            "new_avg_cost":        round(new_avg, 4),
            "delta_avg_cost":      round(delta_avg, 4),
            "delta_avg_cost_pct":  round(delta_pct, 4) if delta_pct is not None else None,
            "impact_unrealized_pnl": impact_unreal,
        }

    return {**pnl, "pnl_pct": pnl_pct, "cost_summary": cost_summary,
            "running_wac": running_wac, "wac_series": wac_series,
            "last_buy": last_buy, "cost_impact": cost_impact}
