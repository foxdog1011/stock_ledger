"""CSV export and import endpoints."""
from __future__ import annotations

import csv
import io
import sqlite3

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()

# ── Helpers ────────────────────────────────────────────────────────────────────


def _csv_response(rows: list[dict], fieldnames: list[str], filename: str) -> StreamingResponse:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _parse_csv(content: bytes) -> list[dict]:
    """Decode (handles UTF-8 BOM) and parse CSV, skipping empty rows."""
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [row for row in reader if any(v.strip() for v in row.values())]


# ── Exports ────────────────────────────────────────────────────────────────────


@router.get("/export/trades.csv", summary="Export trades as CSV")
def export_trades(
    include_void: bool = Query(False),
    ledger: StockLedger = Depends(get_ledger),
):
    trades = ledger.trade_history(include_void=include_void)
    rows = [
        {
            "id": t.get("id", ""),
            "date": t["date"],
            "symbol": t["symbol"],
            "side": t["side"],
            "qty": t["qty"],
            "price": t["price"],
            "commission": t.get("commission", 0),
            "tax": t.get("tax", 0),
            "note": t.get("note", ""),
            "is_void": int(t.get("is_void", 0)),
        }
        for t in trades
    ]
    return _csv_response(
        rows,
        ["id", "date", "symbol", "side", "qty", "price", "commission", "tax", "note", "is_void"],
        "trades.csv",
    )


@router.get("/export/cash.csv", summary="Export cash transactions as CSV")
def export_cash(
    include_void: bool = Query(False),
    ledger: StockLedger = Depends(get_ledger),
):
    flows = ledger.cash_flow(include_void=include_void)
    rows = [
        {
            "id": f.get("id", ""),
            "date": f["date"],
            "type": f["type"],
            "amount": f["amount"],
            "symbol": f.get("symbol", ""),
            "note": f.get("note", ""),
            "balance": f.get("balance", ""),
            "is_void": int(f.get("is_void", 0)),
        }
        for f in flows
    ]
    return _csv_response(
        rows,
        ["id", "date", "type", "amount", "symbol", "note", "balance", "is_void"],
        "cash.csv",
    )


@router.get("/export/quotes.csv", summary="Export price quotes as CSV")
def export_quotes(ledger: StockLedger = Depends(get_ledger)):
    db_path = str(ledger._db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        db_rows = conn.execute(
            "SELECT symbol, date, close FROM prices ORDER BY symbol, date"
        ).fetchall()
    rows = [{"symbol": r["symbol"], "date": r["date"], "close": r["close"]} for r in db_rows]
    return _csv_response(rows, ["symbol", "date", "close"], "quotes.csv")


# ── Imports ────────────────────────────────────────────────────────────────────


@router.post("/import/trades.csv", summary="Import trades from CSV (dry_run=true to validate only)")
async def import_trades(
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    CSV must have columns: ``date, symbol, side, qty, price`` (+ optional ``commission, tax, note``).

    Returns ``{ok, inserted, skipped, errors, dry_run}``.
    ``dry_run=true`` parses and validates without writing to DB.
    """
    content = await file.read()
    rows = _parse_csv(content)
    required = {"date", "symbol", "side", "qty", "price"}
    inserted = 0
    # skipped is reserved for future duplicate-detection logic; currently always 0
    # because every row is either inserted or appended to errors with no third path.
    skipped = 0
    errors: list[dict] = []

    for i, row in enumerate(rows, start=2):
        missing = required - set(k.strip() for k in row.keys())
        if missing:
            errors.append(
                {"row": i, "message": f"Missing columns: {', '.join(sorted(missing))}", "raw": str(row)}
            )
            continue
        try:
            date = row["date"].strip()
            symbol = row["symbol"].strip().upper()
            side = row["side"].strip().lower()
            qty = float(row["qty"])
            price = float(row["price"])
            commission = float(row.get("commission", "") or 0)
            tax = float(row.get("tax", "") or 0)
            note = row.get("note", "").strip()
            if not date or not symbol:
                raise ValueError("date and symbol are required")
            if side not in ("buy", "sell"):
                raise ValueError(f"side must be 'buy' or 'sell', got '{side}'")
            if qty <= 0:
                raise ValueError("qty must be > 0")
            if price <= 0:
                raise ValueError("price must be > 0")
            if commission < 0 or tax < 0:
                raise ValueError("commission and tax must be >= 0")
        except ValueError as exc:
            errors.append({"row": i, "message": str(exc), "raw": str(row)})
            continue

        if dry_run:
            inserted += 1
        else:
            try:
                ledger.add_trade(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                    price=price,
                    date=date,
                    commission=commission,
                    tax=tax,
                    note=note,
                )
                inserted += 1
            except Exception as exc:
                errors.append({"row": i, "message": str(exc), "raw": str(row)})

    return {"ok": len(errors) == 0, "inserted": inserted, "skipped": skipped, "errors": errors, "dry_run": dry_run}


@router.post("/import/cash.csv", summary="Import cash entries from CSV (dry_run=true to validate only)")
async def import_cash(
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    CSV must have columns: ``date, amount`` (+ optional ``note``).
    Only manual deposits / withdrawals (not buy/sell rows) are supported.
    """
    content = await file.read()
    rows = _parse_csv(content)
    required = {"date", "amount"}
    inserted = 0
    # skipped is reserved for future duplicate-detection logic; currently always 0.
    skipped = 0
    errors: list[dict] = []

    for i, row in enumerate(rows, start=2):
        missing = required - set(k.strip() for k in row.keys())
        if missing:
            errors.append(
                {"row": i, "message": f"Missing columns: {', '.join(sorted(missing))}", "raw": str(row)}
            )
            continue
        try:
            date = row["date"].strip()
            amount = float(row["amount"])
            note = row.get("note", "").strip()
            if not date:
                raise ValueError("date is required")
            if amount == 0:
                raise ValueError("amount must be non-zero")
        except ValueError as exc:
            errors.append({"row": i, "message": str(exc), "raw": str(row)})
            continue

        if dry_run:
            inserted += 1
        else:
            try:
                ledger.add_cash(amount=amount, date=date, note=note)
                inserted += 1
            except Exception as exc:
                errors.append({"row": i, "message": str(exc), "raw": str(row)})

    return {"ok": len(errors) == 0, "inserted": inserted, "skipped": skipped, "errors": errors, "dry_run": dry_run}


@router.post("/import/quotes.csv", summary="Import price quotes from CSV (dry_run=true to validate only)")
async def import_quotes(
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    """
    CSV must have columns: ``symbol, date, close``.
    Duplicate (symbol, date) rows are silently upserted.
    """
    content = await file.read()
    rows = _parse_csv(content)
    required = {"symbol", "date", "close"}
    inserted = 0
    # skipped is reserved for future duplicate-detection logic; currently always 0.
    skipped = 0
    errors: list[dict] = []

    for i, row in enumerate(rows, start=2):
        missing = required - set(k.strip() for k in row.keys())
        if missing:
            errors.append(
                {"row": i, "message": f"Missing columns: {', '.join(sorted(missing))}", "raw": str(row)}
            )
            continue
        try:
            symbol = row["symbol"].strip().upper()
            date = row["date"].strip()
            close = float(row["close"])
            if not symbol or not date:
                raise ValueError("symbol and date are required")
            if close <= 0:
                raise ValueError("close must be > 0")
        except ValueError as exc:
            errors.append({"row": i, "message": str(exc), "raw": str(row)})
            continue

        if dry_run:
            inserted += 1
        else:
            try:
                ledger.add_price(symbol=symbol, date=date, close=close)
                inserted += 1
            except Exception as exc:
                errors.append({"row": i, "message": str(exc), "raw": str(row)})

    return {"ok": len(errors) == 0, "inserted": inserted, "skipped": skipped, "errors": errors, "dry_run": dry_run}
