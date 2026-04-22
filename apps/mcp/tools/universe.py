"""Universe and watchlist MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH


def register(mcp: FastMCP) -> None:
    """Register universe and watchlist tools on the given MCP server instance."""

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
