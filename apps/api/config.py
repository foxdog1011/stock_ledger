"""Centralised application configuration.

All environment variables consumed by the API layer are read here once,
at import time.  Import the constants directly instead of calling
``os.getenv(...)`` in individual modules.

Environment variables
---------------------
DB_PATH
    Path to the SQLite database file.
    Default: ``data/ledger.db``

QUOTE_PROVIDER
    Price provider to use: ``auto`` | ``twse`` | ``finmind`` | ``yahoo``.
    Default: ``auto``

AUTO_REFRESH_QUOTES_ON_TRADE
    Set to ``"0"`` to disable background quote refresh after each trade.
    Default: enabled (``"1"``).

Note
----
Provider-level credentials (e.g. ``FINMIND_TOKEN``) are intentionally kept
in their respective provider modules and are *not* centralised here.
"""
from __future__ import annotations

import os
from pathlib import Path

DB_PATH: Path = Path(os.getenv("DB_PATH", "data/ledger.db"))

QUOTE_PROVIDER: str = os.getenv("QUOTE_PROVIDER", "auto")

AUTO_REFRESH_QUOTES_ON_TRADE: bool = os.getenv("AUTO_REFRESH_QUOTES_ON_TRADE", "1") != "0"

# Optional access key for J.A.R.V.I.S. chat. If set, requests must include
# X-Jarvis-Key header matching this value. Leave empty to allow open access.
JARVIS_KEY: str = os.getenv("JARVIS_KEY", "")
