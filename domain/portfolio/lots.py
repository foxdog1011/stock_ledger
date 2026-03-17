"""Lot-level position analysis: FIFO, LIFO, and WAC methods.

Public API
----------
lots_by_method(ledger, symbol, as_of, method='fifo') -> dict

Design notes
------------
- Accepts a ``StockLedger`` instance and returns a plain dict.  No FastAPI,
  Pydantic, or HTTP concerns here.
- DB access uses ``get_connection(ledger.db_path)``; connections are opened
  per-call and always closed in a finally block.
- ``StockLedger`` is imported only under ``TYPE_CHECKING`` to avoid a circular
  import.  The shim in ``StockLedger`` uses a function-local import.
"""
from __future__ import annotations

from datetime import date as Date
from typing import TYPE_CHECKING

from ledger.db import get_connection

if TYPE_CHECKING:
    from ledger import StockLedger


def lots_by_method(
    ledger: "StockLedger",
    symbol: str,
    as_of: str | Date | None = None,
    method: str = "fifo",
) -> dict:
    """
    Return lot-level position detail.

    method : ``"fifo"`` | ``"lifo"`` | ``"wac"``
        FIFO / LIFO pairs sells to specific buy lots.
        WAC shows remaining lots (fifo-tracked qty) but uses WAC cost for P&L.
    """
    as_of  = str(as_of) if as_of else str(Date.today())
    sym    = symbol.upper()
    method = method.lower()
    if method not in ("fifo", "lifo", "wac"):
        raise ValueError(f"method must be fifo, lifo, or wac; got '{method}'")

    conn = get_connection(ledger.db_path)
    try:
        rows = conn.execute(
            "SELECT id, date, side, qty, price, commission, tax FROM trades "
            "WHERE symbol = ? AND date <= ? AND is_void = 0 ORDER BY date, id",
            (sym, as_of),
        ).fetchall()
    finally:
        conn.close()
    trades = [dict(r) for r in rows]

    open_lots: list[dict] = []
    realized_breakdown: list[dict] = []
    lot_counter = 0
    shares_wac  = 0.0
    avg_cost_wac = 0.0

    for t in trades:
        qty   = t["qty"]
        price = t["price"]
        comm  = t["commission"]
        tax   = t["tax"]

        if t["side"] == "buy":
            lot_counter += 1
            cost_per_share = (qty * price + comm + tax) / qty
            avg_cost_wac = (
                (shares_wac * avg_cost_wac + qty * cost_per_share)
                / (shares_wac + qty)
            )
            shares_wac += qty
            open_lots.append({
                "lot_id":       lot_counter,
                "buy_trade_id": t["id"],
                "buy_date":     t["date"],
                "qty_remaining": qty,
                "buy_price":    price,
                "commission":   comm,
                "tax":          tax,
                "cost_per_share": round(cost_per_share, 4),
            })
        else:  # sell
            shares_wac -= qty
            remaining   = qty
            allocations: list[dict] = []

            indices = (
                list(range(len(open_lots) - 1, -1, -1))
                if method == "lifo"
                else list(range(len(open_lots)))
            )
            for i in indices:
                if remaining <= 0:
                    break
                lot     = open_lots[i]
                consume = min(lot["qty_remaining"], remaining)
                lot["qty_remaining"] -= consume
                remaining -= consume
                prop = consume / qty
                net_proceeds       = consume * price - comm * prop - tax * prop
                realized_pnl_piece = net_proceeds - consume * lot["cost_per_share"]
                allocations.append({
                    "lot_id":            lot["lot_id"],
                    "qty":               consume,
                    "buy_price":         lot["buy_price"],
                    "cost_per_share":    lot["cost_per_share"],
                    "realized_pnl_piece": round(realized_pnl_piece, 2),
                })

            open_lots = [lot for lot in open_lots if lot["qty_remaining"] > 0]

            if method != "wac":
                realized_breakdown.append({
                    "sell_trade_id": t["id"],
                    "sell_date":     t["date"],
                    "sell_qty":      qty,
                    "sell_price":    price,
                    "commission":    comm,
                    "tax":           tax,
                    "allocations":   allocations,
                })

    lps = ledger.last_price_with_source(sym, as_of)
    px  = lps["price"]

    result_lots: list[dict] = []
    for lot in open_lots:
        qty_rem  = lot["qty_remaining"]
        cost_ps  = avg_cost_wac if method == "wac" and avg_cost_wac > 0 else lot["cost_per_share"]
        mv       = round(qty_rem * px, 2) if px is not None else None
        tot_cost = round(qty_rem * cost_ps, 2)
        unreal   = round(mv - tot_cost, 2) if mv is not None else None
        unreal_pct = (
            round(unreal / tot_cost * 100, 2)
            if unreal is not None and tot_cost > 0 else None
        )
        underwater_pct = (
            round(max(0.0, (cost_ps - px) / cost_ps * 100), 2)
            if px is not None and cost_ps > 0 else None
        )
        result_lots.append({
            "lot_id":          lot["lot_id"],
            "buy_trade_id":    lot["buy_trade_id"],
            "buy_date":        lot["buy_date"],
            "qty_remaining":   qty_rem,
            "buy_price":       lot["buy_price"],
            "commission":      lot["commission"],
            "tax":             lot["tax"],
            "cost_per_share":  round(cost_ps, 4),
            "total_cost":      tot_cost,
            "market_price":    px,
            "market_value":    mv,
            "unrealized_pnl":  unreal,
            "unrealized_pct":  unreal_pct,
            "underwater_pct":  underwater_pct,
        })

    return {
        "symbol":            sym,
        "method":            method,
        "as_of":             as_of,
        "position_qty":      round(shares_wac, 6),
        "avg_cost_wac":      round(avg_cost_wac, 4) if shares_wac > 0 else None,
        "lots":              result_lots,
        "realized_breakdown": realized_breakdown,
    }
