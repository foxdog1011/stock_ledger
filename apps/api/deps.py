"""FastAPI dependencies: shared StockLedger instance & API-key guard."""
from __future__ import annotations

import os
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from fastapi import Header, HTTPException, Query

from ledger import StockLedger
from .config import DB_PATH

_ledger: StockLedger | None = None


def init_ledger() -> None:
    """Called once at application startup."""
    global _ledger
    _ledger = StockLedger(db_path=DB_PATH)


def get_ledger() -> StockLedger:
    """FastAPI dependency: returns the shared ledger (thread-safe; each method opens its own connection)."""
    if _ledger is None:
        raise RuntimeError("Ledger not initialised – startup event did not run")
    return _ledger


# ── API-key guard ────────────────────────────────────────────────────────────


def _validate_jarvis_key(provided: str | None, header_name: str = "X-API-Key") -> str:
    """Core validation: compare *provided* value against ``JARVIS_KEY`` env var.

    Returns the validated key (or empty string when auth is disabled in local dev).
    Raises 401 if the key is required but missing / wrong.
    """
    expected = os.getenv("JARVIS_KEY", "").strip()
    if not expected:
        return ""  # No key configured = local dev mode, skip auth
    if provided != expected:
        raise HTTPException(401, f"Invalid or missing API key ({header_name} header)")
    return provided


def require_api_key(x_api_key: str = Header(None, alias="X-API-Key")) -> str:
    """FastAPI dependency: validates the ``X-API-Key`` header.

    Used by n8n-facing endpoints (video-gen, knowledge, youtube-upload).
    """
    return _validate_jarvis_key(x_api_key, "X-API-Key")


def require_jarvis_key(x_jarvis_key: str | None = Header(default=None)) -> str:
    """FastAPI dependency: validates the ``X-Jarvis-Key`` header.

    Used by the chat/stream endpoint (called from the Next.js frontend).
    """
    return _validate_jarvis_key(x_jarvis_key, "X-Jarvis-Key")


def require_query_key(key: str = Query(...)) -> str:
    """Validate a ``key`` query parameter against ``JARVIS_KEY``.

    Used by endpoints that accept the secret as a query param (e.g. trump-put alert).
    Raises 403 (not 401) to match the original behaviour.
    """
    expected = os.getenv("JARVIS_KEY", "")
    if key != expected:
        raise HTTPException(403, "Invalid key")
    return key
