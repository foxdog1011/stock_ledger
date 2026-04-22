"""Catalyst event tracking MCP tools."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH


def register(mcp: FastMCP) -> None:
    """Register catalyst tools on the given MCP server instance."""

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
