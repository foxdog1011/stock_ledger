"""Investment rating, quantitative scenario analysis, and research report endpoints."""
from __future__ import annotations

import sqlite3
from datetime import date as Date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..config import DB_PATH
from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


# ── Request Models ───────────────────────────────────────────────────────────

class UpsertRatingIn(BaseModel):
    rating: str
    target_price: float | None = None
    stop_loss: float | None = None
    thesis: str = ""
    time_horizon: str = "12m"
    confidence: float = 0.5


class UpsertScenarioIn(BaseModel):
    scenario_name: str
    target_price: float
    probability: float
    thesis: str = ""


# ── Investment Rating Endpoints ──────────────────────────────────────────────

@router.get("/rating/{symbol}", summary="Get investment rating")
def get_rating(symbol: str) -> dict:
    """Return the latest investment rating for a symbol."""
    from domain.rating.repository import get_rating as _get
    result = _get(DB_PATH, symbol.upper())
    if not result:
        return {"symbol": symbol.upper(), "rating": None, "message": "No rating set"}
    return result


@router.put("/rating/{symbol}", summary="Set/update investment rating")
def set_rating(symbol: str, body: UpsertRatingIn) -> dict:
    """Create or update an investment rating (Buy/Hold/Sell + target price)."""
    from domain.rating.repository import upsert_rating
    try:
        return upsert_rating(
            DB_PATH, symbol.upper(),
            rating=body.rating,
            target_price=body.target_price,
            stop_loss=body.stop_loss,
            thesis=body.thesis,
            time_horizon=body.time_horizon,
            confidence=body.confidence,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ratings", summary="List all investment ratings")
def list_ratings() -> dict:
    """Return all latest ratings (one per symbol)."""
    from domain.rating.repository import list_ratings as _list
    data = _list(DB_PATH)
    return {"count": len(data), "ratings": data}


# ── Quantitative Scenario Endpoints ─────────────────────────────────────────

@router.put("/scenario/{symbol}", summary="Set bull/base/bear scenario")
def set_scenario(symbol: str, body: UpsertScenarioIn) -> dict:
    """Create or update a quantitative scenario (bull/base/bear with probability)."""
    from domain.rating.repository import upsert_scenario_q
    try:
        return upsert_scenario_q(
            DB_PATH, symbol.upper(),
            scenario_name=body.scenario_name,
            target_price=body.target_price,
            probability=body.probability,
            thesis=body.thesis,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scenario/{symbol}", summary="Get all scenarios for a symbol")
def get_scenarios(symbol: str) -> dict:
    """Return all quantitative scenarios for a symbol."""
    from domain.rating.repository import get_scenarios_q
    data = get_scenarios_q(DB_PATH, symbol.upper())
    return {"symbol": symbol.upper(), "count": len(data), "scenarios": data}


@router.get("/scenario/{symbol}/expected-value", summary="Compute expected value")
def expected_value(
    symbol: str,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """Compute probability-weighted expected return from bull/base/bear scenarios."""
    from domain.rating.repository import compute_expected_value
    sym = symbol.upper()

    # Get current price
    positions = ledger.all_positions_pnl()
    current_price = None
    for p in positions:
        if p["symbol"] == sym:
            current_price = p.get("last_price")
            break

    if current_price is None:
        raise HTTPException(
            status_code=404,
            detail=f"No current price found for {sym}. Add a position or quote first.",
        )

    return compute_expected_value(DB_PATH, sym, current_price)


# ── Research Report Generator ────────────────────────────────────────────────

@router.get("/report/{symbol}", summary="Generate structured research report")
def generate_report(
    symbol: str,
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    Generate a comprehensive individual stock research report.

    Aggregates all available data: company profile, financials, valuation,
    technicals, institutional activity, catalysts, rating, and scenarios.
    """
    sym = symbol.upper()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    report: dict = {"symbol": sym, "generated_at": Date.today().isoformat(), "sections": {}}

    try:
        # 1. Company Profile
        company = conn.execute(
            "SELECT ticker, name, sector, industry, market_cap, ev, description "
            "FROM research_companies WHERE ticker = ?", (sym,),
        ).fetchone()
        report["sections"]["company_profile"] = dict(company) if company else None

        # 2. Position (if held)
        positions = ledger.all_positions_pnl()
        pos = next((p for p in positions if p["symbol"] == sym), None)
        report["sections"]["position"] = pos

        # 3. Investment Rating
        rating = conn.execute(
            "SELECT * FROM investment_ratings WHERE symbol=? ORDER BY id DESC LIMIT 1",
            (sym,),
        ).fetchone()
        report["sections"]["rating"] = dict(rating) if rating else None

        # 4. Quantitative Scenarios
        scenarios = conn.execute(
            "SELECT scenario_name, target_price, probability, thesis "
            "FROM scenario_quantitative WHERE symbol=? ORDER BY probability DESC",
            (sym,),
        ).fetchall()
        if scenarios and pos and pos.get("last_price"):
            current = pos["last_price"]
            total_prob = sum(s["probability"] for s in scenarios)
            expected = sum(s["target_price"] * s["probability"] / total_prob for s in scenarios) if total_prob else 0
            report["sections"]["scenarios"] = {
                "data": [dict(s) for s in scenarios],
                "expected_price": round(expected, 2),
                "expected_return_pct": round((expected - current) / current * 100, 2) if current else None,
            }
        else:
            report["sections"]["scenarios"] = None

        # 5. Financial Statements (latest quarter)
        income = conn.execute(
            "SELECT date, origin_name, value FROM financial_statements "
            "WHERE symbol=? AND type='income' ORDER BY date DESC LIMIT 20",
            (sym,),
        ).fetchall()
        if income:
            from collections import OrderedDict
            grouped: OrderedDict[str, dict] = OrderedDict()
            for r in income:
                d = r["date"]
                if d not in grouped:
                    grouped[d] = {"date": d}
                grouped[d][r["origin_name"]] = r["value"]
            report["sections"]["income_statement"] = list(grouped.values())[:4]
        else:
            report["sections"]["income_statement"] = None

        # 6. Valuation Metrics
        val = conn.execute(
            "SELECT date, per, pbr, dividend_yield FROM valuation_metrics "
            "WHERE symbol=? ORDER BY date DESC LIMIT 1",
            (sym,),
        ).fetchone()
        if val:
            # Historical stats
            stats = conn.execute(
                "SELECT AVG(per) as per_avg, MIN(per) as per_min, MAX(per) as per_max, "
                "AVG(pbr) as pbr_avg, MIN(pbr) as pbr_min, MAX(pbr) as pbr_max "
                "FROM valuation_metrics WHERE symbol=? AND per > 0",
                (sym,),
            ).fetchone()
            report["sections"]["valuation"] = {
                "current": dict(val),
                "historical": dict(stats) if stats else None,
            }
        else:
            report["sections"]["valuation"] = None

        # 7. Monthly Revenue Trend
        rev = conn.execute(
            "SELECT year_month, revenue, yoy_pct, mom_pct FROM monthly_revenue "
            "WHERE symbol=? ORDER BY year_month DESC LIMIT 12",
            (sym,),
        ).fetchall()
        report["sections"]["revenue_trend"] = [dict(r) for r in rev] if rev else None

        # 8. Dividends
        divs = conn.execute(
            "SELECT date, cash_dividend, stock_dividend FROM dividend_history "
            "WHERE symbol=? ORDER BY date DESC LIMIT 5",
            (sym,),
        ).fetchall()
        report["sections"]["dividends"] = [dict(d) for d in divs] if divs else None

        # 9. Supply Chain
        upstream = conn.execute(
            "SELECT entity, role_note FROM research_supply_chain "
            "WHERE ticker=? AND direction='upstream'", (sym,),
        ).fetchall()
        downstream = conn.execute(
            "SELECT entity, role_note FROM research_supply_chain "
            "WHERE ticker=? AND direction='downstream'", (sym,),
        ).fetchall()
        report["sections"]["supply_chain"] = {
            "upstream": [dict(u) for u in upstream],
            "downstream": [dict(d) for d in downstream],
        } if upstream or downstream else None

        # 10. Investment Themes
        themes = conn.execute(
            "SELECT theme FROM research_themes WHERE ticker=?", (sym,),
        ).fetchall()
        report["sections"]["themes"] = [t["theme"] for t in themes] if themes else None

        # 11. Catalysts
        catalysts = conn.execute(
            "SELECT * FROM catalysts WHERE symbol=? AND status='pending' ORDER BY event_date",
            (sym,),
        ).fetchall()
        report["sections"]["catalysts"] = [dict(c) for c in catalysts] if catalysts else None

        # 12. Peer Comparison (top 5 by market cap in same industry)
        if company:
            peers = conn.execute(
                "SELECT r.ticker, r.name, r.market_cap, v.per, v.pbr "
                "FROM research_companies r "
                "LEFT JOIN (SELECT symbol, per, pbr FROM valuation_metrics "
                "    WHERE (symbol, date) IN (SELECT symbol, MAX(date) FROM valuation_metrics GROUP BY symbol)"
                ") v ON r.ticker = v.symbol "
                "WHERE r.industry = ? ORDER BY r.market_cap DESC LIMIT 6",
                (company["industry"],),
            ).fetchall()
            report["sections"]["peer_comparison"] = [dict(p) for p in peers]
        else:
            report["sections"]["peer_comparison"] = None

    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()

    return report
