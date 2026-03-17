"""Adjusted cost-basis risk view per position.

Public API
----------
position_adjusted_risk(ledger, symbol, as_of) -> dict
all_positions_adjusted_risk(ledger, as_of, open_only=True) -> list[dict]

position_state values
---------------------
"risk_free"    qty > 0 and realized_pnl >= cost_basis_remaining
"at_risk"      qty > 0 and realized_pnl <  cost_basis_remaining
"closed"       qty == 0 and the symbol has trade history
"no_position"  qty == 0 and no trade history for the symbol

Design notes
------------
- Calls position_pnl() from domain.portfolio.pnl; no additional DB write.
- The only extra DB query is a COUNT check for the "closed" vs "no_position"
  distinction (qty == 0 path only).
- StockLedger is imported under TYPE_CHECKING to avoid circular imports.
"""
from __future__ import annotations

from datetime import date as Date
from typing import TYPE_CHECKING

from ledger.db import get_connection
from domain.portfolio.pnl import position_pnl

if TYPE_CHECKING:
    from ledger import StockLedger


def _total_pnl(
    position_state: str,
    realized_pnl: float,
    unrealized_pnl: float | None,
) -> float | None:
    """Compute total_pnl according to position_state rules."""
    if position_state in ("risk_free", "at_risk"):
        if unrealized_pnl is None:
            return None
        return round(realized_pnl + unrealized_pnl, 2)
    if position_state == "closed":
        return realized_pnl   # may be positive, negative, or 0.0
    # "no_position"
    return None


def position_adjusted_risk(
    ledger: "StockLedger",
    symbol: str,
    as_of: str | Date | None = None,
) -> dict:
    """
    Return the adjusted cost-basis risk view for *symbol*.

    All position_pnl fields are preserved verbatim; the following fields
    are added:

        position_state, cost_basis_remaining, net_at_risk,
        pct_recovered, amount_to_recover, total_pnl
    """
    pnl          = position_pnl(ledger, symbol, as_of)
    qty          = pnl["qty"]
    realized_pnl = pnl["realized_pnl"]
    unrealized   = pnl["unrealized_pnl"]

    if qty == 0:
        sym_upper = symbol.upper()
        conn = get_connection(ledger.db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM trades WHERE symbol = ? AND is_void = 0",
                (sym_upper,),
            ).fetchone()
            count = row[0]
        finally:
            conn.close()

        position_state       = "closed" if count > 0 else "no_position"
        cost_basis_remaining = None
        net_at_risk          = None
        pct_recovered        = None
        amount_to_recover    = None

    else:  # qty > 0
        avg_cost = pnl.get("avg_cost")

        # Defensive: avg_cost should exist for any open position, but guard
        # against corrupt data (e.g. only sells recorded, no buys).
        if avg_cost is None or avg_cost <= 0:
            position_state       = "at_risk"
            cost_basis_remaining = None
            net_at_risk          = None
            pct_recovered        = None
            amount_to_recover    = None
        else:
            cost_basis_remaining = round(avg_cost * qty, 2)
            net_at_risk          = round(cost_basis_remaining - realized_pnl, 2)
            position_state       = "risk_free" if net_at_risk <= 0 else "at_risk"
            pct_recovered        = round(realized_pnl / cost_basis_remaining * 100, 2)
            amount_to_recover    = round(max(0.0, net_at_risk), 2)

    return {
        **pnl,
        "position_state":       position_state,
        "cost_basis_remaining": cost_basis_remaining,
        "net_at_risk":          net_at_risk,
        "pct_recovered":        pct_recovered,
        "amount_to_recover":    amount_to_recover,
        "total_pnl":            _total_pnl(position_state, realized_pnl, unrealized),
    }


def all_positions_adjusted_risk(
    ledger: "StockLedger",
    as_of: str | Date | None = None,
    open_only: bool = True,
) -> list[dict]:
    """
    Return position_adjusted_risk for every symbol that has ever had a trade.

    Parameters
    ----------
    open_only : bool
        If True (default), only symbols with position_state in
        ("risk_free", "at_risk") are returned.

    Output order: sorted by symbol (ORDER BY symbol from SQL query).
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

    results = [position_adjusted_risk(ledger, sym, as_of) for sym in symbols]

    if open_only:
        results = [r for r in results if r["position_state"] in ("risk_free", "at_risk")]

    return results
