"""FastAPI dependency: shared StockLedger instance."""
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ledger import StockLedger
from .config import DB_PATH

_ledger: StockLedger | None = None


def init_ledger() -> None:
    """Called once at application startup."""
    global _ledger
    _ledger = StockLedger(db_path=DB_PATH)


def get_ledger() -> StockLedger:
    """FastAPI dependency: returns the shared ledger (thread-safe; each method opens its own connection)."""
    if _ledger is None:
        raise RuntimeError("Ledger not initialised – startup event did not run")
    return _ledger
