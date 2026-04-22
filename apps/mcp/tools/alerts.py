"""Price alert MCP tools."""

from __future__ import annotations

import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH


def register(mcp: FastMCP) -> None:
    """Register price alert tools on the given MCP server instance."""

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
