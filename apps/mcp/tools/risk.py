"""Risk analysis and benchmark comparison MCP tools."""

from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH, _ledger


def register(mcp: FastMCP) -> None:
    """Register risk tools on the given MCP server instance."""

    @mcp.tool()
    def get_risk_metrics(as_of: str | None = None) -> dict[str, Any]:
        """Return adjusted cost-basis risk metrics for all open positions.

        Uses the domain risk module to compute concentration, downside exposure,
        and adjusted cost basis per position.

        Args:
            as_of: Optional date string (YYYY-MM-DD). Defaults to today.

        Returns:
            Risk metrics dict keyed by symbol.
        """
        try:
            from domain.risk.adjusted import all_positions_adjusted_risk  # type: ignore

            ledger = _ledger()
            result = all_positions_adjusted_risk(ledger, as_of=as_of)
            return result if isinstance(result, dict) else {"risk_metrics": result}
        except Exception as exc:
            return {"error": str(exc), "tool": "get_risk_metrics"}

    @mcp.tool()
    def compare_benchmark(
        bench: str = "0050",
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """Compare portfolio performance against a benchmark index.

        Computes cumulative return comparison, tracking error, correlation,
        and information ratio between the portfolio and a benchmark.

        Available benchmarks: 0050 (Taiwan 50 ETF), TAIEX (Taiwan Index),
        0056 (High Dividend ETF), SPY, QQQ.
        Note: bootstrap the benchmark data first via POST /benchmark/bootstrap
        if you haven't done so.

        Args:
            bench: Benchmark ticker — "0050", "TAIEX", "0056", "SPY", "QQQ", etc.
            start: Start date YYYY-MM-DD (default: 1 year ago).
            end:   End date YYYY-MM-DD (default: today).

        Returns:
            Dict with metrics (excess_return_pct, tracking_error, correlation,
            information_ratio) and most-recent comparison data point.
        """
        try:
            import pandas as pd
            from ledger.equity import equity_curve as _portfolio_curve

            today = date.today()
            end_str   = end   or today.isoformat()
            start_str = start or (today - timedelta(days=365)).isoformat()

            ledger = _ledger()

            # Fetch portfolio equity curve (monthly)
            port_df = _portfolio_curve(ledger, start=start_str, end=end_str, freq="ME")
            if port_df is None or port_df.empty:
                return {"error": "No portfolio equity data in range", "tool": "compare_benchmark"}

            port_df.index = pd.to_datetime(port_df.index)
            valid_mask = port_df["total_equity"] > 0
            if not valid_mask.any():
                return {"error": "Portfolio has no equity in requested range", "tool": "compare_benchmark"}

            first_valid = port_df.index[valid_mask][0]
            port_df = port_df[port_df.index >= first_valid].copy()
            base_equity = port_df["total_equity"].iloc[0]
            if base_equity == 0:
                return {"error": "Portfolio starting equity is zero", "tool": "compare_benchmark"}
            port_df["cum_return_pct"] = (port_df["total_equity"] / base_equity - 1) * 100

            # Fetch benchmark prices from DB
            with sqlite3.connect(DB_PATH) as con:
                rows = con.execute(
                    "SELECT date, close FROM prices WHERE ticker=? AND date BETWEEN ? AND ? ORDER BY date",
                    (bench.upper(), start_str, end_str),
                ).fetchall()

            if not rows:
                return {
                    "error": f"No benchmark data for '{bench}' — run POST /benchmark/bootstrap first",
                    "tool": "compare_benchmark",
                }

            bench_s = pd.Series(
                {pd.Timestamp(r[0]): float(r[1]) for r in rows},
                dtype=float,
            ).resample("ME").last().dropna()

            bench_aligned = bench_s[bench_s.index >= first_valid]
            if bench_aligned.empty:
                return {"error": f"No benchmark data for '{bench}' after portfolio start", "tool": "compare_benchmark"}

            base_bench = bench_aligned.iloc[0]
            bench_cum  = (bench_aligned / base_bench - 1) * 100

            aligned = pd.DataFrame({"portfolio": port_df["cum_return_pct"], "bench": bench_cum}).dropna()
            if aligned.empty:
                return {"error": "No overlapping dates between portfolio and benchmark", "tool": "compare_benchmark"}

            aligned["excess"] = aligned["portfolio"] - aligned["bench"]
            latest = aligned.iloc[-1]

            # Metrics
            ann = 12  # monthly
            metrics: dict[str, Any] = {
                "excess_return_pct": round(float(latest["excess"]), 2),
                "portfolio_cum_return_pct": round(float(latest["portfolio"]), 2),
                "bench_cum_return_pct": round(float(latest["bench"]), 2),
            }
            try:
                port_p  = port_df["total_equity"].pct_change().dropna() * 100
                bench_p = bench_aligned.pct_change().dropna() * 100
                pf = pd.DataFrame({"p": port_p, "b": bench_p}).dropna()
                if len(pf) >= 2:
                    excess_p = pf["p"] - pf["b"]
                    te = float(excess_p.std()) * math.sqrt(ann)
                    if not math.isnan(te):
                        metrics["tracking_error_annualized"] = round(te, 4)
                    corr = float(pf["p"].corr(pf["b"]))
                    if not math.isnan(corr):
                        metrics["correlation"] = round(corr, 4)
                    if metrics.get("tracking_error_annualized", 0) > 0:
                        ir = float(excess_p.mean()) * ann / metrics["tracking_error_annualized"]
                        if not math.isnan(ir):
                            metrics["information_ratio"] = round(ir, 4)
            except Exception:
                pass

            return {
                "bench": bench.upper(),
                "start": start_str,
                "end": end_str,
                "metrics": metrics,
                "interpretation": (
                    "outperforming" if metrics["excess_return_pct"] > 0 else "underperforming"
                ),
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "compare_benchmark"}

    @mcp.tool()
    def get_beta(
        symbol: str,
        benchmark: str = "0050",
    ) -> dict[str, Any]:
        """Calculate Beta coefficient for a stock vs a benchmark.

        Beta measures systematic risk relative to the market.
        Beta > 1 = more volatile, Beta < 1 = less volatile.

        Args:
            symbol: Stock ticker.
            benchmark: Benchmark ticker (default "0050").

        Returns:
            Beta, alpha, correlation, R², and interpretation.
        """
        try:
            import urllib.request, json
            url = f"http://localhost:8000/api/beta/{symbol.upper()}?bench={benchmark}"
            resp = urllib.request.urlopen(url, timeout=30)
            return json.loads(resp.read())
        except Exception as exc:
            return {"error": str(exc), "tool": "get_beta"}
