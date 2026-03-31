"""AI portfolio analyst chat endpoint (SSE streaming)."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any, Generator

import httpx
from anthropic import Anthropic
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import DB_PATH as _CONFIG_DB_PATH
from ..deps import get_ledger
from ledger import StockLedger

DB_PATH = str(_CONFIG_DB_PATH)

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
        "name": "get_company_research",
        "description": (
            "Get fundamental research profile for a Taiwan stock from the My-TW-Coverage database. "
            "Returns company description, sector, industry, supply chain relationships, "
            "customer/supplier links, and investment themes. Use when the user asks about "
            "a company's business, background, or wants fundamental context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "4-digit Taiwan stock ticker e.g. '2330'"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "find_supply_chain",
        "description": (
            "Find upstream and downstream supply chain companies for a Taiwan stock. "
            "Also returns related companies that mention this stock in their own supply chain. "
            "Use when the user asks about supply chain beneficiaries, ecosystem plays, or "
            "who benefits when a particular company grows."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "4-digit Taiwan stock ticker e.g. '2330'"},
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "screen_by_theme",
        "description": (
            "List all Taiwan stocks tagged with an investment theme. "
            "Themes include: AI_伺服器, ABF_載板, CoWoS, HBM, NVIDIA, EUV, 5G, CPO, Apple, etc. "
            "Use when the user asks for stock ideas around a sector trend or thematic play."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "theme": {"type": "string", "description": "Theme name e.g. 'AI_伺服器', 'HBM', '5G'"},
            },
            "required": ["theme"],
        },
    },
    {
        "name": "compare_benchmark",
        "description": (
            "Compare portfolio cumulative return against a benchmark index. "
            "Returns excess return, tracking error, correlation, and information ratio. "
            "Available benchmarks: 0050 (Taiwan 50 ETF), TAIEX, 0056, SPY, QQQ. "
            "Use when the user asks how their portfolio compares to the market."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "bench": {"type": "string", "description": "Benchmark ticker e.g. '0050', 'SPY'", "default": "0050"},
                "start": {"type": "string", "description": "Start date YYYY-MM-DD (default: 1 year ago)"},
                "end":   {"type": "string", "description": "End date YYYY-MM-DD (default: today)"},
            },
            "required": [],
        },
    },
    {
        "name": "get_quote",
        "description": (
            "Get a comprehensive real-time quote for any stock: current price, "
            "change %, volume, PE ratio, market cap, 52-week range, dividend yield. "
            "Use when the user asks for the current price or basic market data of a stock."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker e.g. AAPL, 2330, 0050"},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_technical_indicators",
        "description": (
            "Compute technical indicators for a stock: Moving Averages (MA5/20/60), "
            "RSI-14 (overbought/oversold), MACD (12/26/9 with trend signal), "
            "and Bollinger Bands (20-day ±2σ). Use when the user asks about trends, "
            "entry/exit signals, or technical analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker e.g. AAPL, 2330"},
                "days": {"type": "integer", "description": "History window in trading days (default 120)", "default": 120},
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_news",
        "description": (
            "Fetch recent news headlines for a stock. Use when the user asks about "
            "latest news, catalysts, or market sentiment for a company."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker e.g. AAPL, 2330"},
                "count": {"type": "integer", "description": "Number of articles (default 5, max 10)", "default": 5},
            },
            "required": ["symbol"],
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

import threading as _threading

_MCP_SESSION_ID: str | None = None
_MCP_SESSION_LOCK = _threading.Lock()
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
    with _MCP_SESSION_LOCK:
        if _MCP_SESSION_ID is None:
            _MCP_SESSION_ID = _mcp_init()
        session_id = _MCP_SESSION_ID

    headers = {**_MCP_HEADERS}
    if session_id:
        headers["mcp-session-id"] = session_id

    resp = httpx.post(MCP_URL, json=payload, headers=headers, timeout=30.0)
    if resp.status_code == 400:
        # Session expired — re-initialize once
        with _MCP_SESSION_LOCK:
            _MCP_SESSION_ID = _mcp_init()
            session_id = _MCP_SESSION_ID
        if session_id:
            headers["mcp-session-id"] = session_id
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


def _run_research_tool(name: str, input_: dict) -> Any:
    """Handle research tool calls directly via SQLite (no MCP required)."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        if name == "get_company_research":
            ticker = input_["ticker"]
            company = con.execute(
                "SELECT ticker, name, sector, industry, market_cap, ev, description "
                "FROM research_companies WHERE ticker = ?", (ticker,)
            ).fetchone()
            if company is None:
                return {"error": f"Ticker '{ticker}' not found in research database"}
            sc = con.execute(
                "SELECT direction, entity, role_note FROM research_supply_chain "
                "WHERE ticker = ? ORDER BY direction, entity", (ticker,)
            ).fetchall()
            custs = con.execute(
                "SELECT counterpart, is_customer, note FROM research_customers "
                "WHERE ticker = ? ORDER BY counterpart", (ticker,)
            ).fetchall()
            themes = con.execute(
                "SELECT theme FROM research_themes WHERE ticker = ? ORDER BY theme", (ticker,)
            ).fetchall()
            return {
                "ticker": company["ticker"], "name": company["name"],
                "sector": company["sector"], "industry": company["industry"],
                "market_cap_million_twd": company["market_cap"],
                "ev_million_twd": company["ev"], "description": company["description"],
                "supply_chain": [
                    {"direction": r["direction"], "entity": r["entity"], "role_note": r["role_note"]}
                    for r in sc
                ],
                "customers": [
                    {"counterpart": r["counterpart"], "is_customer": bool(r["is_customer"]), "note": r["note"]}
                    for r in custs
                ],
                "themes": [r["theme"] for r in themes],
            }

        if name == "find_supply_chain":
            ticker = input_["ticker"]
            name_row = con.execute(
                "SELECT name FROM research_companies WHERE ticker = ?", (ticker,)
            ).fetchone()
            if name_row is None:
                return {"error": f"Ticker '{ticker}' not found in research database"}
            company_name = name_row["name"]
            sc = con.execute(
                "SELECT direction, entity, role_note FROM research_supply_chain "
                "WHERE ticker = ? ORDER BY direction, entity", (ticker,)
            ).fetchall()
            related = con.execute(
                """
                SELECT DISTINCT sc.ticker, rc.name, rc.industry
                FROM research_supply_chain sc
                JOIN research_companies rc ON rc.ticker = sc.ticker
                WHERE sc.ticker != ? AND (sc.entity LIKE ? OR sc.entity LIKE ?)
                ORDER BY rc.name
                """,
                (ticker, f"%{ticker}%", f"%{company_name}%"),
            ).fetchall()
            return {
                "ticker": ticker, "name": company_name,
                "upstream": [
                    {"entity": r["entity"], "role_note": r["role_note"]}
                    for r in sc if r["direction"] == "upstream"
                ],
                "downstream": [
                    {"entity": r["entity"], "role_note": r["role_note"]}
                    for r in sc if r["direction"] == "downstream"
                ],
                "related_companies": [
                    {"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]}
                    for r in related
                ],
            }

        if name == "screen_by_theme":
            theme = input_["theme"]
            rows = con.execute(
                """
                SELECT rc.ticker, rc.name, rc.industry
                FROM research_themes rt
                JOIN research_companies rc ON rc.ticker = rt.ticker
                WHERE rt.theme = ? ORDER BY rc.name
                """,
                (theme,),
            ).fetchall()
            if not rows:
                available = con.execute(
                    "SELECT theme, COUNT(*) as cnt FROM research_themes "
                    "GROUP BY theme ORDER BY cnt DESC"
                ).fetchall()
                return {
                    "error": f"Theme '{theme}' not found",
                    "available_themes": [r["theme"] for r in available],
                }
            return {
                "theme": theme, "total": len(rows),
                "companies": [
                    {"ticker": r["ticker"], "name": r["name"], "industry": r["industry"]}
                    for r in rows
                ],
            }

        return {"error": f"Unknown research tool: {name}"}
    finally:
        con.close()


_RESEARCH_TOOLS = {"get_company_research", "find_supply_chain", "screen_by_theme"}


# ===========================================================================
# Conversation memory (SQLite-backed)
# ===========================================================================

_MEMORY_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS chat_memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT    NOT NULL,
    role       TEXT    NOT NULL,
    content    TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
)
"""
_MEMORY_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_chat_memory_session ON chat_memory(session_id, id)"
_MEMORY_CONTEXT_LIMIT = 20  # max messages loaded from history


def _memory_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute(_MEMORY_CREATE_SQL)
    con.execute(_MEMORY_INDEX_SQL)
    con.commit()
    return con


def _load_memory(session_id: str) -> list[dict]:
    """Load the last N messages for a session."""
    try:
        with _memory_db() as con:
            rows = con.execute(
                "SELECT role, content FROM chat_memory "
                "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, _MEMORY_CONTEXT_LIMIT),
            ).fetchall()
        # Return in chronological order (oldest first)
        return [{"role": r[0], "content": r[1]} for r in reversed(rows)]
    except Exception:
        return []


def _save_messages(session_id: str, messages: list[dict]) -> None:
    """Persist new messages to chat memory."""
    try:
        with _memory_db() as con:
            con.executemany(
                "INSERT INTO chat_memory (session_id, role, content) VALUES (?, ?, ?)",
                [(session_id, m["role"], m["content"]) for m in messages],
            )
    except Exception:
        pass  # Memory is best-effort; never block the chat response


def _run_tool(name: str, input_: dict, ledger: StockLedger) -> Any:
    """Proxy tool calls: research tools run locally, others go to MCP."""
    if name in _RESEARCH_TOOLS:
        return _run_research_tool(name, input_)
    return _mcp_call(name, input_)


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


def _stream_chat(
    messages: list[dict],
    ledger: StockLedger,
    page_context: str = "",
    session_id: str | None = None,
) -> Generator[str, None, None]:
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

        # Prepend memory context if session_id provided
        if session_id:
            past = _load_memory(session_id)
            current_messages = past + list(messages)
        else:
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

            tool_blocks = [b for b in response.content if b.type == "tool_use"]
            for block in tool_blocks:
                yield _sse_event({"type": "tool_call", "name": block.name})

            # Run all tool calls for this turn in parallel
            tool_results: list[dict] = [{}] * len(tool_blocks)

            def _call(idx_block: tuple[int, Any]) -> tuple[int, Any]:
                idx, block = idx_block
                try:
                    return idx, _run_tool(block.name, block.input, ledger)
                except Exception as exc:
                    return idx, {"error": str(exc)}

            with ThreadPoolExecutor(max_workers=min(len(tool_blocks), 6)) as pool:
                futures = {pool.submit(_call, (i, b)): i for i, b in enumerate(tool_blocks)}
                for future in as_completed(futures):
                    idx, result = future.result()
                    tool_results[idx] = {
                        "type": "tool_result",
                        "tool_use_id": tool_blocks[idx].id,
                        "content": json.dumps(result, default=str),
                    }

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

        # Persist new messages to memory
        if session_id:
            _save_messages(session_id, list(messages))

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
    session_id: str = ""  # client-supplied session ID; empty = no memory


@router.post("/chat/stream")
def chat_stream(body: ChatRequest, ledger: StockLedger = Depends(get_ledger)):
    """SSE endpoint: streams tool-call events then the final text response."""
    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    session_id = body.session_id or None
    return StreamingResponse(
        _stream_chat(messages, ledger, body.page_context, session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
