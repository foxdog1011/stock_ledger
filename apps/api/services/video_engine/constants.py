"""Video engine constants — resolution, colors, ticker names, sector definitions."""
from __future__ import annotations

# ── Video resolution ──────────────────────────────────────────────────────────

WIDTH, HEIGHT = 1920, 1080
FPS = 24  # frames per second

SLIDE_SECONDS: dict[str, int] = {
    "title": 5,
    "chart": 10,
    "summary": 8,
}

# Shorts (vertical)
SHORTS_W, SHORTS_H = 1080, 1920

# Thumbnail
THUMB_W, THUMB_H = 1280, 720

# ── Colours matching Stock Ledger dark theme ──────────────────────────────────

BG        = "#0f1423"
ACCENT    = "#00d4ff"
GREEN     = "#00e676"
RED       = "#ff5252"
BLUE      = "#3f88ff"
ORANGE    = "#ff9800"
TEXT      = "#ffffff"
MUTED     = "#b0b4c8"
CARD_BG   = "#1a2040"
GRID      = "#2a3050"

# ── Known TW stock ticker -> Chinese name (fallback) ─────────────────────────

TICKER_NAME: dict[str, str] = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達",
    "2308": "台達電", "2881": "富邦金", "2882": "國泰金", "2886": "兆豐金",
    "2891": "中信金", "2884": "玉山金", "3008": "大立光", "2412": "中華電",
    "2303": "聯電",  "2357": "華碩",  "2395": "研華",  "6505": "台塑化",
    "1301": "台塑",  "1303": "南亞",  "1326": "台化",  "2002": "中鋼",
    "2207": "和泰車", "2474": "可成",  "3034": "聯詠",  "3711": "日月光投控",
}

# ── Built-in sector definitions ──────────────────────────────────────────────

SECTOR_SYMBOLS: dict[str, list[str]] = {
    "散熱":   ["2230", "3017", "6245", "8016", "3520", "2243"],
    "AI伺服器": ["2382", "3231", "6669", "5274", "6414"],
    "台積電供應鏈": ["2330", "3711", "2454", "2308", "3034"],
    "金融": ["2881", "2882", "2886", "2891", "2884"],
    "鋼鐵": ["2002", "2006", "2007", "2008"],
    "電動車": ["2308", "1515", "2207", "6116"],
    "記憶體": ["4256", "3443", "2408"],
}

# ── Shorts slot names ────────────────────────────────────────────────────────

SHORTS_SLOTS = ("morning", "afternoon", "sat_am", "sat_pm", "sun_am", "sun_pm")
