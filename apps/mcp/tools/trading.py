"""Trade and cash operation MCP tools."""

from __future__ import annotations

import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH, _ledger


def register(mcp: FastMCP) -> None:
    """Register trading tools on the given MCP server instance."""

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
