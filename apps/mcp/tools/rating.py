"""Investment rating and scenario MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH


def register(mcp: FastMCP) -> None:
    """Register rating tools on the given MCP server instance."""

    @mcp.tool()
    def get_investment_rating(symbol: str) -> dict[str, Any]:
        """Get the investment rating for a stock (Buy/Hold/Sell + target price).

        Args:
            symbol: Stock ticker.

        Returns:
            Rating with target_price, stop_loss, thesis, confidence.
        """
        try:
            from domain.rating.repository import get_rating
            result = get_rating(DB_PATH, symbol.upper())
            if not result:
                return {"symbol": symbol.upper(), "rating": None, "message": "No rating set"}
            return result
        except Exception as exc:
            return {"error": str(exc), "tool": "get_investment_rating"}

    @mcp.tool()
    def set_investment_rating(
        symbol: str,
        rating: str,
        target_price: float | None = None,
        stop_loss: float | None = None,
        thesis: str = "",
        confidence: float = 0.5,
    ) -> dict[str, Any]:
        """Set an investment rating for a stock.

        Args:
            symbol: Stock ticker.
            rating: "strong_buy", "buy", "hold", "sell", or "strong_sell".
            target_price: 12-month target price.
            stop_loss: Stop-loss price.
            thesis: Investment thesis text.
            confidence: Confidence level 0-1 (default 0.5).

        Returns:
            The saved rating record.
        """
        try:
            from domain.rating.repository import upsert_rating
            return upsert_rating(
                DB_PATH, symbol.upper(), rating,
                target_price=target_price, stop_loss=stop_loss,
                thesis=thesis, confidence=confidence,
            )
        except Exception as exc:
            return {"error": str(exc), "tool": "set_investment_rating"}

    @mcp.tool()
    def set_scenario(
        symbol: str,
        scenario_name: str,
        target_price: float,
        probability: float,
        thesis: str = "",
    ) -> dict[str, Any]:
        """Set a bull/base/bear quantitative scenario for a stock.

        Args:
            symbol: Stock ticker.
            scenario_name: e.g. "bull", "base", "bear".
            target_price: Target price for this scenario.
            probability: Probability 0-1.
            thesis: Scenario description.

        Returns:
            The saved scenario record.
        """
        try:
            from domain.rating.repository import upsert_scenario_q
            return upsert_scenario_q(DB_PATH, symbol.upper(), scenario_name, target_price, probability, thesis)
        except Exception as exc:
            return {"error": str(exc), "tool": "set_scenario"}

    @mcp.tool()
    def get_expected_value(
        symbol: str,
        current_price: float,
    ) -> dict[str, Any]:
        """Compute probability-weighted expected value from bull/base/bear scenarios.

        Args:
            symbol: Stock ticker.
            current_price: Current market price for return calculation.

        Returns:
            Expected price, expected return %, and scenario breakdown.
        """
        try:
            from domain.rating.repository import compute_expected_value
            return compute_expected_value(DB_PATH, symbol.upper(), current_price)
        except Exception as exc:
            return {"error": str(exc), "tool": "get_expected_value"}
