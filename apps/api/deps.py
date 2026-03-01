"""FastAPI dependency: shared StockLedger instance."""
import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ledger import StockLedger

_ledger: StockLedger | None = None


def init_ledger() -> None:
    """Called once at application startup."""
    global _ledger
    db_path = Path(os.getenv("DB_PATH", "data/ledger.db"))
    _ledger = StockLedger(db_path=db_path)


def get_ledger() -> StockLedger:
    """FastAPI dependency: returns the shared ledger (thread-safe; each method opens its own connection)."""
    if _ledger is None:
        raise RuntimeError("Ledger not initialised – startup event did not run")
    return _ledger
