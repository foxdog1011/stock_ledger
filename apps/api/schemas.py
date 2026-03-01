"""Pydantic request / response schemas."""
from __future__ import annotations

from typing import Annotated, Literal, Optional
from pydantic import BaseModel, Field


# ── Cash ─────────────────────────────────────────────────────────────────────

class AddCashIn(BaseModel):
    amount: float = Field(..., description="Positive = deposit, negative = withdrawal")
    date: str = Field(..., description="YYYY-MM-DD")
    note: str = Field("", description="Optional description")


class CashBalanceOut(BaseModel):
    as_of: str
    balance: float


class CashTxOut(BaseModel):
    id: Optional[int]
    date: str
    type: Literal["deposit", "withdrawal", "buy", "sell"]
    amount: float
    symbol: Optional[str]
    note: str
    balance: float
    is_void: bool


# ── Trades ────────────────────────────────────────────────────────────────────

class AddTradeIn(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    qty: Annotated[float, Field(gt=0)]
    price: Annotated[float, Field(gt=0)]
    date: str = Field(..., description="YYYY-MM-DD")
    commission: Annotated[float, Field(ge=0)] = 0.0
    tax: Annotated[float, Field(ge=0)] = 0.0
    note: str = ""


# ── Positions ─────────────────────────────────────────────────────────────────

class PositionOut(BaseModel):
    symbol: str
    qty: float
    avg_cost: Optional[float]
    realized_pnl: float
    unrealized_pnl: Optional[float]
    last_price: Optional[float]
    price_source: Optional[Literal["quote", "trade_fallback"]]
    market_value: Optional[float]


# ── Equity ────────────────────────────────────────────────────────────────────

class EquityCurvePoint(BaseModel):
    date: str
    cash: float
    market_value: float
    total_equity: float
    return_pct: Optional[float]
    cum_return_pct: Optional[float]


# ── Quotes ────────────────────────────────────────────────────────────────────

class AddPriceIn(BaseModel):
    symbol: str
    date: str = Field(..., description="YYYY-MM-DD")
    close: Annotated[float, Field(gt=0)]


class LastPriceOut(BaseModel):
    symbol: str
    price: Optional[float]
    price_source: Optional[Literal["quote", "trade_fallback"]]
