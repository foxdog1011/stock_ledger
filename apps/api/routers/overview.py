"""Overview / dashboard endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_ledger
from ..config import DB_PATH
from ledger import StockLedger

router = APIRouter()


@router.get("/overview", summary="Dashboard overview aggregation")
def get_overview(
    as_of: str | None = Query(None),
    catalyst_days: int = Query(30),
    ledger: StockLedger = Depends(get_ledger),
) -> dict:
    from domain.overview.service import build_overview
    return build_overview(
        db_path=DB_PATH,
        ledger=ledger,
        as_of=as_of,
        catalyst_days=catalyst_days,
    )
