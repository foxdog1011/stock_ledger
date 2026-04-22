"""Abstract price provider."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class PriceRecord:
    symbol: str
    date: str   # YYYY-MM-DD
    close: float


class PriceProvider(ABC):
    name: str = "base"

    @abstractmethod
    def get_latest_close(self, symbol: str, as_of: str) -> Optional[PriceRecord]:
        """Return the most-recent closing price on or before *as_of*, or None."""
        ...

    def get_bulk_close(
        self, symbols: list[str], as_of: str
    ) -> dict[str, PriceRecord]:
        """Fetch closing prices for multiple symbols.

        Default implementation calls :meth:`get_latest_close` per symbol.
        Sub-classes with a true bulk API (e.g. TWSE) should override this.
        """
        result: dict[str, PriceRecord] = {}
        for sym in symbols:
            try:
                rec = self.get_latest_close(sym, as_of)
                if rec:
                    result[sym] = rec
            except Exception:
                pass
        return result
