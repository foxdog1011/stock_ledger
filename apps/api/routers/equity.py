"""Equity snapshot and curve endpoints."""
from typing import Optional
import math
from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_ledger
from ..schemas import EquityCurvePoint
from ledger import StockLedger

router = APIRouter()

_VALID_FREQS = {"D", "W", "ME", "QE", "YE"}


@router.get("/equity/snapshot", summary="Point-in-time portfolio snapshot")
def equity_snapshot(
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD  (default: today)"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Return a single-date snapshot:

    ```json
    {
      "date": "2024-12-31",
      "cash": 1351450.0,
      "market_value": 1175000.0,
      "total_equity": 2526450.0,
      "positions": {
        "2330": {"qty": 500, "price": 1000.0, "market_value": 500000.0},
        "2317": {"qty": 5000, "price": 135.0,  "market_value": 675000.0}
      }
    }
    ```
    """
    return ledger.equity_snapshot(as_of=as_of)


@router.get(
    "/equity/curve",
    response_model=list[EquityCurvePoint],
    summary="Time-series equity curve",
)
def equity_curve(
    start: str = Query(..., description="YYYY-MM-DD"),
    end: str = Query(..., description="YYYY-MM-DD"),
    freq: str = Query("ME", description="Pandas offset: D | W | ME | QE | YE"),
    ledger: StockLedger = Depends(get_ledger),
):
    """
    Build an equity curve between `start` and `end` at the requested frequency.

    | freq | meaning       |
    |------|---------------|
    | D    | daily         |
    | W    | weekly (Sun)  |
    | ME   | month-end     |
    | QE   | quarter-end   |
    | YE   | year-end      |

    Returns a list of records with:
    `date, cash, market_value, total_equity, return_pct, cum_return_pct`
    """
    if freq not in _VALID_FREQS:
        raise HTTPException(
            status_code=422,
            detail=f"freq must be one of {sorted(_VALID_FREQS)}, got '{freq}'",
        )

    try:
        from ledger.equity import equity_curve as _curve
        df = _curve(ledger, start=start, end=end, freq=freq)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Convert DataFrame → list[dict], replacing NaN with None
    records = df.reset_index().to_dict(orient="records")
    for r in records:
        r["date"] = str(r["date"])
        for key in ("return_pct", "cum_return_pct"):
            val = r.get(key)
            if val is not None and (isinstance(val, float) and math.isnan(val)):
                r[key] = None

    return records
