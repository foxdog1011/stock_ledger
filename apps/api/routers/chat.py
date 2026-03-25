"""AI portfolio analyst chat endpoint (SSE streaming)."""
from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import date, timedelta
from typing import Any, Generator

import httpx
from anthropic import Anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import get_ledger
from ledger import StockLedger

router = APIRouter()

MCP_URL = os.getenv("MCP_URL", "http://mcp:8001/mcp")

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


# ---------------------------------------------------------------------------
# MCP client helpers (streamable-http with session + SSE parsing)
# ---------------------------------------------------------------------------

_MCP_SESSION_ID: str | None = None
_MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def _parse_sse(text: str) -> Any:
    """Extract JSON payload from an SSE response body."""
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    return json.loads(text)  # fallback: plain JSON


def _mcp_init() -> str | None:
    """Initialize an MCP session and return the session ID."""
    try:
        resp = httpx.post(
            MCP_URL,
            json={
                "jsonrpc": "2.0", "id": 0, "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "jarvis", "version": "1.0"},
                },
            },
            headers=_MCP_HEADERS,
            timeout=10.0,
        )
        return resp.headers.get("mcp-session-id")
    except Exception:
        return None


def _mcp_post(payload: dict) -> Any:
    """POST a JSON-RPC request to the MCP server, managing the session."""
    global _MCP_SESSION_ID
    if _MCP_SESSION_ID is None:
        _MCP_SESSION_ID = _mcp_init()

    headers = {**_MCP_HEADERS}
    if _MCP_SESSION_ID:
        headers["mcp-session-id"] = _MCP_SESSION_ID

    resp = httpx.post(MCP_URL, json=payload, headers=headers, timeout=30.0)
    if resp.status_code == 400:
        # Session expired — re-initialize once
        _MCP_SESSION_ID = _mcp_init()
        if _MCP_SESSION_ID:
            headers["mcp-session-id"] = _MCP_SESSION_ID
        resp = httpx.post(MCP_URL, json=payload, headers=headers, timeout=30.0)

    resp.raise_for_status()
    return _parse_sse(resp.text)


def _mcp_call(name: str, arguments: dict) -> Any:
    """Call a tool on the MCP server and return parsed result."""
    try:
        data = _mcp_post({
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        })
        if "error" in data:
            return {"error": data["error"].get("message", str(data["error"]))}
        content = data.get("result", {}).get("content", [])
        if content and content[0].get("type") == "text":
            return json.loads(content[0]["text"])
        return {"error": "No content in MCP response"}
    except Exception as exc:
        return {"error": str(exc), "tool": name}


def _fetch_mcp_tools() -> list[dict]:
    """Fetch available tools from MCP server, converted to Anthropic tool format."""
    try:
        data = _mcp_post({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = data.get("result", {}).get("tools", [])
        return [
            {
                "name": t["name"],
                "description": t.get("description", ""),
                "input_schema": t.get("inputSchema", {"type": "object", "properties": {}}),
            }
            for t in tools
        ]
    except Exception:
        return TOOLS  # fallback to hardcoded tools if MCP is unavailable


def _run_tool(name: str, input_: dict, ledger: StockLedger) -> Any:
    """Proxy tool calls to the MCP server."""
    return _mcp_call(name, input_)


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _stream_chat(messages: list[dict], ledger: StockLedger, page_context: str = "") -> Generator[str, None, None]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        yield _sse_event({"type": "error", "text": "ANTHROPIC_API_KEY is not configured on the server."})
        return

    try:
        client = Anthropic(api_key=api_key)
        system = SYSTEM_PROMPT.format(
            today=date.today().isoformat(),
            page_label=page_context or "unknown page",
        )
        current_messages = list(messages)
        available_tools = _fetch_mcp_tools()

        # ── Agentic loop: run tool calls until the model stops requesting them ──
        while True:
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=2048,
                system=system,
                tools=available_tools,
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

    except Exception as exc:
        yield _sse_event({"type": "error", "text": f"J.A.R.V.I.S. error: {exc}"})


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
