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
