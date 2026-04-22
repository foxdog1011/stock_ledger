"""Financial statements, valuation, dividends, DCF, and PE band MCP tools."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH


def register(mcp: FastMCP) -> None:
    """Register financial tools on the given MCP server instance."""

    @mcp.tool()
    def get_financial_statements(
        symbol: str,
        statement_type: str = "income",
        limit: int = 8,
    ) -> dict[str, Any]:
        """Get quarterly financial statements for a Taiwan stock.

        Returns income statement, balance sheet, or cash flow data grouped by quarter.

        Args:
            symbol: Taiwan stock ticker (e.g. "2337").
            statement_type: "income", "balance", or "cashflow".
            limit: Max number of quarters to return (default 8).

        Returns:
            Quarterly financial data with fields like 營業收入, 營業利益, 淨利, EPS etc.
        """
        try:
            from domain.financials.repository import get_financial_statements as _get
            data = _get(DB_PATH, symbol.upper(), statement_type, limit)
            return {"symbol": symbol.upper(), "type": statement_type, "count": len(data), "data": data}
        except Exception as exc:
            return {"error": str(exc), "tool": "get_financial_statements"}

    @mcp.tool()
    def fetch_fundamentals(
        symbol: str,
        start_date: str = "2020-01-01",
    ) -> dict[str, Any]:
        """Fetch all fundamental data for a stock from FinMind (one-click).

        Downloads: income statement, balance sheet, cash flow, PER/PBR,
        dividends. Stores everything in local database for fast querying.

        Args:
            symbol: Taiwan stock ticker (e.g. "2337").
            start_date: How far back to fetch (YYYY-MM-DD, default 2020-01-01).

        Returns:
            Summary of fetched/stored records per data type.
        """
        try:
            import json, urllib.parse, urllib.request
            from domain.financials.repository import (
                store_financial_rows, store_valuation_rows, store_dividend_rows,
            )

            sym = symbol.upper()
            _FM_URL = "https://api.finmindtrade.com/api/v4/data"
            _HDR = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            token = os.getenv("FINMIND_TOKEN", "").strip()

            def _fm(dataset: str) -> list[dict]:
                params: dict = {"dataset": dataset, "data_id": sym, "start_date": start_date}
                if token:
                    params["token"] = token
                url = f"{_FM_URL}?{urllib.parse.urlencode(params)}"
                req = urllib.request.Request(url, headers=_HDR)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    d = json.loads(resp.read())
                if d.get("status") != 200:
                    raise ValueError(d.get("msg", "unknown"))
                return d.get("data", [])

            results = {}
            for st, ds in [("income", "TaiwanStockFinancialStatements"),
                           ("balance", "TaiwanStockBalanceSheet"),
                           ("cashflow", "TaiwanStockCashFlowsStatement")]:
                try:
                    rows = _fm(ds)
                    n = store_financial_rows(DB_PATH, sym, st, rows)
                    results[st] = {"fetched": len(rows), "stored": n}
                except Exception as e:
                    results[st] = {"error": str(e)}

            try:
                rows = _fm("TaiwanStockPER")
                n = store_valuation_rows(DB_PATH, sym, rows)
                results["valuation"] = {"fetched": len(rows), "stored": n}
            except Exception as e:
                results["valuation"] = {"error": str(e)}

            try:
                rows = _fm("TaiwanStockDividend")
                n = store_dividend_rows(DB_PATH, sym, rows)
                results["dividends"] = {"fetched": len(rows), "stored": n}
            except Exception as e:
                results["dividends"] = {"error": str(e)}

            return {"symbol": sym, "results": results}
        except Exception as exc:
            return {"error": str(exc), "tool": "fetch_fundamentals"}

    @mcp.tool()
    def get_valuation_metrics(
        symbol: str,
        limit: int = 30,
    ) -> dict[str, Any]:
        """Get PER/PBR/dividend yield history with summary statistics.

        Args:
            symbol: Taiwan stock ticker.
            limit: Number of recent data points (default 30).

        Returns:
            Latest and historical PER/PBR with avg/min/max stats.
        """
        try:
            from domain.financials.repository import get_valuation_metrics as _get
            data = _get(DB_PATH, symbol.upper(), limit)
            if not data:
                return {"symbol": symbol.upper(), "count": 0, "data": [], "summary": None}

            pers = [d["per"] for d in data if d["per"] and d["per"] > 0]
            pbrs = [d["pbr"] for d in data if d["pbr"] and d["pbr"] > 0]
            return {
                "symbol": symbol.upper(),
                "count": len(data),
                "data": data[:10],
                "summary": {
                    "latest_per": data[0]["per"],
                    "latest_pbr": data[0]["pbr"],
                    "latest_dividend_yield": data[0]["dividend_yield"],
                    "per_avg": round(sum(pers) / len(pers), 2) if pers else None,
                    "per_min": round(min(pers), 2) if pers else None,
                    "per_max": round(max(pers), 2) if pers else None,
                    "pbr_avg": round(sum(pbrs) / len(pbrs), 2) if pbrs else None,
                },
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_valuation_metrics"}

    @mcp.tool()
    def get_dividends(symbol: str) -> dict[str, Any]:
        """Get dividend history for a Taiwan stock.

        Args:
            symbol: Taiwan stock ticker.

        Returns:
            Dividend records with cash/stock amounts and summary stats.
        """
        try:
            from domain.financials.repository import get_dividend_history
            data = get_dividend_history(DB_PATH, symbol.upper(), 20)
            total_cash = sum(d["cash_dividend"] or 0 for d in data)
            return {
                "symbol": symbol.upper(),
                "count": len(data),
                "data": data,
                "total_cash_dividend": round(total_cash, 2),
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_dividends"}

    @mcp.tool()
    def get_dcf_valuation(
        symbol: str,
        wacc: float = 0.09,
        terminal_growth: float = 0.02,
    ) -> dict[str, Any]:
        """Run a DCF (Discounted Cash Flow) valuation model.

        Uses historical free cash flow to project future cash flows and
        compute an implied share price.

        Args:
            symbol: Stock ticker.
            wacc: Weighted average cost of capital (default 0.09).
            terminal_growth: Terminal growth rate (default 0.02).

        Returns:
            DCF model output with implied share price and assumptions.
        """
        try:
            import urllib.request, json
            url = f"http://localhost:8000/api/dcf/{symbol.upper()}?wacc={wacc}&terminal_growth={terminal_growth}"
            resp = urllib.request.urlopen(url, timeout=30)
            return json.loads(resp.read())
        except Exception as exc:
            return {"error": str(exc), "tool": "get_dcf_valuation"}

    @mcp.tool()
    def get_pe_band(
        symbol: str,
        years: int = 5,
    ) -> dict[str, Any]:
        """Get P/E Band (河流圖) data for valuation analysis.

        Returns historical PER percentile bands (cheap/fair/expensive zones)
        and time series data for charting.

        Args:
            symbol: Stock ticker.
            years: Years of history (default 5).

        Returns:
            PER bands (p10-p90), trailing EPS, band prices, and time series.
        """
        try:
            import urllib.request, json
            url = f"http://localhost:8000/api/pe-band/{symbol.upper()}?years={years}"
            resp = urllib.request.urlopen(url, timeout=15)
            return json.loads(resp.read())
        except Exception as exc:
            return {"error": str(exc), "tool": "get_pe_band"}
