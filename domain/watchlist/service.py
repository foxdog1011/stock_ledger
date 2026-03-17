"""Watchlist service: coverage check and gap analysis.

These functions require both db_path (watchlist data) and a StockLedger
instance (active positions).
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from domain.portfolio.pnl import all_positions_pnl
from .repository import get_watchlist, list_watchlist_items

if TYPE_CHECKING:
    from ledger import StockLedger


def _coverage_core(
    db_path: Path,
    watchlist_id: int,
    ledger: "StockLedger",
) -> tuple[dict, int, int, int]:
    """
    Shared computation for coverage and gaps.

    Returns (watchlist, active_position_count, current_active_item_count, gap).
    Raises ValueError if watchlist_id is not found.
    """
    watchlist = get_watchlist(db_path, watchlist_id)
    if watchlist is None:
        raise ValueError(f"Watchlist {watchlist_id} not found")

    positions = all_positions_pnl(ledger, open_only=True)
    active_position_count = len(positions)

    items = list_watchlist_items(db_path, watchlist_id, include_archived=False)
    current_active_item_count = len(items)

    required = active_position_count * 3
    gap = max(0, required - current_active_item_count)

    return watchlist, active_position_count, current_active_item_count, gap


def get_watchlist_coverage(
    db_path: Path,
    watchlist_id: int,
    ledger: "StockLedger",
) -> dict:
    """
    Return coverage summary for a watchlist.

    coverage_sufficient = current_active_item_count >= active_position_count * 3
    """
    watchlist, active_pos, active_items, gap = _coverage_core(
        db_path, watchlist_id, ledger
    )
    required = active_pos * 3
    return {
        "watchlist_id":              watchlist_id,
        "watchlist_name":            watchlist["name"],
        "active_position_count":     active_pos,
        "required_watchlist_count":  required,
        "current_active_item_count": active_items,
        "coverage_sufficient":       active_items >= required,
        "gap":                       gap,
    }


def list_watchlist_gaps(
    db_path: Path,
    watchlist_id: int,
    ledger: "StockLedger",
) -> dict:
    """
    Return coverage summary plus per-symbol gap analysis.

    positions_not_in_watchlist : active position symbols absent from this watchlist
    positions_in_watchlist     : active position symbols already in this watchlist
    """
    watchlist, active_pos, active_items, gap = _coverage_core(
        db_path, watchlist_id, ledger
    )
    required = active_pos * 3

    positions = all_positions_pnl(ledger, open_only=True)
    position_symbols = {p["symbol"] for p in positions}

    items = list_watchlist_items(db_path, watchlist_id, include_archived=False)
    watchlist_symbols = {item["symbol"] for item in items}

    return {
        "watchlist_id":                watchlist_id,
        "watchlist_name":              watchlist["name"],
        "active_position_count":       active_pos,
        "required_watchlist_count":    required,
        "current_active_item_count":   active_items,
        "coverage_sufficient":         active_items >= required,
        "gap":                         gap,
        "positions_not_in_watchlist":  sorted(position_symbols - watchlist_symbols),
        "positions_in_watchlist":      sorted(position_symbols & watchlist_symbols),
    }
