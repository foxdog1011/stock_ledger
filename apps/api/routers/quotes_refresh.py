"""Quote refresh endpoints.

POST /api/quotes/refresh          – fetch latest prices from an external provider
GET  /api/quotes/refresh/status   – last refresh run summary (filterable by trigger)
GET  /api/quotes/provider         – configured / effective provider info
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..config import QUOTE_PROVIDER
from ..deps import get_ledger
from ..providers.auto import effective_provider_name
from ..services.quotes_service import (
    refresh_quotes_for_symbols,
    _ensure_log_table,
    RefreshServiceResult,
)
from ..tz import TZ
from ledger import StockLedger

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RefreshBody(BaseModel):
    symbols: Optional[List[str]] = None
    as_of: Optional[str] = None
    provider: Optional[str] = None   # "auto" | "twse" | "finmind" | "yahoo"


class RefreshErrorItem(BaseModel):
    symbol: str
    message: str


class RefreshPriceItem(BaseModel):
    symbol: str
    date: str
    close: float


class RefreshResult(BaseModel):
    as_of: str
    provider: str
    requested: int
    inserted: int
    skipped: int
    errors: List[RefreshErrorItem]
    prices: List[RefreshPriceItem]


class RefreshStatusOut(BaseModel):
    last_run_at: Optional[str] = None
    provider: Optional[str] = None
    as_of: Optional[str] = None
    trigger: Optional[str] = None
    inserted: Optional[int] = None
    skipped: Optional[int] = None
    errors_count: Optional[int] = None
    message: Optional[str] = None


class ProviderInfoOut(BaseModel):
    configured: str
    effective: str
    finmind_token_set: bool


# ── Helpers ───────────────────────────────────────────────────────────────────

def _today_taipei() -> str:
    import datetime
    return datetime.datetime.now(TZ).strftime("%Y-%m-%d")


def _to_api_result(r: RefreshServiceResult) -> RefreshResult:
    return RefreshResult(
        as_of=r.as_of,
        provider=r.provider,
        requested=r.requested,
        inserted=r.inserted,
        skipped=r.skipped,
        errors=[RefreshErrorItem(symbol=e.symbol, message=e.message) for e in r.errors],
        prices=[RefreshPriceItem(symbol=p.symbol, date=p.date, close=p.close) for p in r.prices],
    )


# Public alias so main.py and scheduler can call it
def do_refresh(
    ledger: StockLedger,
    symbols: Optional[List[str]] = None,
    as_of: Optional[str] = None,
    provider_name: Optional[str] = None,
    trigger: str = "manual",
) -> RefreshResult:
    as_of = as_of or _today_taipei()
    provider_name = provider_name or QUOTE_PROVIDER

    if not symbols:
        positions = ledger.positions(as_of=as_of)
        symbols = [s for s, qty in positions.items() if qty > 0]

    result = refresh_quotes_for_symbols(
        ledger=ledger,
        symbols=symbols or [],
        as_of=as_of,
        provider_name=provider_name,
        trigger=trigger,
        skip_if_fresh=False,   # manual refresh always fetches
    )
    return _to_api_result(result)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/quotes/refresh",
    response_model=RefreshResult,
    summary="Fetch latest closing prices for open positions",
)
def refresh_quotes(
    body: RefreshBody = RefreshBody(),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Fetch the most-recent closing prices from the configured provider
    and upsert them into the prices table.

    **Provider auto-resolution:**
    - Taiwan tickers (4–6 digits) → TWSE / TPEX
    - US / international tickers → Yahoo Finance
    - `FINMIND_TOKEN` env set → FinMind for all

    All body fields are optional:
    - `symbols` – defaults to all open positions
    - `as_of` – defaults to today (Asia/Taipei)
    - `provider` – defaults to `QUOTE_PROVIDER` env (fallback: `auto`)
    """
    return do_refresh(
        ledger=ledger,
        symbols=body.symbols,
        as_of=body.as_of,
        provider_name=body.provider,
        trigger="manual",
    )


@router.get(
    "/quotes/refresh/status",
    response_model=RefreshStatusOut,
    summary="Get the status of the last price refresh",
)
def refresh_status(
    trigger: Optional[str] = Query(None, description="Filter by trigger: manual|schedule|trade"),
):
    """Return metadata about the most-recent refresh run (optionally filtered by trigger)."""
    try:
        _ensure_log_table()
        with sqlite3.connect(DB_PATH) as conn:
            if trigger:
                row = conn.execute(
                    """
                    SELECT run_at, provider, as_of, trigger, inserted, skipped, errors_count, message
                    FROM quote_refresh_log
                    WHERE trigger = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (trigger,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT run_at, provider, as_of, trigger, inserted, skipped, errors_count, message
                    FROM quote_refresh_log
                    ORDER BY id DESC LIMIT 1
                    """
                ).fetchone()
    except Exception:
        row = None

    if not row:
        return RefreshStatusOut()

    return RefreshStatusOut(
        last_run_at=row[0],
        provider=row[1],
        as_of=row[2],
        trigger=row[3],
        inserted=row[4],
        skipped=row[5],
        errors_count=row[6],
        message=row[7],
    )


@router.get(
    "/quotes/provider",
    response_model=ProviderInfoOut,
    summary="Get the configured price provider",
)
def provider_info():
    """Return configured provider, effective provider, and token status."""
    configured = QUOTE_PROVIDER
    return ProviderInfoOut(
        configured=configured,
        effective=effective_provider_name() if configured == "auto" else configured,
        finmind_token_set=bool(os.getenv("FINMIND_TOKEN", "").strip()),
    )
