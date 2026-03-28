"""Research endpoints — My-TW-Coverage integration.

Exposes company profile data, supply chain relationships, customer links,
and investment themes sourced from the research_companies,
research_supply_chain, research_customers, and research_themes tables.

Route order matters: specific paths (/search, /themes, /theme/*, /supply-chain/*)
must be declared before the wildcard /{ticker} to avoid being shadowed.
"""
from __future__ import annotations

import re
import sqlite3

from fastapi import APIRouter, HTTPException, Query

from ..config import DB_PATH

router = APIRouter()


# ── supply chain helpers ──────────────────────────────────────────────────────

def _supply_chain_tier(upstream_count: int, downstream_count: int) -> str | None:
    """
    Derive supply chain position from a company's own supply chain entries.
    - Has downstream entries (customers) → company is an upstream supplier → "upstream"
    - Has upstream entries (suppliers)   → company is a downstream buyer   → "downstream"
    - Has both                           → "integrated"
    - Has neither                        → None
    """
    has_up   = (upstream_count or 0) > 0
    has_down = (downstream_count or 0) > 0
    if has_up and has_down:
        return "integrated"
    if has_down:
        return "upstream"    # supplies downstream customers
    if has_up:
        return "downstream"  # buys from upstream suppliers
    return None


def _resolve_entity_ticker(con: sqlite3.Connection, entity: str) -> str | None:
    """Try to resolve a free-text entity name to a known ticker."""
    stripped = entity.strip()
    # 4-digit ticker prefix
    m = re.match(r'^(\d{4})', stripped)
    if m:
        row = con.execute(
            "SELECT ticker FROM research_companies WHERE ticker = ? LIMIT 1",
            (m.group(1),),
        ).fetchone()
        if row:
            return row["ticker"]
    # Exact name match
    row = con.execute(
        "SELECT ticker FROM research_companies WHERE name = ? LIMIT 1",
        (stripped,),
    ).fetchone()
    if row:
        return row["ticker"]
    # Partial name match (greedy — only use if unambiguous)
    rows = con.execute(
        "SELECT ticker FROM research_companies WHERE name LIKE ? LIMIT 2",
        (f"%{stripped}%",),
    ).fetchall()
    if len(rows) == 1:
        return rows[0]["ticker"]
    return None


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
    """Return all companies tagged with the given investment theme, including supply chain tier."""
    with _connect() as con:
        rows = con.execute(
            """
            SELECT rc.ticker, rc.name, rc.industry,
                   SUM(CASE WHEN sc.direction = 'upstream'   THEN 1 ELSE 0 END) AS upstream_count,
                   SUM(CASE WHEN sc.direction = 'downstream' THEN 1 ELSE 0 END) AS downstream_count
            FROM research_themes rt
            JOIN research_companies rc ON rc.ticker = rt.ticker
            LEFT JOIN research_supply_chain sc ON sc.ticker = rc.ticker
            WHERE rt.theme = ?
            GROUP BY rc.ticker, rc.name, rc.industry
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
            {
                "ticker":             r["ticker"],
                "name":               r["name"],
                "industry":           r["industry"],
                "supply_chain_tier":  _supply_chain_tier(r["upstream_count"], r["downstream_count"]),
            }
            for r in rows
        ],
    }


@router.get("/theme/{theme_name}/supply-chain", summary="Companies in a theme grouped by supply chain tier")
def get_theme_supply_chain(theme_name: str) -> dict:
    """
    Return companies in a theme grouped by supply chain tier (upstream / integrated / downstream / unknown),
    plus cross-links between companies in the same theme.
    """
    with _connect() as con:
        rows = con.execute(
            """
            SELECT rc.ticker, rc.name, rc.industry,
                   SUM(CASE WHEN sc.direction = 'upstream'   THEN 1 ELSE 0 END) AS upstream_count,
                   SUM(CASE WHEN sc.direction = 'downstream' THEN 1 ELSE 0 END) AS downstream_count
            FROM research_themes rt
            JOIN research_companies rc ON rc.ticker = rt.ticker
            LEFT JOIN research_supply_chain sc ON sc.ticker = rc.ticker
            WHERE rt.theme = ?
            GROUP BY rc.ticker, rc.name, rc.industry
            ORDER BY rc.name
            """,
            (theme_name,),
        ).fetchall()

        if not rows:
            raise HTTPException(status_code=404, detail=f"Theme '{theme_name}' not found")

        ticker_set = {r["ticker"] for r in rows}

        # Build cross-links: A mentions B (both in this theme) in its supply chain
        links: list[dict] = []
        seen_links: set[tuple] = set()
        for r in rows:
            sc_entries = con.execute(
                "SELECT direction, entity FROM research_supply_chain WHERE ticker = ?",
                (r["ticker"],),
            ).fetchall()
            for e in sc_entries:
                resolved = _resolve_entity_ticker(con, e["entity"])
                if resolved and resolved in ticker_set and resolved != r["ticker"]:
                    key = (r["ticker"], resolved)
                    if key not in seen_links:
                        seen_links.add(key)
                        links.append({
                            "from":      r["ticker"],
                            "to":        resolved,
                            "direction": e["direction"],
                        })

    # Group by tier
    groups: dict[str, list] = {"upstream": [], "integrated": [], "downstream": [], "unknown": []}
    for r in rows:
        tier = _supply_chain_tier(r["upstream_count"], r["downstream_count"])
        bucket = tier if tier in groups else "unknown"
        groups[bucket].append({
            "ticker":   r["ticker"],
            "name":     r["name"],
            "industry": r["industry"],
            "tier":     tier,
        })

    return {
        "theme_name": theme_name,
        "upstream":   groups["upstream"],
        "integrated": groups["integrated"],
        "downstream": groups["downstream"],
        "unknown":    groups["unknown"],
        "links":      links,
    }


@router.get("/supply-chain/{ticker}/tree", summary="Multi-hop supply chain tree")
def get_supply_chain_tree(
    ticker: str,
    depth: int = Query(2, ge=1, le=2, description="Hop depth (1 or 2)"),
) -> dict:
    """
    Return a multi-hop supply chain tree centred on ticker.
    Level +1/+2 = downstream; Level −1/−2 = upstream.
    Unknown entities (not resolvable to a known ticker) are included at level 1 only.
    """
    ticker = ticker.upper()
    with _connect() as con:
        if not _company_exists(con, ticker):
            raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found")

        center_row = con.execute(
            "SELECT name, industry FROM research_companies WHERE ticker = ?", (ticker,)
        ).fetchone()

        def _get_entries(t: str) -> list[dict]:
            rows = con.execute(
                "SELECT direction, entity, role_note FROM research_supply_chain WHERE ticker = ?", (t,)
            ).fetchall()
            return [{"direction": r["direction"], "entity": r["entity"], "role_note": r["role_note"]} for r in rows]

        def _enrich(entity: str) -> dict:
            resolved = _resolve_entity_ticker(con, entity)
            if not resolved:
                return {"entity": entity, "ticker": None, "name": None, "industry": None}
            row = con.execute(
                "SELECT name, industry FROM research_companies WHERE ticker = ?", (resolved,)
            ).fetchone()
            return {
                "entity":   entity,
                "ticker":   resolved,
                "name":     row["name"] if row else None,
                "industry": row["industry"] if row else None,
            }

        # Level 1
        l1_entries = _get_entries(ticker)
        upstream_l1   = [_enrich(e["entity"]) | {"role_note": e["role_note"]} for e in l1_entries if e["direction"] == "upstream"][:15]
        downstream_l1 = [_enrich(e["entity"]) | {"role_note": e["role_note"]} for e in l1_entries if e["direction"] == "downstream"][:15]

        # Level 2 (only for resolved companies)
        upstream_l2:   list[dict] = []
        downstream_l2: list[dict] = []
        if depth >= 2:
            seen: set[str] = {ticker}
            for node in upstream_l1:
                t2 = node.get("ticker")
                if t2 and t2 not in seen:
                    seen.add(t2)
                    for e in _get_entries(t2):
                        if e["direction"] == "upstream" and len(upstream_l2) < 20:
                            enriched = _enrich(e["entity"])
                            upstream_l2.append(enriched | {"via": t2, "role_note": e["role_note"]})
            for node in downstream_l1:
                t2 = node.get("ticker")
                if t2 and t2 not in seen:
                    seen.add(t2)
                    for e in _get_entries(t2):
                        if e["direction"] == "downstream" and len(downstream_l2) < 20:
                            enriched = _enrich(e["entity"])
                            downstream_l2.append(enriched | {"via": t2, "role_note": e["role_note"]})

    return {
        "ticker":        ticker,
        "name":          center_row["name"],
        "industry":      center_row["industry"],
        "upstream_l1":   upstream_l1,
        "upstream_l2":   upstream_l2,
        "downstream_l1": downstream_l1,
        "downstream_l2": downstream_l2,
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
