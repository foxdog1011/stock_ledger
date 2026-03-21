"""AI portfolio analyst chat endpoint (SSE streaming)."""
from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import date, timedelta
from typing import Any, Generator

from anthropic import Anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()

SYSTEM_PROMPT = """\
You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), an AI portfolio analyst \
embedded in Stock Ledger.

You have direct access to the user's real-time investment data through specialized tools. \
Always call the appropriate tools to retrieve current data before answering — never estimate \
or approximate portfolio figures.

Operational parameters:
- Be precise, direct, and confident. Prefer concise responses with clear numbers.
- Format currency with commas (e.g. $1,234,567). Use explicit +/− prefix for P&L.
- When multiple data points are relevant, present them in a clear, structured way.
- If asked for a recommendation or analysis, be decisive and ground it in the data.
- You may occasionally refer to the user's portfolio activity in a confident, observational tone.

Write capabilities:
- You can record trades and cash entries using add_trade and add_cash tools.
- When the user says they bought/sold stocks or deposited/withdrew cash, extract all details \
(date, symbol, qty, price, commission, tax) and call the appropriate tool.
- If any required field is ambiguous, ask for clarification before writing.
- After writing, confirm exactly what was recorded (e.g. "Recorded: BUY 100 AAPL @ $150.00 on 2024-01-15").
- Use today's date ({today}) if the user doesn't specify a date.

Current context: The user is on the {page_label} page. Today: {today}.\
"""

TOOLS: list[dict] = [
    {
        "name": "get_portfolio_snapshot",
        "description": (
            "Get current portfolio snapshot: total equity, cash, market value, "
            "position count, unrealized P&L summary."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_positions",
        "description": (
            "Get stock positions with quantity, average cost, last price, "
            "market value, unrealized P&L and realized P&L."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "include_closed": {
                    "type": "boolean",
                    "description": "Include closed (zero-qty) positions",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_cash_balance",
        "description": "Get current cash balance.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_recent_trades",
        "description": "Get recent trade history (buy/sell records).",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of trades to return (default 20)",
                    "default": 20,
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_lots",
        "description": (
            "Get individual purchase lot details for a specific stock: "
            "lot date, qty, cost, unrealized P&L per lot."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Stock symbol e.g. AAPL, 2330"},
                "method": {
                    "type": "string",
                    "enum": ["fifo", "lifo", "avg"],
                    "description": "Cost accounting method (default fifo)",
                    "default": "fifo",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_perf_summary",
        "description": (
            "Get performance summary for a date range: P&L ex-cashflow, "
            "realized P&L, unrealized P&L, fees paid."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start date YYYY-MM-DD (default: 1 year ago)"},
                "end": {"type": "string", "description": "End date YYYY-MM-DD (default: today)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_risk_metrics",
        "description": (
            "Get risk metrics for a date range: Sharpe ratio, volatility, "
            "best/worst single day, win rate."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start": {"type": "string", "description": "Start date YYYY-MM-DD (default: 1 year ago)"},
                "end": {"type": "string", "description": "End date YYYY-MM-DD (default: today)"},
            },
            "required": [],
        },
    },
    {
        "name": "add_trade",
        "description": (
            "Record a buy or sell trade. Use when the user says they bought or sold a stock. "
            "Returns the saved trade details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Trade date YYYY-MM-DD"},
                "symbol": {"type": "string", "description": "Stock ticker symbol e.g. AAPL, 2330"},
                "side": {"type": "string", "enum": ["buy", "sell"], "description": "buy or sell"},
                "qty": {"type": "number", "description": "Number of shares (positive)"},
                "price": {"type": "number", "description": "Price per share"},
                "commission": {"type": "number", "description": "Brokerage commission (default 0)", "default": 0},
                "tax": {"type": "number", "description": "Transaction tax (default 0)", "default": 0},
                "note": {"type": "string", "description": "Optional note", "default": ""},
            },
            "required": ["date", "symbol", "side", "qty", "price"],
        },
    },
    {
        "name": "add_cash",
        "description": (
            "Record a cash deposit or withdrawal. Use when the user mentions depositing "
            "or withdrawing money from their account. "
            "Positive amount = deposit, negative = withdrawal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date YYYY-MM-DD"},
                "amount": {"type": "number", "description": "Amount: positive = deposit, negative = withdrawal"},
                "note": {"type": "string", "description": "Optional note", "default": ""},
            },
            "required": ["date", "amount"],
        },
    },
]


def _default_range() -> tuple[str, str]:
    today = date.today()
    return (today - timedelta(days=365)).isoformat(), today.isoformat()


def _run_tool(name: str, input_: dict, ledger: StockLedger) -> Any:
    if name == "get_portfolio_snapshot":
        return ledger.equity_snapshot()

    if name == "get_positions":
        return ledger.position_pnl(include_closed=input_.get("include_closed", False))

    if name == "get_cash_balance":
        return {"balance": ledger.cash_balance()}

    if name == "get_recent_trades":
        limit = int(input_.get("limit", 20))
        return ledger.trade_history()[:limit]

    if name == "get_lots":
        return ledger.lots_by_method(input_["symbol"].upper(), input_.get("method", "fifo"))

    if name == "get_perf_summary":
        default_start, default_end = _default_range()
        start = input_.get("start") or default_start
        end = input_.get("end") or default_end
        daily = ledger.daily_equity(start=start, end=end, freq="B")
        if not daily:
            return {"error": "No equity data for this range"}
        external_cf = sum(d["external_cashflow"] for d in daily)
        with sqlite3.connect(str(ledger.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT SUM(commission) AS c, SUM(tax) AS t FROM trades"
                " WHERE date >= ? AND date <= ? AND is_void = 0",
                (start, end),
            ).fetchone()
        return {
            "start": start,
            "end": end,
            "start_equity": daily[0]["total_equity"],
            "end_equity": daily[-1]["total_equity"],
            "pnl_ex_cashflow": round(daily[-1]["total_equity"] - daily[0]["total_equity"] - external_cf, 2),
            "external_cashflow_sum": round(external_cf, 2),
            "fees_commission": round(float(row["c"] or 0), 2),
            "fees_tax": round(float(row["t"] or 0), 2),
        }

    if name == "get_risk_metrics":
        default_start, default_end = _default_range()
        start = input_.get("start") or default_start
        end = input_.get("end") or default_end
        daily = ledger.daily_equity(start=start, end=end, freq="B")
        returns = [d["daily_return_pct"] for d in daily if d.get("daily_return_pct") is not None]
        if not returns:
            return {"error": "No return data for this range"}
        n = len(returns)
        avg = sum(returns) / n
        variance = sum((r - avg) ** 2 for r in returns) / n if n > 1 else 0.0
        std_dev = math.sqrt(variance) if variance > 0 else 0.0
        return {
            "start": start,
            "end": end,
            "sharpe_ratio": round((avg / std_dev) * math.sqrt(252), 4) if std_dev > 0 else None,
            "positive_day_ratio": round(sum(1 for r in returns if r > 0) / n * 100, 2),
            "worst_day_pct": round(min(returns), 4),
            "best_day_pct": round(max(returns), 4),
            "trading_days": n,
            "volatility_pct": round(std_dev, 4),
        }

    if name == "add_trade":
        symbol = input_["symbol"].upper()
        trade_id = ledger.add_trade(
            date=input_["date"],
            symbol=symbol,
            side=input_["side"],
            qty=float(input_["qty"]),
            price=float(input_["price"]),
            commission=float(input_.get("commission") or 0),
            tax=float(input_.get("tax") or 0),
            note=str(input_.get("note") or ""),
        )
        total = float(input_["qty"]) * float(input_["price"])
        return {
            "status": "ok",
            "trade_id": trade_id,
            "date": input_["date"],
            "symbol": symbol,
            "side": input_["side"],
            "qty": float(input_["qty"]),
            "price": float(input_["price"]),
            "commission": float(input_.get("commission") or 0),
            "tax": float(input_.get("tax") or 0),
            "total": round(total, 2),
        }

    if name == "add_cash":
        ledger.add_cash(
            date=input_["date"],
            amount=float(input_["amount"]),
            note=str(input_.get("note") or ""),
        )
        return {
            "status": "ok",
            "date": input_["date"],
            "amount": float(input_["amount"]),
            "type": "deposit" if float(input_["amount"]) >= 0 else "withdrawal",
        }

    return {"error": f"Unknown tool: {name}"}


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _stream_chat(messages: list[dict], ledger: StockLedger, page_context: str = "") -> Generator[str, None, None]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        yield _sse_event({"type": "error", "text": "ANTHROPIC_API_KEY is not configured on the server."})
        return

    client = Anthropic(api_key=api_key)
    system = SYSTEM_PROMPT.format(
        today=date.today().isoformat(),
        page_label=page_context or "unknown page",
    )
    current_messages = list(messages)

    # ── Agentic loop: run tool calls until the model stops requesting them ──
    while True:
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=2048,
            system=system,
            tools=TOOLS,
            messages=current_messages,
        )

        if response.stop_reason != "tool_use":
            break

        current_messages.append({"role": "assistant", "content": response.content})
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue
            yield _sse_event({"type": "tool_call", "name": block.name})
            try:
                result = _run_tool(block.name, block.input, ledger)
            except Exception as exc:
                result = {"error": str(exc)}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, default=str),
            })

        current_messages.append({"role": "user", "content": tool_results})

    # ── Stream the final text response ──
    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=2048,
        system=system,
        messages=current_messages,
    ) as stream:
        for text in stream.text_stream:
            yield _sse_event({"type": "text", "text": text})

    yield _sse_event({"type": "done"})


# ── Request / endpoint ─────────────────────────────────────────────────────────

class _Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[_Message]
    page_context: str = ""


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, ledger: StockLedger = Depends(get_ledger)):
    """SSE endpoint: streams tool-call events then the final text response."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    return StreamingResponse(
        _stream_chat(messages, ledger, body.page_context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
