"""Research endpoints — My-TW-Coverage integration.

Exposes company profile data, supply chain relationships, customer links,
and investment themes sourced from the research_companies,
research_supply_chain, research_customers, and research_themes tables.

Route order matters: specific paths (/search, /themes, /theme/*, /supply-chain/*)
must be declared before the wildcard /{ticker} to avoid being shadowed.
"""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Query

from ..config import DB_PATH

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _company_exists(con: sqlite3.Connection, ticker: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM research_companies WHERE ticker = ? LIMIT 1", (ticker,)
    ).fetchone()
    return row is not None


# ── specific routes first (before wildcard /{ticker}) ─────────────────────────

@router.get("/search", summary="Full-text search across research companies")
def search_companies(
    q: str = Query(..., min_length=1, description="Keyword to search in name, description, industry"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """Full-text search across company name, description, and industry."""
    keyword = f"%{q}%"
    with _connect() as con:
        rows = con.execute(
            """
            SELECT ticker, name, industry, description
            FROM research_companies
            WHERE name LIKE ?
               OR description LIKE ?
               OR industry LIKE ?
            ORDER BY name
            LIMIT ?
            """,
            (keyword, keyword, keyword, limit),
        ).fetchall()

    results = []
    for r in rows:
        desc = r["description"] or ""
        snippet = desc[:200] + ("…" if len(desc) > 200 else "")
        results.append({
            "ticker": r["ticker"],
            "name": r["name"],
            "industry": r["industry"],
            "description_snippet": snippet,
        })

    return {"total": len(results), "results": results}


@router.get("/themes", summary="List all distinct investment themes with company count")
def list_themes() -> dict:
    """Return all distinct investment themes sorted by company count."""
    with _connect() as con:
        rows = con.execute(
            """
            SELECT theme, COUNT(DISTINCT ticker) AS company_count
            FROM research_themes
            GROUP BY theme
            ORDER BY company_count DESC, theme
            """
        ).fetchall()

    return {
        "total": len(rows),
        "themes": [
            {"theme_name": r["theme"], "company_count": r["company_count"]}
            for r in rows
        ],
    }


@router.get("/theme/{theme_name}", summary="List companies tagged with a theme")
def get_theme_companies(theme_name: str) -> dict:
    """Return all companies tagged with the given investment theme."""
    with _connect() as con:
        rows = con.execute(
            """
            SELECT rc.ticker, rc.name, rc.industry
            FROM research_themes rt
            JOIN research_companies rc ON rc.ticker = rt.ticker
            WHERE rt.theme = ?
            ORDER BY rc.name
            """,
            (theme_name,),
        ).fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail=f"Theme '{theme_name}' not found or has no companies")

    return {
        "theme_name": theme_name,
        "total": len(rows),
        "companies": [
            {"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]}
            for r in rows
        ],
    }


@router.get("/supply-chain/{ticker}", summary="Get supply chain for a ticker")
def get_supply_chain(ticker: str) -> dict:
    """Return upstream, downstream, and related companies for a ticker."""
    ticker = ticker.upper()
    with _connect() as con:
        if not _company_exists(con, ticker):
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in research_companies")

        sc_rows = con.execute(
            """
            SELECT direction, entity, role_note
            FROM research_supply_chain
            WHERE ticker = ?
            ORDER BY direction, entity
            """,
            (ticker,),
        ).fetchall()

        name_row = con.execute(
            "SELECT name FROM research_companies WHERE ticker = ?", (ticker,)
        ).fetchone()
        company_name = name_row["name"] if name_row else ""

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


# ── wildcard route last ────────────────────────────────────────────────────────

@router.get("/{ticker}", summary="Get company research profile")
def get_company(ticker: str) -> dict:
    """
    Return full research profile for a ticker:
    name, sector, industry, market_cap, ev, description,
    supply_chain entries, customer links, and investment themes.
    """
    ticker = ticker.upper()
    with _connect() as con:
        if not _company_exists(con, ticker):
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in research_companies")

        company = con.execute(
            """
            SELECT ticker, name, sector, industry, market_cap, ev, description
            FROM research_companies
            WHERE ticker = ?
            """,
            (ticker,),
        ).fetchone()

        supply_chain_rows = con.execute(
            """
            SELECT direction, entity, role_note
            FROM research_supply_chain
            WHERE ticker = ?
            ORDER BY direction, entity
            """,
            (ticker,),
        ).fetchall()

        customer_rows = con.execute(
            """
            SELECT counterpart, is_customer, note
            FROM research_customers
            WHERE ticker = ?
            ORDER BY counterpart
            """,
            (ticker,),
        ).fetchall()

        theme_rows = con.execute(
            """
            SELECT theme
            FROM research_themes
            WHERE ticker = ?
            ORDER BY theme
            """,
            (ticker,),
        ).fetchall()

    return {
        "ticker": company["ticker"],
        "name": company["name"],
        "sector": company["sector"],
        "industry": company["industry"],
        "market_cap": company["market_cap"],
        "ev": company["ev"],
        "description": company["description"],
        "supply_chain": [
            {
                "direction": r["direction"],
                "entity": r["entity"],
                "role_note": r["role_note"],
            }
            for r in supply_chain_rows
        ],
        "customers": [
            {
                "counterpart": r["counterpart"],
                "is_customer": bool(r["is_customer"]),
                "note": r["note"],
            }
            for r in customer_rows
        ],
        "themes": [r["theme"] for r in theme_rows],
    }
