"""Auto provider selector.

Resolution order:
  1. If provider arg is "twse"    → TWSeProvider
  2. If provider arg is "finmind" → FinMindProvider
  3. If provider arg is "yahoo"   → YahooProvider
  4. If provider arg is "auto" (or anything else):
       a. FINMIND_TOKEN env set → FinMindProvider (TW stocks only)
       b. otherwise → SmartProvider:
            - symbols that look like TW tickers (≤6 digits) → TWSE
            - everything else                               → Yahoo Finance

SmartProvider handles mixed TW + US portfolios automatically.
"""
from __future__ import annotations

import os
import re
from typing import Optional

from .base import PriceProvider, PriceRecord
from .twse import TWSeProvider
from .finmind import FinMindProvider
from .yahoo import YahooProvider

_TW_PATTERN = re.compile(r"^\d{4,6}$")


def _is_tw_symbol(symbol: str) -> bool:
    return bool(_TW_PATTERN.match(symbol))


class SmartProvider(PriceProvider):
    """Routes Taiwan symbols to TWSE and everything else to Yahoo Finance."""

    name = "auto"

    def __init__(self) -> None:
        self._twse = TWSeProvider()
        self._yahoo = YahooProvider()

    def get_bulk_close(
        self, symbols: list[str], as_of: str
    ) -> dict[str, PriceRecord]:
        tw_syms = [s for s in symbols if _is_tw_symbol(s)]
        us_syms = [s for s in symbols if not _is_tw_symbol(s)]

        result: dict[str, PriceRecord] = {}

        if tw_syms:
            result.update(self._twse.get_bulk_close(tw_syms, as_of))

        if us_syms:
            result.update(self._yahoo.get_bulk_close(us_syms, as_of))

        return result

    def get_latest_close(self, symbol: str, as_of: str) -> Optional[PriceRecord]:
        provider = self._twse if _is_tw_symbol(symbol) else self._yahoo
        return provider.get_latest_close(symbol, as_of)


def get_provider(name: str = "auto") -> PriceProvider:
    name = (name or "auto").lower().strip()
    if name == "twse":
        return TWSeProvider()
    if name == "finmind":
        return FinMindProvider()
    if name == "yahoo":
        return YahooProvider()
    # auto
    if os.getenv("FINMIND_TOKEN", "").strip():
        return FinMindProvider()
    return SmartProvider()


def effective_provider_name() -> str:
    """Return the provider that 'auto' would resolve to."""
    if os.getenv("FINMIND_TOKEN", "").strip():
        return "finmind"
    return "auto (twse + yahoo)"
