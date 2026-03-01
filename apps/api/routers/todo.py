"""Quote To-Do endpoint – symbols needing fresh price quotes."""
from __future__ import annotations

import sqlite3
from datetime import date as Date, datetime

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()


@router.get("/quotes/todo", summary="Symbols with missing or stale quotes")
def quotes_todo(
    as_of: str = Query(default=None, description="YYYY-MM-DD (defaults to today)"),
    stale_days: int = Query(2, ge=1, description="Days since last quote to consider stale"),
    ledger: StockLedger = Depends(get_ledger),
) -> list[dict]:
    """
    Return open-position symbols that have no quote or whose most-recent quote
    is older than ``stale_days`` business days from ``as_of``.

    | field            | description                                    |
    |------------------|------------------------------------------------|
    | symbol           | ticker                                         |
    | qty              | current position size                          |
    | last_quote_date  | date of most-recent price entry (or null)      |
    | staleness_days   | calendar days since last quote (or null)       |
    | last_price       | closing price on last_quote_date (or null)     |
    | missing          | true = no quote at all                         |
    | stale            | true = quote exists but is older than stale_days |
    """
    if as_of is None:
        as_of = str(Date.today())

    positions = ledger.positions(as_of=as_of)
    result: list[dict] = []

    db_path = str(ledger._db_path)
    for symbol, qty in positions.items():
        if qty <= 0:
            continue

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT date, close FROM prices WHERE symbol=? AND date<=?"
                " ORDER BY date DESC LIMIT 1",
                (symbol, as_of),
            ).fetchone()

        if row is None:
            result.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "last_quote_date": None,
                    "staleness_days": None,
                    "last_price": None,
                    "missing": True,
                    "stale": False,
                }
            )
        else:
            last_quote_date: str = row["date"]
            as_of_dt = datetime.strptime(as_of, "%Y-%m-%d").date()
            quote_dt = datetime.strptime(last_quote_date, "%Y-%m-%d").date()
            staleness_days = (as_of_dt - quote_dt).days
            if staleness_days > stale_days:
                result.append(
                    {
                        "symbol": symbol,
                        "qty": qty,
                        "last_quote_date": last_quote_date,
                        "staleness_days": staleness_days,
                        "last_price": float(row["close"]),
                        "missing": False,
                        "stale": True,
                    }
                )

    return result
