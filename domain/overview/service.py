"""Overview service: aggregation layer for the dashboard.

This module is a pure orchestration / aggregation layer.
It does NOT implement any business logic — it delegates entirely to
existing domain functions and reshapes their output into one payload.

Dependency map
--------------
portfolio         ← ledger.equity_snapshot(), domain.portfolio.pnl.all_positions_pnl()
risk              ← domain.risk.adjusted.all_positions_adjusted_risk()
watchlist_coverage← domain.watchlist.repository.list_watchlists()
                    domain.watchlist.service.get_watchlist_coverage()
upcoming_catalysts← domain.catalyst.service.upcoming_catalysts()
offsetting        ← domain.execution.offsetting.losing_positions()
                    domain.execution.offsetting.profit_inventory()
"""
from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ledger import StockLedger


def build_overview(
    db_path: Path,
    ledger: "StockLedger",
    as_of: str | None = None,
    catalyst_days: int = 30,
) -> dict:
    """
    Build and return the full overview / dashboard payload.

    Parameters
    ----------
    db_path:        Path to the SQLite database (used by domain modules that
                    accept db_path directly).
    ledger:         StockLedger instance (used by portfolio, risk, execution).
    as_of:          Date string YYYY-MM-DD.  Defaults to today.
    catalyst_days:  Inclusive window for upcoming catalysts.
                    catalyst_days=0 means only events on as_of itself.
    """
    if as_of is None:
        as_of = datetime.date.today().isoformat()

    generated_at = datetime.datetime.now().isoformat(timespec="seconds")

    return {
        "portfolio":           _portfolio_section(ledger, as_of),
        "risk":                _risk_section(ledger, as_of),
        "watchlist_coverage":  _watchlist_coverage_section(db_path, ledger, as_of),
        "upcoming_catalysts":  _upcoming_catalysts_section(db_path, as_of, catalyst_days),
        "offsetting":          _offsetting_section(ledger, as_of),
        "generated_at":        generated_at,
        "as_of":               as_of,
    }


# ── section builders ──────────────────────────────────────────────────────────

def _portfolio_section(ledger: "StockLedger", as_of: str) -> dict:
    """Aggregate portfolio summary from equity_snapshot + all_positions_pnl."""
    from domain.portfolio.pnl import all_positions_pnl

    snap = ledger.equity_snapshot(as_of=as_of)
    positions = all_positions_pnl(ledger, as_of=as_of, open_only=True)

    # avg_cost is per-share; multiply by qty for position cost basis.
    # avg_cost is None only when qty==0 (closed), which open_only=True excludes.
    total_cost   = sum(
        (p["avg_cost"] or 0.0) * p["qty"] for p in positions
    )
    realized_pnl = sum(p["realized_pnl"] for p in positions)

    # Conservative rule: if any position has unrealized_pnl = None,
    # the aggregate is None.
    unrealized_pnl: float | None
    if any(p["unrealized_pnl"] is None for p in positions):
        unrealized_pnl = None
    else:
        unrealized_pnl = sum(p["unrealized_pnl"] for p in positions)  # type: ignore[misc]

    unrealized_pct: float | None
    if unrealized_pnl is None or total_cost == 0:
        unrealized_pct = None
    else:
        unrealized_pct = unrealized_pnl / total_cost * 100

    return {
        "total_equity":   snap["total_equity"],
        "cash":           snap["cash"],
        "market_value":   snap["market_value"],
        "total_cost":     total_cost,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pct": unrealized_pct,
        "realized_pnl":   realized_pnl,
        "position_count": len(positions),
        "as_of":          as_of,
    }


def _risk_section(ledger: "StockLedger", as_of: str) -> dict:
    """Aggregate risk summary from all_positions_adjusted_risk."""
    from domain.risk.adjusted import all_positions_adjusted_risk

    risk_rows = all_positions_adjusted_risk(ledger, as_of=as_of, open_only=True)

    at_risk_count  = sum(1 for r in risk_rows if r["position_state"] == "at_risk")
    risk_free_count = sum(1 for r in risk_rows if r["position_state"] == "risk_free")

    # Conservative: if any net_at_risk is None, total is None
    total_net_at_risk: float | None
    if any(r["net_at_risk"] is None for r in risk_rows):
        total_net_at_risk = None
    else:
        total_net_at_risk = sum(r["net_at_risk"] for r in risk_rows)  # type: ignore[misc]

    positions = [
        {
            "symbol":         r["symbol"],
            "position_state": r["position_state"],
            "net_at_risk":    r["net_at_risk"],
            "pct_recovered":  r["pct_recovered"],
        }
        for r in sorted(
            risk_rows,
            key=lambda x: (x["net_at_risk"] is None, -(x["net_at_risk"] or 0)),
        )
    ]

    return {
        "at_risk_count":     at_risk_count,
        "risk_free_count":   risk_free_count,
        "total_net_at_risk": total_net_at_risk,
        "positions":         positions,
    }


def _watchlist_coverage_section(
    db_path: Path,
    ledger: "StockLedger",
    as_of: str,
) -> dict:
    """Aggregate watchlist coverage across all watchlists."""
    from domain.watchlist.repository import list_watchlists
    from domain.watchlist.service import get_watchlist_coverage

    watchlists = list_watchlists(db_path)
    coverage_rows = []
    for wl in watchlists:
        cov = get_watchlist_coverage(db_path, wl["id"], ledger)
        coverage_rows.append({
            "watchlist_id":              cov["watchlist_id"],
            "watchlist_name":            cov["watchlist_name"],
            "active_position_count":     cov["active_position_count"],
            "required_watchlist_count":  cov["required_watchlist_count"],
            "current_active_item_count": cov["current_active_item_count"],
            "coverage_sufficient":       cov["coverage_sufficient"],
            "gap":                       cov["gap"],
        })

    any_insufficient = any(not r["coverage_sufficient"] for r in coverage_rows)

    return {
        "watchlists":      coverage_rows,
        "any_insufficient": any_insufficient,
    }


def _upcoming_catalysts_section(
    db_path: Path,
    as_of: str,
    days: int,
) -> dict:
    """Aggregate upcoming catalysts within [as_of, as_of+days] (inclusive)."""
    from domain.catalyst.service import upcoming_catalysts

    items_raw = upcoming_catalysts(db_path, as_of=as_of, days=days)

    items = [
        {
            "id":           c["id"],
            "event_type":   c["event_type"],
            "symbol":       c["symbol"],
            "title":        c["title"],
            "event_date":   c["event_date"],
            "has_scenario": c["scenario"] is not None,
        }
        for c in items_raw
    ]

    return {
        "days_window": days,
        "count":       len(items),
        "items":       items,
    }


def _offsetting_section(ledger: "StockLedger", as_of: str) -> dict:
    """
    Aggregate offsetting summary from losing_positions + profit_inventory.

    total_unrealized_loss: sum of unrealized_pnl for all losing positions.
        This value is always <= 0.0.  (0.0 when no losing positions.)
    net_offset_capacity: profit_available + total_unrealized_loss.
        Positive means available profit exceeds total losses.
    """
    from domain.execution.offsetting import losing_positions, profit_inventory

    losers  = losing_positions(ledger, as_of=as_of)
    inv     = profit_inventory(ledger, as_of=as_of)

    # total_unrealized_loss is negative (or 0.0)
    total_unrealized_loss = sum(p["unrealized_pnl"] for p in losers) if losers else 0.0
    profit_available      = inv["summary"]["available_to_offset"]
    net_offset_capacity   = profit_available + total_unrealized_loss

    return {
        "losing_count":          len(losers),
        "total_unrealized_loss": total_unrealized_loss,   # <= 0.0
        "profit_available":      profit_available,
        "net_offset_capacity":   net_offset_capacity,
    }
