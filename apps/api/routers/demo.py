"""Demo seed endpoint – clears all data and inserts a sample portfolio."""
from fastapi import APIRouter, Depends

from ..deps import get_ledger
from ledger import StockLedger
from ledger.db import get_connection

router = APIRouter()

# ── Sample data ───────────────────────────────────────────────────────────────

_CASH = [
    ("2024-01-02", 500_000.0, "Initial deposit"),
    ("2024-07-01", 200_000.0, "Additional capital"),
]

# (date, symbol, side, qty, price, commission, note)
_TRADES = [
    ("2024-01-05", "AAPL",  "buy",  200, 185.20, 20, "Demo seed"),
    ("2024-01-05", "MSFT",  "buy",  100, 374.50, 20, "Demo seed"),
    ("2024-02-20", "TSLA",  "buy",   50, 200.00, 10, "Demo seed"),
    ("2024-04-10", "AAPL",  "sell",  50, 195.00, 10, "Demo seed"),
    ("2024-07-15", "META",  "buy",   20, 490.00, 10, "Demo seed"),
    ("2024-08-20", "GOOGL", "buy",   30, 170.00, 10, "Demo seed"),
]

# (date, symbol, close)  – month-end prices for held positions
_PRICES = [
    # AAPL
    ("2024-01-31","AAPL",183.0), ("2024-02-29","AAPL",180.0), ("2024-03-28","AAPL",171.0),
    ("2024-04-30","AAPL",170.0), ("2024-05-31","AAPL",191.0), ("2024-06-28","AAPL",210.0),
    ("2024-07-31","AAPL",218.0), ("2024-08-30","AAPL",226.0), ("2024-09-30","AAPL",233.0),
    ("2024-10-31","AAPL",225.0), ("2024-11-29","AAPL",237.0), ("2024-12-31","AAPL",248.0),
    ("2025-01-31","AAPL",236.0),
    # MSFT
    ("2024-01-31","MSFT",404.0), ("2024-02-29","MSFT",415.0), ("2024-03-28","MSFT",420.0),
    ("2024-04-30","MSFT",398.0), ("2024-05-31","MSFT",430.0), ("2024-06-28","MSFT",445.0),
    ("2024-07-31","MSFT",412.0), ("2024-08-30","MSFT",428.0), ("2024-09-30","MSFT",441.0),
    ("2024-10-31","MSFT",430.0), ("2024-11-29","MSFT",422.0), ("2024-12-31","MSFT",424.0),
    ("2025-01-31","MSFT",415.0),
    # TSLA
    ("2024-02-29","TSLA",195.0), ("2024-03-28","TSLA",175.0),
    ("2024-04-30","TSLA",148.0), ("2024-05-31","TSLA",178.0), ("2024-06-28","TSLA",182.0),
    ("2024-07-31","TSLA",215.0), ("2024-08-30","TSLA",205.0), ("2024-09-30","TSLA",250.0),
    ("2024-10-31","TSLA",260.0), ("2024-11-29","TSLA",352.0), ("2024-12-31","TSLA",403.0),
    ("2025-01-31","TSLA",380.0),
    # META
    ("2024-07-31","META",495.0), ("2024-08-30","META",520.0), ("2024-09-30","META",565.0),
    ("2024-10-31","META",580.0), ("2024-11-29","META",590.0), ("2024-12-31","META",590.0),
    ("2025-01-31","META",624.0),
    # GOOGL
    ("2024-08-30","GOOGL",170.0), ("2024-09-30","GOOGL",163.0),
    ("2024-10-31","GOOGL",178.0), ("2024-11-29","GOOGL",178.0), ("2024-12-31","GOOGL",191.0),
    ("2025-01-31","GOOGL",197.0),
]


@router.post("/demo/seed", status_code=200, summary="Reset & load demo portfolio data")
def seed_demo(ledger: StockLedger = Depends(get_ledger)):
    """
    **Deletes all existing data** then inserts a sample US-equity portfolio
    spanning Jan 2024 → Jan 2025.

    Positions seeded: AAPL (150), MSFT (100), TSLA (50), META (20), GOOGL (30)
    Monthly close prices are included so the equity curve renders correctly.
    """
    # 1. Clear all tables
    conn = get_connection(ledger.db_path)
    try:
        conn.execute("DELETE FROM prices")
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM cash_entries")
        conn.commit()
    finally:
        conn.close()

    # 2. Seed cash
    for date, amount, note in _CASH:
        ledger.add_cash(amount=amount, date=date, note=note)

    # 3. Seed trades (chronological order; ledger validates cash/share balance)
    for date, symbol, side, qty, price, commission, note in _TRADES:
        ledger.add_trade(
            symbol=symbol, side=side, qty=qty, price=price,
            date=date, commission=commission, note=note,
        )

    # 4. Seed prices
    for date, symbol, close in _PRICES:
        ledger.add_price(symbol=symbol, date=date, close=close)

    return {
        "seeded": True,
        "cash_entries": len(_CASH),
        "trades": len(_TRADES),
        "prices": len(_PRICES),
    }
