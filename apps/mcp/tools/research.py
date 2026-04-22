"""Company research, supply chain, theme screening, and peer comparison MCP tools."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ._common import DB_PATH, _research_db


def register(mcp: FastMCP) -> None:
    """Register research tools on the given MCP server instance."""

    @mcp.tool()
    def get_company_research(ticker: str) -> dict[str, Any]:
        """Get fundamental research profile for a Taiwan stock.

        Returns company description, sector, industry, supply chain relationships,
        customer/supplier links, and investment themes sourced from My-TW-Coverage.

        Args:
            ticker: 4-digit Taiwan stock ticker (e.g. "2330" for TSMC).

        Returns:
            Company profile with supply_chain, customers, suppliers, and themes lists.
        """
        try:
            with _research_db() as con:
                company = con.execute(
                    "SELECT ticker, name, sector, industry, market_cap, ev, description "
                    "FROM research_companies WHERE ticker = ?",
                    (ticker,),
                ).fetchone()
                if company is None:
                    return {"error": f"Ticker '{ticker}' not found in research database"}

                supply_chain = con.execute(
                    "SELECT direction, entity, role_note FROM research_supply_chain "
                    "WHERE ticker = ? ORDER BY direction, entity",
                    (ticker,),
                ).fetchall()

                customers = con.execute(
                    "SELECT counterpart, is_customer, note FROM research_customers "
                    "WHERE ticker = ? ORDER BY counterpart",
                    (ticker,),
                ).fetchall()

                themes = con.execute(
                    "SELECT theme FROM research_themes WHERE ticker = ? ORDER BY theme",
                    (ticker,),
                ).fetchall()

            return {
                "ticker": company["ticker"],
                "name": company["name"],
                "sector": company["sector"],
                "industry": company["industry"],
                "market_cap_million_twd": company["market_cap"],
                "ev_million_twd": company["ev"],
                "description": company["description"],
                "supply_chain": [
                    {"direction": r["direction"], "entity": r["entity"], "role_note": r["role_note"]}
                    for r in supply_chain
                ],
                "customers": [
                    {"counterpart": r["counterpart"], "is_customer": bool(r["is_customer"]), "note": r["note"]}
                    for r in customers
                ],
                "themes": [r["theme"] for r in themes],
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_company_research"}

    @mcp.tool()
    def find_supply_chain(ticker: str) -> dict[str, Any]:
        """Find upstream and downstream supply chain companies for a Taiwan stock.

        Also returns related companies — other tickers whose supply chain mentions
        this company, revealing indirect ecosystem relationships.

        Args:
            ticker: 4-digit Taiwan stock ticker (e.g. "2330").

        Returns:
            upstream, downstream lists and related_companies with ticker cross-references.
        """
        try:
            with _research_db() as con:
                name_row = con.execute(
                    "SELECT name FROM research_companies WHERE ticker = ?", (ticker,)
                ).fetchone()
                if name_row is None:
                    return {"error": f"Ticker '{ticker}' not found in research database"}
                company_name = name_row["name"]

                sc_rows = con.execute(
                    "SELECT direction, entity, role_note FROM research_supply_chain "
                    "WHERE ticker = ? ORDER BY direction, entity",
                    (ticker,),
                ).fetchall()

                related_rows = con.execute(
                    """
                    SELECT DISTINCT sc.ticker, rc.name, rc.industry
                    FROM research_supply_chain sc
                    JOIN research_companies rc ON rc.ticker = sc.ticker
                    WHERE sc.ticker != ?
                      AND (sc.entity LIKE ? OR sc.entity LIKE ?)
                    ORDER BY rc.name
                    """,
                    (ticker, f"%{ticker}%", f"%{company_name}%"),
                ).fetchall()

            return {
                "ticker": ticker,
                "name": company_name,
                "upstream": [
                    {"entity": r["entity"], "role_note": r["role_note"]}
                    for r in sc_rows if r["direction"] == "upstream"
                ],
                "downstream": [
                    {"entity": r["entity"], "role_note": r["role_note"]}
                    for r in sc_rows if r["direction"] == "downstream"
                ],
                "related_companies": [
                    {"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]}
                    for r in related_rows
                ],
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "find_supply_chain"}

    @mcp.tool()
    def screen_by_theme(theme: str) -> dict[str, Any]:
        """List all Taiwan stocks tagged with an investment theme.

        Themes include: AI_伺服器, ABF_載板, CoWoS, HBM, NVIDIA, EUV, 5G, CPO,
        Apple, and others from the My-TW-Coverage database.

        Args:
            theme: Theme name to filter by (e.g. "AI_伺服器", "HBM", "5G").

        Returns:
            List of companies in the theme with ticker, name, and industry.
        """
        try:
            with _research_db() as con:
                rows = con.execute(
                    """
                    SELECT rc.ticker, rc.name, rc.industry
                    FROM research_themes rt
                    JOIN research_companies rc ON rc.ticker = rt.ticker
                    WHERE rt.theme = ?
                    ORDER BY rc.name
                    """,
                    (theme,),
                ).fetchall()

                if not rows:
                    # Return available themes as hint
                    available = con.execute(
                        "SELECT theme, COUNT(*) as cnt FROM research_themes "
                        "GROUP BY theme ORDER BY cnt DESC"
                    ).fetchall()
                    return {
                        "error": f"Theme '{theme}' not found",
                        "available_themes": [r["theme"] for r in available],
                    }

            return {
                "theme": theme,
                "total": len(rows),
                "companies": [
                    {"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]}
                    for r in rows
                ],
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "screen_by_theme"}

    @mcp.tool()
    def get_peer_comparison(
        symbol: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Compare a stock against its industry peers.

        Finds companies in the same industry and compares market cap,
        PER, PBR, and revenue growth.

        Args:
            symbol: Taiwan stock ticker.
            limit: Max peers to return (default 10).

        Returns:
            Peer list with valuation metrics and industry averages.
        """
        try:
            sym = symbol.upper()
            with _research_db() as con:
                target = con.execute(
                    "SELECT ticker, name, sector, industry, market_cap "
                    "FROM research_companies WHERE ticker=?", (sym,),
                ).fetchone()
                if not target:
                    return {"error": f"Company {sym} not found in research DB"}

                peers = con.execute(
                    "SELECT r.ticker, r.name, r.market_cap, v.per, v.pbr "
                    "FROM research_companies r "
                    "LEFT JOIN (SELECT symbol, per, pbr FROM valuation_metrics "
                    "  WHERE (symbol, date) IN (SELECT symbol, MAX(date) FROM valuation_metrics GROUP BY symbol)"
                    ") v ON r.ticker = v.symbol "
                    "WHERE r.industry=? ORDER BY r.market_cap DESC LIMIT ?",
                    (target["industry"], limit),
                ).fetchall()

            return {
                "symbol": sym,
                "industry": target["industry"],
                "peers": [dict(p) for p in peers],
            }
        except Exception as exc:
            return {"error": str(exc), "tool": "get_peer_comparison"}

    @mcp.tool()
    def generate_research_report(symbol: str) -> dict[str, Any]:
        """Generate a comprehensive individual stock research report.

        Aggregates all available data: company profile, financials, valuation,
        rating, scenarios, revenue trends, dividends, supply chain, themes,
        catalysts, and peer comparison into one structured report.

        Args:
            symbol: Stock ticker.

        Returns:
            Full research report with 12 sections.
        """
        try:
            import urllib.request, json
            resp = urllib.request.urlopen(
                f"http://localhost:8000/api/report/{symbol.upper()}", timeout=15
            )
            return json.loads(resp.read())
        except Exception:
            # Fallback: build from local DB
            try:
                sym = symbol.upper()
                report: dict = {"symbol": sym, "sections": {}}
                with _research_db() as con:
                    company = con.execute(
                        "SELECT * FROM research_companies WHERE ticker=?", (sym,),
                    ).fetchone()
                    report["sections"]["company"] = dict(company) if company else None

                    from domain.rating.repository import get_rating, get_scenarios_q
                    report["sections"]["rating"] = get_rating(DB_PATH, sym)
                    report["sections"]["scenarios"] = get_scenarios_q(DB_PATH, sym)

                    from domain.financials.repository import (
                        get_financial_statements, get_valuation_metrics as _gv,
                        get_dividend_history,
                    )
                    report["sections"]["income"] = get_financial_statements(DB_PATH, sym, "income", 4)
                    report["sections"]["valuation"] = _gv(DB_PATH, sym, 5)
                    report["sections"]["dividends"] = get_dividend_history(DB_PATH, sym, 5)

                return report
            except Exception as inner:
                return {"error": str(inner), "tool": "generate_research_report"}
