"""FinMind price provider.

Uses the FinMind public API (TaiwanStockPrice dataset).
Requires FINMIND_TOKEN environment variable.

API reference:
  https://finmindtrade.com/analysis/#/data/api
  POST https://api.finmindtrade.com/api/v4/data
    dataset=TaiwanStockPrice
    data_id=<symbol>
    start_date=YYYY-MM-DD
    token=<FINMIND_TOKEN>
"""
from __future__ import annotations

import datetime
import json
import os
import urllib.parse
import urllib.request
from typing import Optional

from .base import PriceProvider, PriceRecord

_API_URL = "https://api.finmindtrade.com/api/v4/data"


class FinMindProvider(PriceProvider):
    name = "finmind"

    def _token(self) -> str:
        token = os.getenv("FINMIND_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "FINMIND_TOKEN environment variable is not set. "
                "Set it to your FinMind API token to use the finmind provider."
            )
        return token

    def get_latest_close(self, symbol: str, as_of: str) -> Optional[PriceRecord]:
        token = self._token()
        # Look back 14 days to cover weekends + holidays
        start = (
            datetime.date.fromisoformat(as_of) - datetime.timedelta(days=14)
        ).isoformat()

        params = urllib.parse.urlencode({
            "dataset": "TaiwanStockPrice",
            "data_id": symbol,
            "start_date": start,
            "token": token,
        })
        url = f"{_API_URL}?{params}"

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "stock-ledger/1.0"},
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            raise ValueError(f"FinMind API request failed: {exc}") from exc

        status = data.get("status", 0)
        if status != 200:
            msg = data.get("msg", f"status={status}")
            raise ValueError(f"FinMind API error: {msg}")

        rows = data.get("data", [])
        if not rows:
            return None

        # Filter to on or before as_of, then take the latest
        valid = [r for r in rows if r.get("date", "") <= as_of]
        if not valid:
            return None

        latest = max(valid, key=lambda r: r["date"])
        return PriceRecord(
            symbol=symbol,
            date=latest["date"],
            close=float(latest["Close"]),
        )

    # get_bulk_close inherited from PriceProvider (per-symbol loop)
