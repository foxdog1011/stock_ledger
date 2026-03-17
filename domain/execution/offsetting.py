"""Profit-loss offsetting simulation.

Public API
----------
losing_positions(ledger, as_of=None) -> list[dict]
profit_inventory(ledger, as_of=None) -> dict
simulate_offsetting(ledger, symbol, qty=None, price=None, as_of=None) -> dict

Design notes
------------
- Pure read-only simulation; nothing is written to the ledger.
- Depends on domain.portfolio.pnl functions only — no direct DB access
  except via those functions.
- StockLedger is imported under TYPE_CHECKING to avoid circular imports.
"""
from __future__ import annotations

from datetime import date as Date
from typing import TYPE_CHECKING

from domain.portfolio.pnl import position_pnl, all_positions_pnl

if TYPE_CHECKING:
    from ledger import StockLedger


def losing_positions(
    ledger: "StockLedger",
    as_of: str | Date | None = None,
) -> list[dict]:
    """
    Return all open positions whose unrealized P&L is negative.

    Sorted by unrealized_pnl ascending (largest loss first).
    """
    rows = all_positions_pnl(ledger, as_of=as_of, open_only=True)
    result = []
    for r in rows:
        unreal = r["unrealized_pnl"]
        if unreal is None or unreal >= 0:
            continue
        avg_cost = r["avg_cost"]
        last_price = r["last_price"]
        unreal_pct = (
            round((last_price - avg_cost) / avg_cost * 100, 2)
            if (last_price is not None and avg_cost and avg_cost > 0)
            else None
        )
        result.append({
            "symbol":            r["symbol"],
            "qty":               r["qty"],
            "avg_cost":          avg_cost,
            "last_price":        last_price,
            "unrealized_pnl":    unreal,
            "unrealized_pct":    unreal_pct,
            "loss_if_full_exit": round(abs(unreal), 2),
        })
    result.sort(key=lambda x: x["unrealized_pnl"])
    return result


def profit_inventory(
    ledger: "StockLedger",
    as_of: str | Date | None = None,
) -> dict:
    """
    Return realized P&L summary and per-symbol breakdown.

    summary
        gross_realized_pnl    : net realized P&L across all symbols
        positive_realized_pnl : sum of positive realized P&L only
        available_to_offset   : max(0, gross_realized_pnl)

    by_symbol
        List of {symbol, realized_pnl, qty}, sorted by realized_pnl desc.
    """
    rows = all_positions_pnl(ledger, as_of=as_of, open_only=False)
    by_symbol = [
        {
            "symbol":       r["symbol"],
            "realized_pnl": r["realized_pnl"],
            "qty":          r["qty"],
        }
        for r in rows
    ]
    by_symbol.sort(key=lambda x: x["realized_pnl"], reverse=True)

    gross = round(sum(r["realized_pnl"] for r in rows), 2)
    pos   = round(sum(r["realized_pnl"] for r in rows if r["realized_pnl"] > 0), 2)
    avail = round(max(0.0, gross), 2)

    return {
        "summary": {
            "gross_realized_pnl":    gross,
            "positive_realized_pnl": pos,
            "available_to_offset":   avail,
        },
        "by_symbol": by_symbol,
    }


def _check_guardrail(
    sim_price: float | None,
    sim_qty: float,
    current_qty: float,
    sim_realized_loss: float | None,
    projected: float | None,
) -> dict:
    if sim_price is None:
        return {"passed": False, "reason": "no_price", "warnings": []}
    if sim_qty > current_qty:
        return {"passed": False, "reason": "qty_exceeds_position", "warnings": []}
    if sim_realized_loss is None or sim_realized_loss >= 0:
        return {"passed": False, "reason": "not_a_loss", "warnings": []}
    if projected is not None and projected < 0:
        return {"passed": False, "reason": "over_offset", "warnings": []}
    return {"passed": True, "reason": None, "warnings": []}


def simulate_offsetting(
    ledger: "StockLedger",
    symbol: str,
    qty: float | None = None,
    price: float | None = None,
    as_of: str | Date | None = None,
) -> dict:
    """
    Simulate selling *qty* shares of *symbol* at *price* as an offsetting trade.

    qty   defaults to the full current position.
    price defaults to last_price.

    Nothing is written to the ledger.
    """
    as_of = str(as_of) if as_of else str(Date.today())

    pnl        = position_pnl(ledger, symbol, as_of)
    avg_cost   = pnl["avg_cost"]
    unreal     = pnl["unrealized_pnl"]
    last_price = pnl["last_price"]

    sim_qty   = qty   if qty   is not None else pnl["qty"]
    sim_price = price if price is not None else last_price

    # ── losing_position section ──────────────────────────────────────────
    lp: dict | None = None
    if unreal is not None and unreal < 0:
        unreal_pct = (
            round((last_price - avg_cost) / avg_cost * 100, 2)
            if (last_price is not None and avg_cost and avg_cost > 0)
            else None
        )
        lp = {
            "symbol":            pnl["symbol"],
            "qty":               pnl["qty"],
            "avg_cost":          avg_cost,
            "last_price":        last_price,
            "unrealized_pnl":    unreal,
            "unrealized_pct":    unreal_pct,
            "loss_if_full_exit": round(abs(unreal), 2),
        }

    # ── profit_inventory section ─────────────────────────────────────────
    pi    = profit_inventory(ledger, as_of)
    avail = pi["summary"]["available_to_offset"]
    gross = pi["summary"]["gross_realized_pnl"]

    # ── simulation section ───────────────────────────────────────────────
    if sim_price is not None and avg_cost is not None:
        sim_realized_loss = round((sim_price - avg_cost) * sim_qty, 2)
        matched_amount    = round(min(abs(sim_realized_loss), avail), 2)
        projected         = round(gross + sim_realized_loss, 2)
    else:
        sim_realized_loss = None
        matched_amount    = None
        projected         = None

    # ── guardrail ────────────────────────────────────────────────────────
    guardrail = _check_guardrail(
        sim_price, sim_qty, pnl["qty"], sim_realized_loss, projected
    )

    return {
        "as_of":            as_of,
        "losing_position":  lp,
        "profit_inventory": pi,
        "simulation": {
            "symbol":                       pnl["symbol"],
            "sim_qty":                      sim_qty,
            "sim_price":                    sim_price,
            "sim_realized_loss":            sim_realized_loss,
            "matched_amount":               matched_amount,
            "projected_gross_realized_pnl": projected,
            "commission_not_included":      True,
        },
        "guardrail": guardrail,
    }
