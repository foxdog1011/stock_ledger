"""Anomaly detection MCP tools."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import _yf_fetch


def register(mcp: FastMCP) -> None:
    """Register anomaly detection tools on the given MCP server instance."""

    @mcp.tool()
    def detect_anomalies(
        symbol: str,
        days: int = 120,
        method: str = "both",
    ) -> dict[str, Any]:
        """Detect price/volume anomalies for a stock using statistical methods.

        Fetches historical price data from Yahoo Finance, then runs anomaly
        detection using the configured method.  For Taiwan-listed stocks supply
        the numeric ticker code (e.g. "2330"); the suffix (.TW / .TWO) is
        resolved automatically.

        Args:
            symbol: Ticker symbol.  Numeric strings are treated as Taiwan stocks.
            days:   Look-back window in trading days (default 120).
            method: Detection method — "zscore", "autoencoder", or "both".

        Returns:
            Anomaly detection results dict produced by analysis.anomaly_detector.
        """
        try:
            from analysis.anomaly_detector import detect_anomalies as _detect  # type: ignore
            import yfinance as yf  # type: ignore

            sym = symbol.upper()
            yf_sym = f"{sym}.TW" if sym.isdigit() else sym

            end_dt = date.today()
            start_dt = end_dt - timedelta(days=days + 90)

            hist = _yf_fetch(yf.Ticker(yf_sym), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)
            if hist.empty and sym.isdigit():
                hist = _yf_fetch(yf.Ticker(f"{sym}.TWO"), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)

            if hist.empty:
                return {
                    "error": f"No price data found for symbol '{symbol}'",
                    "symbol": sym,
                }

            rows = [
                {
                    "date": idx.strftime("%Y-%m-%d"),
                    "close": float(r["Close"]),
                    "volume": float(r.get("Volume") or 0),
                }
                for idx, r in hist.iterrows()
            ]

            warmup_rows = rows[-(days + 80):]

            result = _detect(
                rows=warmup_rows,
                method=method,
                zscore_threshold=2.5,
                ae_threshold=2.5,
                lookback=days,
            )
            return result if isinstance(result, dict) else {"anomalies": result}
        except Exception as exc:
            return {"error": str(exc), "tool": "detect_anomalies", "symbol": symbol}
