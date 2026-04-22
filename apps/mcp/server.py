"""
Stock Ledger MCP Server
=======================
Exposes portfolio management tools via the Model Context Protocol (MCP)
so AI agents (Claude Desktop, etc.) can read and write the stock ledger.

Entry point:
    python -m apps.mcp.server
    # or
    python apps/mcp/server.py

Environment variables:
    DB_PATH   Path to the SQLite database (default: /data/ledger.db)
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_MCP_HOST: str = os.getenv("FASTMCP_HOST", "127.0.0.1")
_MCP_PORT: int = int(os.getenv("FASTMCP_PORT", "8000"))

# ---------------------------------------------------------------------------
# MCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Stock Ledger", host=_MCP_HOST, port=_MCP_PORT)

# ---------------------------------------------------------------------------
# Register all tools from sub-modules
# ---------------------------------------------------------------------------

from apps.mcp.tools import register_all_tools  # noqa: E402

register_all_tools(mcp)

# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport in ("sse", "streamable-http"):
        mcp.run(transport=transport)
    else:
        mcp.run(transport="stdio")
