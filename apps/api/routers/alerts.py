"""Price alert endpoints — stop-loss and target-price notifications."""
from __future__ import annotations

import sqlite3
from datetime import date as Date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_ledger
from ..config import DB_PATH
from ledger import StockLedger

router = APIRouter()


# ── Schema ────────────────────────────────────────────────────────────────────

class AlertIn(BaseModel):
    symbol: str
    alert_type: str       # "stop_loss" | "target"
    price: float
    note: str = ""


# ── DB helpers ────────────────────────────────────────────────────────────────

def _ensure_table(db_path: str) -> None:
    with sqlite3.connect(db_path) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS price_alerts (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol      TEXT    NOT NULL,
                alert_type  TEXT    NOT NULL,  -- stop_loss | target
                price       REAL    NOT NULL,
                note        TEXT    DEFAULT '',
                created_at  TEXT    NOT NULL DEFAULT (date('now')),
                triggered   INTEGER NOT NULL DEFAULT 0,
                triggered_at TEXT
            )
        """)


def _get_db_path() -> str:
    return DB_PATH


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/alerts", status_code=201, summary="Set a stop-loss or target-price alert")
def create_alert(body: AlertIn):
    """
    Create a price alert.

    - `alert_type = "stop_loss"` → triggers when price **drops to or below** `price`
    - `alert_type = "target"` → triggers when price **rises to or above** `price`
    """
    if body.alert_type not in ("stop_loss", "target"):
        raise HTTPException(status_code=400, detail="alert_type must be 'stop_loss' or 'target'")

    db_path = _get_db_path()
    _ensure_table(db_path)

    with sqlite3.connect(db_path) as con:
        cur = con.execute(
            "INSERT INTO price_alerts (symbol, alert_type, price, note) VALUES (?,?,?,?)",
            (body.symbol.upper(), body.alert_type, body.price, body.note),
        )
        return {
            "id": cur.lastrowid,
            "symbol": body.symbol.upper(),
            "alert_type": body.alert_type,
            "price": body.price,
            "note": body.note,
        }


@router.get("/alerts", summary="List all price alerts")
def list_alerts(include_triggered: bool = False):
    db_path = _get_db_path()
    _ensure_table(db_path)

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        if include_triggered:
            rows = con.execute("SELECT * FROM price_alerts ORDER BY id").fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM price_alerts WHERE triggered=0 ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]


@router.delete("/alerts/{alert_id}", summary="Delete a price alert")
def delete_alert(alert_id: int):
    db_path = _get_db_path()
    _ensure_table(db_path)

    with sqlite3.connect(db_path) as con:
        affected = con.execute(
            "DELETE FROM price_alerts WHERE id=?", (alert_id,)
        ).rowcount
        if affected == 0:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
        return {"deleted": alert_id}


@router.get("/alerts/check", summary="Check all active alerts against current prices")
def check_alerts(ledger: StockLedger = Depends(get_ledger)):
    """
    Compare each active alert against the latest available price.
    Returns triggered alerts and marks them as triggered in the DB.
    """
    db_path = _get_db_path()
    _ensure_table(db_path)

    today = str(Date.today())

    with sqlite3.connect(db_path) as con:
        con.row_factory = sqlite3.Row
        active = con.execute(
            "SELECT * FROM price_alerts WHERE triggered=0"
        ).fetchall()

    triggered = []
    pending = []

    for alert in active:
        sym = alert["symbol"]
        price_info = ledger.last_price_with_source(symbol=sym, as_of=today)
        current = price_info.get("price")

        if current is None:
            pending.append({**dict(alert), "current_price": None, "status": "no_price"})
            continue

        fired = False
        if alert["alert_type"] == "stop_loss" and current <= alert["price"]:
            fired = True
        elif alert["alert_type"] == "target" and current >= alert["price"]:
            fired = True

        if fired:
            with sqlite3.connect(db_path) as con:
                con.execute(
                    "UPDATE price_alerts SET triggered=1, triggered_at=? WHERE id=?",
                    (today, alert["id"]),
                )
            triggered.append({
                **dict(alert),
                "current_price": current,
                "status": "triggered",
                "gap_pct": round((current - alert["price"]) / alert["price"] * 100, 2),
            })
        else:
            pending.append({
                **dict(alert),
                "current_price": current,
                "status": "pending",
                "gap_pct": round((current - alert["price"]) / alert["price"] * 100, 2),
            })

    return {
        "triggered": triggered,
        "pending": pending,
        "summary": {
            "total_active": len(active),
            "triggered_now": len(triggered),
            "still_pending": len(pending),
        },
    }
