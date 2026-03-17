"""Daily Digest endpoints.

POST /api/digest/generate?date=YYYY-MM-DD&overwrite=false
GET  /api/digest/{date}
GET  /api/digest?start=&end=&limit=30
PATCH /api/digest/{date}/notes
"""
from __future__ import annotations

import datetime
import json
import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..config import DB_PATH
from ..deps import get_ledger
from ..tz import TZ
from ledger import StockLedger

router = APIRouter()
logger = logging.getLogger(__name__)


# ── DB helpers ────────────────────────────────────────────────────────────────

def ensure_digest_table(db_path=None) -> None:
    with sqlite3.connect(db_path or DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS daily_digest (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                date                  TEXT UNIQUE NOT NULL,
                created_at            TEXT NOT NULL DEFAULT (datetime('now')),
                total_equity          REAL,
                daily_pnl             REAL,
                daily_return_pct      REAL,
                external_cashflow     REAL,
                market_value          REAL,
                cash                  REAL,
                top_contributors_json TEXT,
                top_losers_json       TEXT,
                alerts_json           TEXT,
                notes                 TEXT
            )
        """)
        conn.commit()


# ── Schemas ───────────────────────────────────────────────────────────────────

class DigestOut(BaseModel):
    id: int
    date: str
    created_at: str
    total_equity: Optional[float] = None
    daily_pnl: Optional[float] = None
    daily_return_pct: Optional[float] = None
    external_cashflow: Optional[float] = None
    market_value: Optional[float] = None
    cash: Optional[float] = None
    top_contributors: Optional[list] = None
    top_losers: Optional[list] = None
    alerts: Optional[list] = None
    notes: Optional[str] = None


class DigestSummary(BaseModel):
    date: str
    total_equity: Optional[float] = None
    daily_pnl: Optional[float] = None
    daily_return_pct: Optional[float] = None
    notes: Optional[str] = None


class PatchNotesBody(BaseModel):
    notes: str


# ── Core generation logic ─────────────────────────────────────────────────────

def _generate_digest_data(ledger: StockLedger, date: str) -> dict:
    """Compute all digest fields for *date*. Pure function, no DB writes."""
    prev_date = (
        datetime.date.fromisoformat(date) - datetime.timedelta(days=1)
    ).isoformat()

    # 1. Equity snapshot (as-of date)
    snap = ledger.equity_snapshot(as_of=date)
    total_equity = snap.get("total_equity", 0.0)
    market_value = snap.get("market_value", 0.0)
    cash = snap.get("cash", 0.0)

    # 2. Daily equity for pnl / return
    daily = ledger.daily_equity(start=date, end=date, freq="D")
    daily_pnl = None
    daily_return_pct = None
    external_cashflow = 0.0
    if daily:
        r = daily[-1]
        daily_pnl = r.get("daily_pnl")
        daily_return_pct = r.get("daily_return_pct")
        external_cashflow = r.get("external_cashflow", 0.0) or 0.0

    # 3. Attribution (prev_date → date)
    from .perf import perf_attribution
    try:
        attr = perf_attribution(start=prev_date, end=date, top_n=5, ledger=ledger)
        top_contributors = attr["top_gainers"]
        top_losers = attr["top_losers"]
    except Exception:
        top_contributors = []
        top_losers = []

    # 4. Rebalance alerts
    from .rebalance import rebalance_check
    try:
        rb = rebalance_check(as_of=date, ledger=ledger)
        alerts = rb.get("alerts", [])
    except Exception:
        alerts = []

    return {
        "total_equity":      total_equity,
        "daily_pnl":         daily_pnl,
        "daily_return_pct":  daily_return_pct,
        "external_cashflow": external_cashflow,
        "market_value":      market_value,
        "cash":              cash,
        "top_contributors":  top_contributors,
        "top_losers":        top_losers,
        "alerts":            alerts,
    }


def generate_and_save(ledger: StockLedger, date: str, overwrite: bool = False) -> dict:
    """Generate digest for *date* and upsert into DB. Returns the saved row."""
    _ldb = ledger.db_path
    ensure_digest_table(_ldb)
    data = _generate_digest_data(ledger, date)
    now = datetime.datetime.now(TZ).isoformat()

    with sqlite3.connect(_ldb) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT id FROM daily_digest WHERE date = ?", (date,)
        ).fetchone()

        if existing and not overwrite:
            raise HTTPException(
                status_code=409,
                detail=f"Digest for {date} already exists. Pass ?overwrite=true to replace.",
            )

        if existing and overwrite:
            conn.execute(
                """
                UPDATE daily_digest SET
                    created_at = ?,
                    total_equity = ?, daily_pnl = ?, daily_return_pct = ?,
                    external_cashflow = ?, market_value = ?, cash = ?,
                    top_contributors_json = ?, top_losers_json = ?, alerts_json = ?
                WHERE date = ?
                """,
                (
                    now,
                    data["total_equity"], data["daily_pnl"], data["daily_return_pct"],
                    data["external_cashflow"], data["market_value"], data["cash"],
                    json.dumps(data["top_contributors"]),
                    json.dumps(data["top_losers"]),
                    json.dumps(data["alerts"]),
                    date,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO daily_digest
                    (date, created_at, total_equity, daily_pnl, daily_return_pct,
                     external_cashflow, market_value, cash,
                     top_contributors_json, top_losers_json, alerts_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    date, now,
                    data["total_equity"], data["daily_pnl"], data["daily_return_pct"],
                    data["external_cashflow"], data["market_value"], data["cash"],
                    json.dumps(data["top_contributors"]),
                    json.dumps(data["top_losers"]),
                    json.dumps(data["alerts"]),
                ),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM daily_digest WHERE date = ?", (date,)
        ).fetchone()
    return dict(row)


def _row_to_out(row: dict) -> DigestOut:
    return DigestOut(
        id=row["id"],
        date=row["date"],
        created_at=row["created_at"],
        total_equity=row.get("total_equity"),
        daily_pnl=row.get("daily_pnl"),
        daily_return_pct=row.get("daily_return_pct"),
        external_cashflow=row.get("external_cashflow"),
        market_value=row.get("market_value"),
        cash=row.get("cash"),
        top_contributors=json.loads(row["top_contributors_json"]) if row.get("top_contributors_json") else None,
        top_losers=json.loads(row["top_losers_json"]) if row.get("top_losers_json") else None,
        alerts=json.loads(row["alerts_json"]) if row.get("alerts_json") else None,
        notes=row.get("notes"),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post(
    "/digest/generate",
    response_model=DigestOut,
    status_code=201,
    summary="Generate (or regenerate) a daily digest",
)
def generate_digest(
    date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today Asia/Taipei)"),
    overwrite: bool = Query(False, description="Replace existing digest if present"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Compute and persist the daily digest for *date*.

    **409** is returned if the digest already exists and `overwrite=false`.
    Pass `?overwrite=true` to regenerate.
    """
    if date is None:
        date = datetime.datetime.now(TZ).strftime("%Y-%m-%d")

    row = generate_and_save(ledger=ledger, date=date, overwrite=overwrite)
    return _row_to_out(row)


@router.get(
    "/digest/{date}",
    response_model=DigestOut,
    summary="Get the digest for a specific date",
)
def get_digest(date: str, ledger: StockLedger = Depends(get_ledger)):
    ensure_digest_table(ledger.db_path)
    with sqlite3.connect(ledger.db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM daily_digest WHERE date = ?", (date,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"No digest found for {date}")
    return _row_to_out(dict(row))


@router.get(
    "/digest",
    response_model=list[DigestSummary],
    summary="List digests in a date range",
)
def list_digests(
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(30, ge=1, le=365),
):
    ensure_digest_table()
    clauses: list[str] = []
    params: list = []
    if start:
        clauses.append("date >= ?")
        params.append(start)
    if end:
        clauses.append("date <= ?")
        params.append(end)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT date, total_equity, daily_pnl, daily_return_pct, notes "
            f"FROM daily_digest {where} ORDER BY date DESC LIMIT ?",
            params,
        ).fetchall()
    return [DigestSummary(**dict(r)) for r in rows]


@router.patch(
    "/digest/{date}/notes",
    response_model=DigestOut,
    summary="Update the notes field of a digest",
)
def patch_notes(date: str, body: PatchNotesBody):
    ensure_digest_table()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            "SELECT id FROM daily_digest WHERE date = ?", (date,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"No digest found for {date}")
        conn.execute(
            "UPDATE daily_digest SET notes = ? WHERE date = ?",
            (body.notes, date),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM daily_digest WHERE date = ?", (date,)).fetchone()
    return _row_to_out(dict(row))
