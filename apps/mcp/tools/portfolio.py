"""Portfolio, position, equity, and lot-related MCP tools."""

from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import _ledger, _positions_dict


def register(mcp: FastMCP) -> None:
    """Register portfolio tools on the given MCP server instance."""

    @mcp.tool()
    def get_portfolio_snapshot(as_of: str | None = None) -> dict[str, Any]:
        """Return a high-level snapshot of the portfolio.

        Includes total equity, cash balance, aggregate market value, and the
        number of open positions.  Pass *as_of* (YYYY-MM-DD) to get a
        point-in-time view; omit it for the current state.

        Args:
            as_of: Optional date string (YYYY-MM-DD). Defaults to today.

        Returns:
            {
                "cash": float,
                "market_value": float,
                "total_equity": float,
                "position_count": int,
                "as_of": str,
            }
        """
        try:
            ledger = _ledger()
            positions = _positions_dict(ledger, as_of=as_of)
            bal = ledger.cash_balance(as_of=as_of)
            mv = sum(
                p["market_value"]
                for p in positions.values()
                if p.get("market_value") is not None
            )
            return {
                "cash": bal,
                "market_value": mv,
                "total_equity": bal + mv,
                "position_count": len(positions),
                "as_of": as_of or date.today().isoformat(),
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_portfolio_snapshot"}

    @mcp.tool()
    def get_positions(
        as_of: str | None = None,
        include_closed: bool = False,
    ) -> dict[str, Any]:
        """Return all portfolio positions with cost basis and P&L detail.

        Each entry contains: symbol, qty, avg_cost, last_price, market_value,
        unrealized_pnl, realized_pnl, and (where available) unrealized_pnl_pct.

        Args:
            as_of: Optional date string (YYYY-MM-DD). Defaults to today.
            include_closed: If True, also return positions whose qty is 0
                            (fully exited positions).

        Returns:
            {"positions": {symbol: {...}}, "count": int}
        """
        try:
            ledger = _ledger()
            raw = _positions_dict(ledger, as_of=as_of)
            if not include_closed:
                raw = {
                    sym: data
                    for sym, data in raw.items()
                    if (data.get("qty") or 0) != 0
                }
            return {
                "positions": raw,
                "count": len(raw),
                "as_of": as_of or date.today().isoformat(),
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_positions"}

    @mcp.tool()
    def get_cash_balance(as_of: str | None = None) -> dict[str, Any]:
        """Return the current (or historical) cash balance.

        Args:
            as_of: Optional date string (YYYY-MM-DD). Defaults to today.

        Returns:
            {"cash": float, "as_of": str}
        """
        try:
            ledger = _ledger()
            bal = ledger.cash_balance(as_of=as_of)
            return {
                "cash": bal,
                "as_of": as_of or date.today().isoformat(),
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_cash_balance"}

    @mcp.tool()
    def get_perf_summary(start: str, end: str) -> dict[str, Any]:
        """Return portfolio performance statistics over a date range.

        Computes metrics such as total return, annualised return, and drawdown
        by analysing daily equity values between *start* and *end*.

        Args:
            start: Start date string (YYYY-MM-DD), inclusive.
            end:   End date string (YYYY-MM-DD), inclusive.

        Returns:
            Performance summary dict with keys such as total_return,
            annualised_return, max_drawdown, sharpe_ratio (where computable).
        """
        try:
            from domain.portfolio.pnl import compute_perf_summary  # type: ignore

            ledger = _ledger()
            result = compute_perf_summary(ledger, start=start, end=end)
            return result if isinstance(result, dict) else {"summary": result}
        except ImportError:
            # Fallback: compute a simple return from daily equity series
            try:
                ledger = _ledger()
                equity_series = ledger.daily_equity(start, end)
                if not equity_series:
                    return {"error": "No equity data for the given range"}
                values = list(equity_series.values())
                first, last = values[0], values[-1]
                total_return = (last - first) / first if first else None
                return {
                    "start": start,
                    "end": end,
                    "start_equity": first,
                    "end_equity": last,
                    "total_return": total_return,
                    "data_points": len(values),
                }
            except Exception as inner_exc:
                return {"error": str(inner_exc), "tool": "get_perf_summary"}
        except Exception as exc:
            return {"error": str(exc), "tool": "get_perf_summary"}

    @mcp.tool()
    def get_rebalance_check(as_of: str | None = None) -> dict[str, Any]:
        """Check whether portfolio rebalancing is needed based on concentration limits.

        Computes each position's weight relative to total equity and flags any
        that exceed reasonable concentration thresholds (> 20% single name,
        etc.).

        Args:
            as_of: Optional date string (YYYY-MM-DD). Defaults to today.

        Returns:
            {
                "needs_rebalance": bool,
                "alerts": [...],
                "weights": {symbol: weight_pct},
                "as_of": str,
            }
        """
        try:
            ledger = _ledger()
            positions = _positions_dict(ledger, as_of=as_of)
            cash = ledger.cash_balance(as_of=as_of)

            mv = sum(
                p["market_value"]
                for p in positions.values()
                if p.get("market_value") is not None
            )
            total_equity = cash + mv

            weights: dict[str, float] = {}
            alerts: list[dict] = []

            if total_equity > 0:
                for sym, pos in positions.items():
                    if (pos.get("qty") or 0) == 0:
                        continue
                    pos_mv = pos.get("market_value") or 0
                    weight = pos_mv / total_equity
                    weights[sym] = round(weight * 100, 2)

                    if weight > 0.20:
                        alerts.append(
                            {
                                "symbol": sym,
                                "weight_pct": round(weight * 100, 2),
                                "message": f"{sym} is {weight*100:.1f}% of portfolio (>20% threshold)",
                                "severity": "high" if weight > 0.30 else "medium",
                            }
                        )

                cash_weight = cash / total_equity
                if cash_weight > 0.40:
                    alerts.append(
                        {
                            "symbol": "CASH",
                            "weight_pct": round(cash_weight * 100, 2),
                            "message": f"Cash is {cash_weight*100:.1f}% of portfolio (>40%)",
                            "severity": "low",
                        }
                    )

            return {
                "needs_rebalance": len(alerts) > 0,
                "alerts": alerts,
                "weights": weights,
                "cash_pct": round(cash / total_equity * 100, 2) if total_equity else 0,
                "total_equity": total_equity,
                "as_of": as_of or date.today().isoformat(),
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_rebalance_check"}

    @mcp.tool()
    def get_lots(
        symbol: str,
        method: str = "fifo",
    ) -> dict[str, Any]:
        """Return lot-level position detail for a symbol using the specified cost method.

        Args:
            symbol: Ticker symbol (case-insensitive).
            method: Cost method — "fifo", "lifo", or "avg" (default "fifo").

        Returns:
            Lot detail dict as returned by the ledger's lots_by_method.
        """
        try:
            if method not in ("fifo", "lifo", "avg"):
                return {
                    "error": f"Invalid method '{method}'. Must be 'fifo', 'lifo', or 'avg'.",
                    "tool": "get_lots",
                }
            ledger = _ledger()
            return ledger.lots_by_method(symbol=symbol.upper(), method=method)
        except Exception as exc:
            return {"error": str(exc), "tool": "get_lots"}
