"""Market data, quotes, technical indicators, and news MCP tools."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import _yf_fetch, _yf_symbol


# ── Standalone logic (importable for tests) ──────────────────────────────────


def get_quote(symbol: str) -> dict[str, Any]:
    """Get a comprehensive real-time quote for any stock."""
    try:
        import yfinance as yf

        yf_sym = _yf_symbol(symbol)
        ticker = yf.Ticker(yf_sym)
        try:
            fast = ticker.fast_info
            _ = fast.last_price
        except Exception:
            fast = None
        if fast is None and symbol.isdigit():
            yf_sym = f"{symbol}.TWO"
            ticker = yf.Ticker(yf_sym)
            fast = ticker.fast_info
        info = ticker.info or {}

        price = getattr(fast, "last_price", None) or info.get("currentPrice") or info.get("regularMarketPrice")
        prev_close = getattr(fast, "previous_close", None) or info.get("previousClose") or info.get("regularMarketPreviousClose")
        change = (price - prev_close) if (price and prev_close) else None
        change_pct = (change / prev_close * 100) if (change is not None and prev_close) else None

        return {
            "symbol": symbol.upper(),
            "yf_symbol": yf_sym,
            "price": round(price, 2) if price else None,
            "change": round(change, 2) if change is not None else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "volume": getattr(fast, "three_month_average_volume", None) or info.get("volume"),
            "market_cap": getattr(fast, "market_cap", None) or info.get("marketCap"),
            "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
            "52w_high": getattr(fast, "year_high", None) or info.get("fiftyTwoWeekHigh"),
            "52w_low": getattr(fast, "year_low", None) or info.get("fiftyTwoWeekLow"),
            "dividend_yield": info.get("dividendYield"),
            "currency": info.get("currency"),
            "exchange": info.get("exchange"),
            "as_of": date.today().isoformat(),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_quote", "symbol": symbol}


def get_technical_indicators(symbol: str, days: int = 120) -> dict[str, Any]:
    """Compute technical indicators for a stock using recent price history."""
    try:
        import yfinance as yf
        import pandas as pd

        yf_sym = _yf_symbol(symbol)
        end_dt = date.today()
        start_dt = end_dt - timedelta(days=days + 120)

        hist = _yf_fetch(yf.Ticker(yf_sym), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)
        if hist.empty and symbol.isdigit():
            hist = _yf_fetch(yf.Ticker(f"{symbol}.TWO"), "history", start=str(start_dt), end=str(end_dt), auto_adjust=True)
        if hist.empty:
            return {"error": f"No price data for '{symbol}'", "tool": "get_technical_indicators"}

        close = hist["Close"]
        latest = float(close.iloc[-1])

        ma = {}
        for period in (5, 10, 20, 60):
            if len(close) >= period:
                ma[f"ma{period}"] = round(float(close.rolling(period).mean().iloc[-1]), 2)

        delta = close.diff()
        gain = delta.clip(lower=0).rolling(14).mean()
        loss = (-delta.clip(upper=0)).rolling(14).mean()
        rs = gain / loss.replace(0, float("nan"))
        rsi_series = 100 - (100 / (1 + rs))
        rsi = round(float(rsi_series.iloc[-1]), 2) if not rsi_series.empty else None

        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line
        macd = {
            "macd": round(float(macd_line.iloc[-1]), 4),
            "signal": round(float(signal_line.iloc[-1]), 4),
            "histogram": round(float(histogram.iloc[-1]), 4),
            "trend": "bullish" if macd_line.iloc[-1] > signal_line.iloc[-1] else "bearish",
        }

        bb_mid = close.rolling(20).mean()
        bb_std = close.rolling(20).std()
        bb_upper = bb_mid + 2 * bb_std
        bb_lower = bb_mid - 2 * bb_std
        bb_pct = (close - bb_lower) / (bb_upper - bb_lower)
        bollinger = {
            "upper": round(float(bb_upper.iloc[-1]), 2),
            "mid": round(float(bb_mid.iloc[-1]), 2),
            "lower": round(float(bb_lower.iloc[-1]), 2),
            "pct_b": round(float(bb_pct.iloc[-1]), 3),
            "position": "overbought" if bb_pct.iloc[-1] > 1 else ("oversold" if bb_pct.iloc[-1] < 0 else "normal"),
        }

        return {
            "symbol": symbol.upper(),
            "latest_close": round(latest, 2),
            "ma": ma,
            "rsi14": rsi,
            "rsi_signal": "overbought" if (rsi or 0) > 70 else ("oversold" if (rsi or 100) < 30 else "neutral"),
            "macd": macd,
            "bollinger": bollinger,
            "as_of": date.today().isoformat(),
            "data_points": len(close),
        }
    except Exception as exc:
        return {"error": str(exc), "tool": "get_technical_indicators", "symbol": symbol}


def get_news(symbol: str, count: int = 5) -> dict[str, Any]:
    """Fetch recent news articles for a stock."""
    try:
        import yfinance as yf

        yf_sym = _yf_symbol(symbol)
        ticker = yf.Ticker(yf_sym)
        try:
            raw_news = ticker.news or []
        except Exception:
            raw_news = []

        articles = []
        for item in raw_news[: min(count, 10)]:
            content = item.get("content", {})
            articles.append({
                "title": content.get("title") or item.get("title", ""),
                "publisher": (content.get("provider") or {}).get("displayName") or item.get("publisher", ""),
                "link": (content.get("canonicalUrl") or {}).get("url") or item.get("link", ""),
                "published": content.get("pubDate") or item.get("providerPublishTime", ""),
            })

        return {"symbol": symbol.upper(), "articles": articles, "count": len(articles)}
    except Exception as exc:
        return {"error": str(exc), "tool": "get_news", "symbol": symbol}


# ── MCP registration ─────────────────────────────────────────────────────────


def register(mcp: FastMCP) -> None:
    """Register market data tools on the given MCP server instance."""
    # Wrap standalone functions as MCP tools, preserving their docstrings
    mcp.tool()(get_quote)
    mcp.tool()(get_technical_indicators)
    mcp.tool()(get_news)
