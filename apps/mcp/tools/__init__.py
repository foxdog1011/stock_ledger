"""MCP tool registration.

Call ``register_all_tools(mcp)`` once after creating the FastMCP instance
to register every tool from every sub-module.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import (
    alerts,
    anomaly,
    catalyst,
    financials,
    knowledge,
    market,
    portfolio,
    rating,
    research,
    risk,
    trading,
    universe,
)

_MODULES = [
    portfolio,
    trading,
    risk,
    anomaly,
    research,
    market,
    alerts,
    financials,
    rating,
    catalyst,
    universe,
    knowledge,
]


def register_all_tools(mcp: FastMCP) -> None:
    """Register all MCP tools from every sub-module."""
    for mod in _MODULES:
        mod.register(mcp)
