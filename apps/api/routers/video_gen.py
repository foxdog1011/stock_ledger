"""Video generation endpoint — creates YouTube-style stock analysis MP4 slides.

POST /api/video/generate
  body: { symbol, script, days }
  returns: MP4 file

Slides generated:
  1. Title card
  2. 外資買賣超 bar chart
  3. 投信/自營 grouped bar chart
  4. 累積淨買超 area chart
  5. 本週總結 summary card

Optional TTS via ElevenLabs (set ELEVENLABS_API_KEY env var).
"""
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import tempfile
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from PIL import Image

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from starlette.background import BackgroundTask
from PIL import ImageDraw, ImageFont

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Video constants ────────────────────────────────────────────────────────────

WIDTH, HEIGHT = 1920, 1080
FPS = 24  # frames per second

SLIDE_SECONDS: dict[str, int] = {
    "title": 5,
    "chart": 10,
    "summary": 8,
}

# Colours matching Stock Ledger dark theme
_BG        = "#0f1423"
_ACCENT    = "#00d4ff"
_GREEN     = "#00e676"
_RED       = "#ff5252"
_BLUE      = "#3f88ff"
_ORANGE    = "#ff9800"
_TEXT      = "#ffffff"
_MUTED     = "#b0b4c8"
_CARD_BG   = "#1a2040"
_GRID      = "#2a3050"


# ── Font setup ─────────────────────────────────────────────────────────────────

# Known TW stock ticker → Chinese name (fallback when research DB has no entry)
_TICKER_NAME: dict[str, str] = {
    "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達",
    "2308": "台達電", "2881": "富邦金", "2882": "國泰金", "2886": "兆豐金",
    "2891": "中信金", "2884": "玉山金", "3008": "大立光", "2412": "中華電",
    "2303": "聯電",  "2357": "華碩",  "2395": "研華",  "6505": "台塑化",
    "1301": "台塑",  "1303": "南亞",  "1326": "台化",  "2002": "中鋼",
    "2207": "和泰車","2474": "可成",  "3034": "聯詠",  "3711": "日月光投控",
}


# Known locations of Noto Sans CJK (installed via fonts-noto-cjk)
_NOTO_SANS_CJK_PATHS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
_CJK_FONT_PATH: str = ""
_CJK_FONT_PROP: "fm.FontProperties | None" = None


def _setup_matplotlib_fonts() -> None:
    global _CJK_FONT_PATH, _CJK_FONT_PROP

    # Find the first available CJK font file
    import glob as _glob
    candidates = list(_NOTO_SANS_CJK_PATHS)
    # Windows CJK fonts
    candidates += [
        "C:/Windows/Fonts/msjh.ttc",    # Microsoft JhengHei (繁體)
        "C:/Windows/Fonts/msyh.ttc",    # Microsoft YaHei (簡體)
        "C:/Windows/Fonts/mingliu.ttc", # MingLiU
    ]
    candidates += _glob.glob("/usr/share/fonts/**/*SansCJK*.ttc", recursive=True)
    candidates += _glob.glob("/usr/share/fonts/**/*SansCJK*.otf", recursive=True)

    for path in candidates:
        if Path(path).exists():
            try:
                fm.fontManager.addfont(path)
                prop = fm.FontProperties(fname=path)
                _CJK_FONT_PATH = path
                _CJK_FONT_PROP = prop
                matplotlib.rcParams["font.sans-serif"] = [prop.get_name(), "DejaVu Sans"]
                matplotlib.rcParams["axes.unicode_minus"] = False
                logger.info("CJK font ready: %s → %s", path, prop.get_name())
                return
            except Exception as e:
                logger.debug("addfont failed for %s: %s", path, e)

    matplotlib.rcParams["axes.unicode_minus"] = False
    logger.warning("No CJK font found — Chinese text will show as boxes")


_setup_matplotlib_fonts()


# ── Request model ──────────────────────────────────────────────────────────────

class VideoRequest(BaseModel):
    symbol: str
    script: str = ""
    days: int = 7
    format: str = "landscape"   # "landscape" (1920×1080) | "shorts" (1080×1920)
    # Sector mode: if sector_name + symbols provided, generate a sector report
    sector_name: str = ""        # e.g. "散熱族群"
    symbols: list[str] = []      # e.g. ["2230","3017","6245","8016"]


# ── Built-in sector definitions ────────────────────────────────────────────────

SECTOR_SYMBOLS: dict[str, list[str]] = {
    "散熱":   ["2230", "3017", "6245", "8016", "3520", "2243"],
    "AI伺服器": ["2382", "3231", "6669", "5274", "6414"],
    "台積電供應鏈": ["2330", "3711", "2454", "2308", "3034"],
    "金融": ["2881", "2882", "2886", "2891", "2884"],
    "鋼鐵": ["2002", "2006", "2007", "2008"],
    "電動車": ["2308", "1515", "2207", "6116"],
    "記憶體": ["4256", "3443", "2408"],
}


# ── Slide generators ───────────────────────────────────────────────────────────

def _fig_to_array(fig: plt.Figure) -> np.ndarray:
    """Render matplotlib figure → RGB numpy array at target resolution."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    return np.array(img)


def _fp(size: int) -> "fm.FontProperties":
    """Return FontProperties for CJK font at given size (bypasses family lookup)."""
    if _CJK_FONT_PROP is not None:
        return fm.FontProperties(fname=_CJK_FONT_PATH, size=size)
    return fm.FontProperties(size=size)


def _make_title_slide(symbol: str, company_name: str, date_range: str) -> np.ndarray:
    fig = plt.figure(figsize=(19.2, 10.8), facecolor=_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_BG)
    ax.axis("off")

    ax.axhline(0.86, xmin=0.08, xmax=0.92, color=_ACCENT, lw=3)
    ax.axhline(0.14, xmin=0.08, xmax=0.92, color=_ACCENT, lw=2, alpha=0.4)

    ax.text(0.5, 0.93, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=_ACCENT, fontproperties=_fp(26), fontweight="bold")
    ax.text(0.5, 0.73, f"{company_name}（{symbol}）", transform=ax.transAxes,
            ha="center", va="center", color=_TEXT, fontproperties=_fp(68), fontweight="bold")
    ax.text(0.5, 0.57, "三大法人週報", transform=ax.transAxes,
            ha="center", va="center", color=_ACCENT, fontproperties=_fp(54))
    ax.text(0.5, 0.43, date_range, transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(30))
    ax.text(0.5, 0.25, "本週機構買賣超 完整分析", transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(26))
    ax.text(0.5, 0.07, "訂閱 JARVIS 選股｜每天更新",
            transform=ax.transAxes, ha="center", va="center",
            color=_ACCENT, alpha=0.8, fontproperties=_fp(22))

    plt.tight_layout(pad=0)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def _make_foreign_chart(daily: list[dict]) -> np.ndarray:
    dates = [d["date"][-5:] for d in daily]
    nets  = [round(d["foreign"]["net"] / 1000) for d in daily]
    colors = [_GREEN if n >= 0 else _RED for n in nets]

    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=_BG)
    ax.set_facecolor(_BG)

    bars = ax.bar(dates, nets, color=colors, width=0.55, edgecolor="none", zorder=3)

    for bar, val in zip(bars, nets):
        offset = max(abs(val) * 0.06, 30)
        va = "bottom" if val >= 0 else "top"
        y  = val + offset if val >= 0 else val - offset
        ax.text(bar.get_x() + bar.get_width() / 2, y,
                f"{val:+,}", ha="center", va=va,
                fontsize=20, color=_TEXT, fontweight="bold")

    ax.axhline(0, color=_MUTED, lw=1.5, alpha=0.5, zorder=2)
    ax.set_title("外資近週買賣超（張）", fontproperties=_fp(40), color=_TEXT, pad=18)
    ax.set_ylabel("張", fontproperties=_fp(20), color=_MUTED)
    ax.tick_params(colors=_TEXT, labelsize=20)
    for sp in ax.spines.values():
        sp.set_edgecolor(_GRID)
    ax.grid(axis="y", color=_GRID, lw=1, zorder=1)

    plt.tight_layout(pad=1.5)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def _make_trust_dealer_chart(daily: list[dict]) -> np.ndarray:
    dates   = [d["date"][-5:] for d in daily]
    trusts  = [round(d["investment_trust"]["net"] / 1000) for d in daily]
    dealers = [round(d["dealer"]["net"] / 1000) for d in daily]

    x = np.arange(len(dates))
    w = 0.35

    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=_BG)
    ax.set_facecolor(_BG)

    ax.bar(x - w / 2, trusts,  w, label="投信",
           color=[_GREEN if v >= 0 else _RED for v in trusts],
           alpha=0.9, edgecolor="none", zorder=3)
    ax.bar(x + w / 2, dealers, w, label="自營商",
           color=[_BLUE if v >= 0 else _ORANGE for v in dealers],
           alpha=0.9, edgecolor="none", zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(dates, fontsize=20)
    ax.axhline(0, color=_MUTED, lw=1.5, alpha=0.5, zorder=2)
    ax.set_title("投信 / 自營商 近週買賣超（張）", fontproperties=_fp(40), color=_TEXT, pad=18)
    ax.set_ylabel("張", fontproperties=_fp(20), color=_MUTED)
    ax.tick_params(colors=_TEXT, labelsize=20)
    ax.legend(prop=_fp(22), facecolor=_CARD_BG, edgecolor=_ACCENT, labelcolor=_TEXT)
    for sp in ax.spines.values():
        sp.set_edgecolor(_GRID)
    ax.grid(axis="y", color=_GRID, lw=1, zorder=1)

    plt.tight_layout(pad=1.5)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def _make_cumulative_chart(daily: list[dict]) -> np.ndarray:
    dates = [d["date"][-5:] for d in daily]
    running, total = [], 0
    for d in daily:
        total += round(d["total_net"] / 1000)
        running.append(total)

    final_color = _GREEN if (running[-1] >= 0 if running else True) else _RED

    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=_BG)
    ax.set_facecolor(_BG)

    x = range(len(dates))
    ax.fill_between(x, running, alpha=0.25, color=final_color, zorder=2)
    ax.plot(x, running, color=final_color, lw=4,
            marker="o", markersize=14, zorder=3)

    span = max(running) - min(running) if len(running) > 1 else 1
    for i, (v, _d) in enumerate(zip(running, dates)):
        ax.text(i, v + span * 0.08, f"{v:+,}",
                ha="center", fontsize=19, color=_TEXT, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(dates, fontsize=20)
    ax.axhline(0, color=_MUTED, lw=1.5, alpha=0.5, zorder=1)
    ax.set_title("三大法人 累積淨買超（張）", fontproperties=_fp(40), color=_TEXT, pad=18)
    ax.set_ylabel("張", fontproperties=_fp(20), color=_MUTED)
    ax.tick_params(colors=_TEXT, labelsize=20)
    for sp in ax.spines.values():
        sp.set_edgecolor(_GRID)
    ax.grid(color=_GRID, lw=1, zorder=0)

    plt.tight_layout(pad=1.5)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def _make_summary_slide(summary: dict, date_range: str) -> np.ndarray:
    foreign_k = round(summary.get("foreign_net_total", 0) / 1000)
    trust_k   = round(summary.get("investment_trust_net_total", 0) / 1000)
    dealer_k  = round(summary.get("dealer_net_total", 0) / 1000)

    fig = plt.figure(figsize=(19.2, 10.8), facecolor=_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_BG)
    ax.axis("off")

    ax.axhline(0.86, xmin=0.06, xmax=0.94, color=_ACCENT, lw=2.5)
    ax.text(0.5, 0.93, f"本週總結  {date_range}", transform=ax.transAxes,
            ha="center", va="center", color=_ACCENT, fontproperties=_fp(36))

    metrics = [
        ("外資", foreign_k, _ACCENT),
        ("投信", trust_k,   _GREEN),
        ("自營商", dealer_k, _BLUE),
    ]
    xs = [0.20, 0.50, 0.80]
    for (label, val, clr), cx in zip(metrics, xs):
        val_color = _GREEN if val >= 0 else _RED
        trend_txt = "▲ 買超" if val >= 0 else "▼ 賣超"
        sign = "+" if val >= 0 else ""

        rect = plt.Rectangle(
            (cx - 0.135, 0.33), 0.27, 0.45,
            transform=ax.transAxes, clip_on=False,
            facecolor=_CARD_BG, edgecolor=clr, linewidth=3
        )
        ax.add_patch(rect)

        ax.text(cx, 0.70, label, transform=ax.transAxes,
                ha="center", va="center", color=clr, fontproperties=_fp(34))
        ax.text(cx, 0.54, f"{sign}{val:,} 張", transform=ax.transAxes,
                ha="center", va="center", color=val_color, fontproperties=_fp(30))
        ax.text(cx, 0.40, trend_txt, transform=ax.transAxes,
                ha="center", va="center", color=val_color, fontproperties=_fp(24))

    ax.axhline(0.28, xmin=0.06, xmax=0.94, color=_GRID, lw=1.5)
    ax.text(0.5, 0.20, "以上資訊僅供參考，不構成任何投資建議，請自行評估風險。",
            transform=ax.transAxes, ha="center", va="center",
            color=_MUTED, fontproperties=_fp(20))
    ax.text(0.5, 0.10, "按讚 + 訂閱 JARVIS 選股，每週一掌握三大法人動向！",
            transform=ax.transAxes, ha="center", va="center",
            color=_ACCENT, fontproperties=_fp(22))

    plt.tight_layout(pad=0)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


# ── YouTube Thumbnail ─────────────────────────────────────────────────────────

_THUMB_W, _THUMB_H = 1280, 720


def _pil_font(size: int) -> ImageFont.FreeTypeFont:
    """Load Noto Sans CJK at given size for PIL rendering."""
    if _CJK_FONT_PATH:
        try:
            return ImageFont.truetype(_CJK_FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _hex(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _draw_rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    radius: int,
    fill: tuple,
) -> None:
    x0, y0, x1, y1 = xy
    draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    draw.ellipse([x0, y0, x0 + 2 * radius, y0 + 2 * radius], fill=fill)
    draw.ellipse([x1 - 2 * radius, y0, x1, y0 + 2 * radius], fill=fill)
    draw.ellipse([x0, y1 - 2 * radius, x0 + 2 * radius, y1], fill=fill)
    draw.ellipse([x1 - 2 * radius, y1 - 2 * radius, x1, y1], fill=fill)


def make_thumbnail(
    symbol: str,
    company_name: str,
    foreign_net_k: int,          # foreign net in 千張 (positive = buy, negative = sell)
    date_range: str,
) -> bytes:
    """Generate a YouTube-optimised thumbnail (1280×720) as PNG bytes.

    Layout:
      Left half  — channel badge + company name + ticker
      Right half — BIG number (外資 net) + 買超/賣超 label
    """
    img = Image.new("RGB", (_THUMB_W, _THUMB_H), _hex(_BG))
    draw = ImageDraw.Draw(img)

    # ── Gradient-ish left band ──────────────────────────────────────────────
    for x in range(0, _THUMB_W // 2):
        alpha = int(30 * (1 - x / (_THUMB_W // 2)))
        for y in range(_THUMB_H):
            r, g, b = img.getpixel((x, y))
            img.putpixel((x, y), (r + alpha, g + alpha, b + alpha))

    # ── Vertical accent bar ─────────────────────────────────────────────────
    draw.rectangle([0, 0, 12, _THUMB_H], fill=_hex(_ACCENT))

    # ── Channel name ────────────────────────────────────────────────────────
    font_channel = _pil_font(38)
    draw.text((52, 52), "JARVIS 選股", font=font_channel, fill=_hex(_ACCENT))

    # ── Company name (large) ────────────────────────────────────────────────
    font_company = _pil_font(110)
    draw.text((52, 120), company_name, font=font_company, fill=_hex(_TEXT))

    # ── Ticker badge ────────────────────────────────────────────────────────
    font_ticker = _pil_font(52)
    _pad_x, _pad_y = 22, 10
    tbbox = draw.textbbox((0, 0), symbol, font=font_ticker)
    tw, th = tbbox[2] - tbbox[0], tbbox[3] - tbbox[1]
    bx, by = 52, 270
    rect_w, rect_h = tw + _pad_x * 2, th + _pad_y * 2
    _draw_rounded_rect(draw, (bx, by, bx + rect_w, by + rect_h), 14, _hex(_ACCENT))
    # adjust for bbox offset so text is visually centred in the pill
    draw.text((bx + _pad_x - tbbox[0], by + _pad_y - tbbox[1]),
              symbol, font=font_ticker, fill=_hex(_BG))

    # ── Date range ──────────────────────────────────────────────────────────
    font_date = _pil_font(34)
    draw.text((52, _THUMB_H - 80), date_range, font=font_date, fill=_hex(_MUTED))

    # ── Divider ─────────────────────────────────────────────────────────────
    draw.rectangle([_THUMB_W // 2 - 2, 40, _THUMB_W // 2 + 2, _THUMB_H - 40],
                   fill=_hex(_GRID))

    # ── Right side: main metric ─────────────────────────────────────────────
    is_buy    = foreign_net_k >= 0
    val_color = _hex(_GREEN) if is_buy else _hex(_RED)
    label     = "外資買超" if is_buy else "外資賣超"
    sign      = "+" if is_buy else ""
    abs_k     = abs(foreign_net_k)

    # Format number: show in 萬張 if >= 10000
    if abs_k >= 10000:
        num_str  = f"{sign}{abs_k / 10000:.1f}萬"
        unit_str = "張"
    else:
        num_str  = f"{sign}{abs_k:,}"
        unit_str = "張"

    # Right column: from rx_start to _THUMB_W
    rx_start  = _THUMB_W // 2 + 40   # left edge of right column (700)
    right_w   = _THUMB_W - rx_start  # available width (580)
    ry_center = _THUMB_H // 2        # vertical center (360)

    def _rcenter(text_w: int) -> int:
        """X coordinate to center text of given width in the right column."""
        return rx_start + max(0, (right_w - text_w) // 2)

    # Label pill
    font_label = _pil_font(52)
    lbbox = draw.textbbox((0, 0), label, font=font_label)
    lw, lh = lbbox[2] - lbbox[0], lbbox[3] - lbbox[1]
    l_pad_x, l_pad_y = 28, 12
    pill_w = lw + l_pad_x * 2
    lx = _rcenter(pill_w)          # x of pill left edge
    pill_top = ry_center - 215
    _draw_rounded_rect(draw, (lx, pill_top, lx + pill_w, pill_top + lh + l_pad_y * 2),
                       22, val_color)
    # offset by bbox[0]/bbox[1] so text is optically centred in pill
    draw.text((lx + l_pad_x - lbbox[0], pill_top + l_pad_y - lbbox[1]),
              label, font=font_label, fill=_hex(_BG))

    # Big number — dynamically fit within right column width
    for num_pt in (180, 150, 120, 96):
        font_number = _pil_font(num_pt)
        nbbox = draw.textbbox((0, 0), num_str, font=font_number)
        nw = nbbox[2] - nbbox[0]
        if nw <= right_w - 20:
            break
    nx = _rcenter(nw)
    draw.text((nx, ry_center - 130), num_str, font=font_number, fill=val_color)

    # Unit
    font_unit = _pil_font(56)
    ubbox = draw.textbbox((0, 0), unit_str, font=font_unit)
    uw = ubbox[2] - ubbox[0]
    draw.text((_rcenter(uw), ry_center + 110), unit_str, font=font_unit, fill=_hex(_MUTED))

    # Suggested title at bottom
    font_title = _pil_font(32)
    title_hint = f"{symbol} {company_name} 本週三大法人籌碼分析"
    tbbox = draw.textbbox((0, 0), title_hint, font=font_title)
    tw = tbbox[2] - tbbox[0]
    draw.text((_rcenter(tw), _THUMB_H - 72), title_hint, font=font_title, fill=_hex(_MUTED))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── OpenAI script generation ──────────────────────────────────────────────────


def _openai_script(prompt: str, max_tokens: int = 500) -> str:
    """Generate a narration script via OpenAI gpt-4o-mini."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return prompt  # fallback: use prompt as script

    import urllib.request as _ur
    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "你是專業台股分析 YouTuber，語氣活潑但專業。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()
    req = _ur.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with _ur.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("OpenAI script generation failed")
        return prompt


# ── Script cleaning ────────────────────────────────────────────────────────────

import re as _re

def _clean_script_for_tts(script: str) -> str:
    """Strip non-spoken content from AI-generated scripts before TTS.

    Removes entirely:
    - Markdown header lines (## 任何標題 — skip the whole line)
    - Numbered section lines (1. 開場Hook / 第一段：)
    - Horizontal rules --- / ===
    - Emoji-only lines
    - Blank lines

    Strips inline:
    - Stage directions [開場畫面] 【B-roll】 （停頓）
    - Timestamp cues [0:15]
    - Speaker labels 主持人：/ 旁白：
    - Markdown bold/italic **text**
    """
    lines = script.splitlines()
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Skip entire markdown header lines (## 小標 / # 大標)
        if _re.match(r'^#{1,6}\s+', s):
            continue
        # Skip numbered section labels: "1. 開場", "第一段：", "【段落一】"
        if _re.match(r'^(第[一二三四五六七八九十百]+[段節部點]|[一二三四五六七八九十]\s*[、.．]|[1-9]\d*\s*[\.、])\s*\S{1,20}[：:]?\s*$', s):
            continue
        # Skip standalone section-label lines like "開場 Hook（前 15 秒）"
        # heuristic: ≤25 chars, no sentence-ending punctuation, contains 「」or ()
        if len(s) <= 30 and _re.search(r'[（(【\[]', s) and not _re.search(r'[。！？，、]', s):
            continue
        # Remove horizontal rules
        if _re.match(r'^[-=*]{3,}$', s):
            continue
        # Strip bracketed/parenthetical stage directions
        s = _re.sub(r'[【\[（(][^】\]）)]{1,60}[】\]）)]', '', s)
        # Strip timestamp cues
        s = _re.sub(r'[\[(]\d+:\d+[\])]', '', s)
        # Strip speaker labels
        s = _re.sub(r'^(主持人|旁白|Host|Narrator|VO|V\.O\.)\s*[：:]\s*', '', s)
        # Strip markdown formatting markers
        s = _re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', s)
        s = _re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', s)
        s = s.strip()
        if not s:
            continue
        # Skip emoji-only lines
        text_only = _re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff]', '', s).strip()
        if not text_only:
            continue
        cleaned.append(s)

    return '\n'.join(cleaned)


# ── TTS ────────────────────────────────────────────────────────────────────────
# Priority: ElevenLabs (if key set) → Edge-TTS (free, Chinese support) → silent

# Edge-TTS Chinese voices
_EDGE_VOICE_ZH = os.getenv("EDGE_TTS_VOICE", "zh-TW-HsiaoChenNeural")  # TW Mandarin female, more natural
_EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+15%")   # +15% = slightly faster, natural pace


async def _edge_tts_bytes(text: str, voice: str, rate: str = "+0%") -> bytes:
    import edge_tts
    import io
    buf = io.BytesIO()
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def _tts_edge(script: str, rate: str | None = None) -> bytes | None:
    """Generate TTS via Edge-TTS (free Microsoft voices, zh-TW supported)."""
    if not script:
        return None
    import asyncio
    effective_rate = rate if rate is not None else _EDGE_TTS_RATE
    try:
        audio = asyncio.run(_edge_tts_bytes(script[:3000], _EDGE_VOICE_ZH, rate=effective_rate))
        logger.info("Edge-TTS voiceover generated (%d bytes) at rate %s", len(audio), effective_rate)
        return audio
    except Exception:
        logger.exception("Edge-TTS failed")
        return None


def _tts_elevenlabs(script: str) -> bytes | None:
    """Call ElevenLabs API → return MP3 bytes (premium, most natural)."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key or not script:
        return None

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
    payload  = json.dumps({
        "text": script[:2500],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode()

    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception:
        logger.exception("ElevenLabs TTS failed")
        return None


def _tts_to_mp3(script: str) -> bytes | None:
    """TTS with automatic provider selection.

    Cleans non-spoken content before sending to TTS.
    Priority: ElevenLabs (if ELEVENLABS_API_KEY set) → Edge-TTS (free default).
    Returns None if both fail, resulting in a silent video.
    """
    spoken = _clean_script_for_tts(script)
    if not spoken:
        return None
    logger.info("TTS input after cleaning: %d chars (was %d)", len(spoken), len(script))
    if os.getenv("ELEVENLABS_API_KEY", "").strip():
        result = _tts_elevenlabs(spoken)
        if result:
            return result
        logger.warning("ElevenLabs failed, falling back to Edge-TTS")
    return _tts_edge(spoken)


# ── Video assembly ─────────────────────────────────────────────────────────────

def _get_audio_duration(audio_path: str) -> float:
    """Return audio duration in seconds using ffprobe."""
    import imageio_ffmpeg
    ff_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    # Only replace the filename, not directory names containing "ffmpeg"
    ffprobe = ff_exe.parent / ff_exe.name.replace("ffmpeg", "ffprobe")
    if not ffprobe.exists():
        # Fallback: parse duration from ffmpeg -i stderr
        r = subprocess.run(
            [str(ff_exe), "-i", audio_path],
            capture_output=True, timeout=30,
        )
        stderr = r.stderr.decode("utf-8", errors="replace") if r.stderr else ""
        for line in stderr.splitlines():
            if "Duration" in line:
                t = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = t.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
        return 0.0
    r = subprocess.run(
        [str(ffprobe), "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", audio_path],
        capture_output=True, timeout=30,
    )
    if r.returncode != 0:
        logger.warning("ffprobe failed (exit %d) for %s", r.returncode, audio_path)
        return 0.0
    return float(r.stdout.decode("utf-8", errors="replace").strip() or 0)


def _build_mp4(
    frames: list[tuple[np.ndarray, int]],
    audio_bytes: bytes | None,
    output: str,
) -> None:
    """Write frames to MP4, syncing slide durations to audio length when available.

    If audio is provided:
      - Distribute slides evenly across audio duration
      - Audio is the master timeline (no -shortest truncation)
    If no audio:
      - Use fixed SLIDE_SECONDS durations
    """
    import imageio.v2 as imageio
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    # Determine per-slide seconds
    slide_seconds: list[int]
    if audio_bytes:
        audio_path = output.replace(".mp4", "_audio.mp3")
        Path(audio_path).write_bytes(audio_bytes)
        total_audio = _get_audio_duration(audio_path)
        if total_audio > 0:
            # Distribute audio evenly; title gets ~15%, others equal share of rest
            n = len(frames)
            per = max(3, total_audio / n)
            slide_seconds = [max(3, round(per))] * n
            # Adjust last slide to absorb rounding error
            slide_seconds[-1] = max(3, round(total_audio - sum(slide_seconds[:-1])))
        else:
            slide_seconds = [s for _, s in frames]
            audio_path_obj = Path(audio_path)
            audio_path_obj.unlink(missing_ok=True)
            audio_bytes = None
    else:
        slide_seconds = [s for _, s in frames]
        audio_path = ""

    # Build silent video
    silent = output.replace(".mp4", "_silent.mp4")
    writer = imageio.get_writer(
        silent, fps=FPS, codec="libx264",
        output_params=["-pix_fmt", "yuv420p", "-crf", "20"],
        macro_block_size=None,
    )
    for (frame_arr, _), secs in zip(frames, slide_seconds):
        for _ in range(max(1, secs * FPS)):
            writer.append_data(frame_arr)
    writer.close()

    if not audio_bytes:
        import shutil
        shutil.move(silent, output)
        return

    # Merge audio — pad audio with silence if shorter than video, truncate if longer
    try:
        result = subprocess.run(
            [ffmpeg, "-y",
             "-i", silent,
             "-i", audio_path,
             "-c:v", "copy",
             "-c:a", "aac",
             "-map", "0:v:0",
             "-map", "1:a:0",
             output],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            err_msg = result.stderr.decode("utf-8", errors="replace")[-500:] if result.stderr else ""
            logger.warning("ffmpeg merge failed (%d): %s", result.returncode, err_msg)
            import shutil
            shutil.copy(silent, output)
    except Exception:
        logger.exception("Audio merge error — using silent video")
        import shutil
        shutil.copy(silent, output)
    finally:
        Path(silent).unlink(missing_ok=True)
        Path(audio_path).unlink(missing_ok=True)


# ── Sector chip aggregation ────────────────────────────────────────────────────

def _get_sector_chip(symbols: list[str], sector_name: str, days: int) -> dict:
    """Fetch chip data for each symbol and aggregate into a sector summary."""
    all_data: list[dict] = []
    failed: list[str] = []

    for sym in symbols:
        try:
            data = _get_chip_data(sym, days)
            all_data.append({"symbol": sym, "name": _get_company_name(sym), **data})
        except Exception:
            logger.warning("Sector chip fetch failed for %s", sym)
            failed.append(sym)

    if not all_data:
        raise HTTPException(502, f"No chip data available for any symbol in {sector_name}")

    # Build unified daily grid: sum across all symbols per date
    date_map: dict[str, dict] = {}
    for item in all_data:
        for d in item.get("daily", []):
            dt = d["date"]
            if dt not in date_map:
                date_map[dt] = {
                    "date": dt,
                    "foreign":          {"net": 0},
                    "investment_trust": {"net": 0},
                    "dealer":           {"net": 0},
                    "total_net": 0,
                }
            date_map[dt]["foreign"]["net"]          += d.get("foreign", {}).get("net", 0)
            date_map[dt]["investment_trust"]["net"] += d.get("investment_trust", {}).get("net", 0)
            date_map[dt]["dealer"]["net"]           += d.get("dealer", {}).get("net", 0)
            date_map[dt]["total_net"]               += d.get("total_net", 0)

    daily = sorted(date_map.values(), key=lambda x: x["date"])

    summary = {
        "foreign_net_total":          sum(d["foreign"]["net"]          for d in daily),
        "investment_trust_net_total": sum(d["investment_trust"]["net"] for d in daily),
        "dealer_net_total":           sum(d["dealer"]["net"]           for d in daily),
        "total_net":                  sum(d["total_net"]               for d in daily),
    }

    return {
        "sector_name": sector_name,
        "symbols": [{"symbol": s["symbol"], "name": s["name"]} for s in all_data],
        "failed": failed,
        "daily": daily,
        "summary": summary,
    }


def _make_sector_title_slide(sector_name: str, symbols: list[dict], date_range: str) -> np.ndarray:
    fig = plt.figure(figsize=(19.2, 10.8), facecolor=_BG)
    ax  = fig.add_subplot(111)
    ax.set_facecolor(_BG)
    ax.axis("off")

    ax.axhline(0.86, xmin=0.08, xmax=0.92, color=_ACCENT, lw=3)
    ax.axhline(0.14, xmin=0.08, xmax=0.92, color=_ACCENT, lw=2, alpha=0.4)

    ax.text(0.5, 0.93, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=_ACCENT, fontproperties=_fp(26), fontweight="bold")
    ax.text(0.5, 0.74, f"{sector_name}　族群週報", transform=ax.transAxes,
            ha="center", va="center", color=_TEXT, fontproperties=_fp(62), fontweight="bold")
    ax.text(0.5, 0.57, date_range, transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(30))

    # Ticker badges row
    names = [f"{s['symbol']} {s['name']}" for s in symbols[:6]]
    badge_str = "　".join(names)
    ax.text(0.5, 0.42, badge_str, transform=ax.transAxes,
            ha="center", va="center", color=_ACCENT, fontproperties=_fp(22), alpha=0.9)

    ax.text(0.5, 0.25, "三大法人合計買賣超分析", transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(26))
    ax.text(0.5, 0.07, "訂閱 JARVIS 選股｜每天更新",
            transform=ax.transAxes, ha="center", va="center",
            color=_ACCENT, alpha=0.8, fontproperties=_fp(22))

    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def _make_sector_breakdown_chart(symbols_data: list[dict], days: int) -> np.ndarray:
    """Horizontal bar chart: each symbol's total foreign net for the period."""
    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=_BG)
    ax.set_facecolor(_BG)

    names  = [f"{s['symbol']}\n{s['name']}" for s in symbols_data]
    totals = []
    for s in symbols_data:
        foreign_total = sum(
            d.get("foreign", {}).get("net", 0) for d in s.get("daily", [])
        )
        totals.append(round(foreign_total / 1000))

    colors = [_GREEN if v >= 0 else _RED for v in totals]
    bars = ax.barh(names, totals, color=colors, height=0.6)
    ax.axvline(0, color=_GRID, lw=1.5)

    for bar, val in zip(bars, totals):
        sign = "+" if val >= 0 else ""
        ax.text(bar.get_width() + (max(abs(t) for t in totals) * 0.02),
                bar.get_y() + bar.get_height() / 2,
                f"{sign}{val:,}", va="center", color=_TEXT, fontproperties=_fp(18))

    ax.set_title("各股外資買賣超（張）", fontproperties=_fp(28), color=_TEXT, pad=16)
    ax.set_xlabel("張", fontproperties=_fp(20), color=_MUTED)
    ax.tick_params(colors=_MUTED, labelsize=16)
    for tick in ax.get_yticklabels():
        tick.set_fontproperties(_fp(18))
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)
    ax.set_facecolor(_CARD_BG)
    fig.patch.set_facecolor(_BG)

    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


# ── Local API helpers ──────────────────────────────────────────────────────────

def _get_chip_data(symbol: str, days: int) -> dict:
    end   = date.today().isoformat()
    start = (date.today() - timedelta(days=days + 10)).isoformat()
    url   = f"http://localhost:8000/api/chip/{symbol}/range?start={start}&end={end}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=20,
        ) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        raise HTTPException(502, f"Chip data unavailable: {exc}") from exc

    # Trim to last N trading days so numbers match the requested scope
    daily = data.get("daily", [])
    if daily and len(daily) > days:
        data["daily"] = daily[-days:]
    return data


def _get_company_name(symbol: str) -> str:
    url = f"http://localhost:8000/api/research/{symbol}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=10,
        ) as resp:
            name = json.loads(resp.read()).get("name", "")
            if name and name != symbol:
                return name
    except Exception:
        pass
    return _TICKER_NAME.get(symbol, symbol)


# ── Shorts slide generator (1080×1920 vertical) ────────────────────────────────

_SHORTS_W, _SHORTS_H = 1080, 1920

def _make_shorts_slide(
    symbol: str,
    company_name: str,
    date_range: str,
    summary: dict,
    daily: list[dict],
) -> np.ndarray:
    """Single vertical slide for YouTube Shorts (1080×1920) — key metrics only."""
    fig = plt.figure(figsize=(10.8, 19.2), facecolor=_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_BG)
    ax.axis("off")

    # Header
    ax.text(0.5, 0.98, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=_ACCENT, fontproperties=_fp(26), fontweight="bold")
    ax.axhline(0.955, xmin=0.05, xmax=0.95, color=_ACCENT, lw=3)
    # If symbol == company_name (sector mode), show simpler header
    if symbol == company_name or not symbol.isdigit():
        header_text = f"{company_name} 三大法人週報"
    else:
        header_text = f"{company_name}（{symbol}）三大法人週報"
    ax.text(0.5, 0.925, header_text,
            transform=ax.transAxes, ha="center", va="center",
            color=_TEXT, fontproperties=_fp(40), fontweight="bold")
    ax.text(0.5, 0.89, date_range, transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(26))

    # Foreign net big number — display in 萬張 for large values, 張 otherwise
    foreign_k = _compute_foreign_net_k(summary, daily)  # unit: 張
    is_buy = foreign_k >= 0
    val_color = _GREEN if is_buy else _RED
    label = "外資買超" if is_buy else "外資賣超"
    abs_k = abs(foreign_k)
    if abs_k >= 10000:
        num_str = f"{abs_k / 10000:.1f}".rstrip("0").rstrip(".")
        unit_str = "萬張"
    else:
        num_str = f"{abs_k:,}"
        unit_str = "張"

    ax.text(0.5, 0.82, label, transform=ax.transAxes,
            ha="center", va="center", color=val_color, fontproperties=_fp(48), fontweight="bold")
    ax.text(0.5, 0.74, num_str, transform=ax.transAxes,
            ha="center", va="center", color=val_color, fontproperties=_fp(88), fontweight="bold")
    ax.text(0.5, 0.69, unit_str, transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(32))

    # Daily bar mini chart (last 5 days of foreign net, unit: 張)
    recent = daily[-5:] if len(daily) >= 5 else daily
    dates_short = [d["date"][-5:] for d in recent]  # MM-DD
    vals = [round(d.get("foreign", {}).get("net", 0) / 1000) for d in recent]
    colors = [_GREEN if v >= 0 else _RED for v in vals]

    ax_bar = fig.add_axes([0.12, 0.18, 0.76, 0.33], facecolor=_CARD_BG)
    ax_bar.bar(dates_short, vals, color=colors, width=0.45)
    ax_bar.axhline(0, color=_GRID, lw=1)
    ax_bar.set_facecolor(_CARD_BG)
    ax_bar.tick_params(axis="x", colors=_MUTED, labelsize=22)
    ax_bar.tick_params(axis="y", colors=_MUTED, labelsize=16)
    ax_bar.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax_bar.set_title("近期外資買賣超（張）", fontproperties=_fp(24), color=_MUTED, pad=16)
    for spine in ax_bar.spines.values():
        spine.set_edgecolor(_GRID)
    # Add value labels on bars — place inside bar if it would go out of bounds
    max_abs_val = max((abs(x) for x in vals), default=1)
    y_min, y_max = ax_bar.get_ylim()
    y_margin = (y_max - y_min) * 0.12
    ax_bar.set_ylim(y_min - y_margin, y_max + y_margin)
    for i, v in enumerate(vals):
        if v != 0:
            offset = max_abs_val * 0.04 * (1 if v >= 0 else -1)
            ax_bar.text(i, v + offset,
                        f"{v:,}", ha="center", va="bottom" if v >= 0 else "top",
                        color=_TEXT, fontproperties=_fp(14), clip_on=True)

    # Footer CTA — use fig.text to ensure it's always at the very bottom
    fig.text(0.5, 0.06, "━" * 30, ha="center", va="center",
             color=_ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.035, "訂閱 JARVIS 選股｜每天更新",
             ha="center", va="center", color=_ACCENT,
             fontproperties=_fp(28), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((_SHORTS_W, _SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)


# ── Cleanup helper ─────────────────────────────────────────────────────────────

def _cleanup_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


# ── Endpoint ───────────────────────────────────────────────────────────────────

def _compute_foreign_net_k(summary: dict, daily: list[dict]) -> int:
    """Return total foreign net in 千張 from summary or daily fallback."""
    total = summary.get("foreign_net_total")
    if total is None and daily:
        total = sum(d.get("foreign", {}).get("net", 0) for d in daily)
    return round((total or 0) / 1000)


@router.get("/video/thumbnail", summary="Generate YouTube thumbnail PNG")
def get_thumbnail(symbol: str, days: int = 7) -> Response:
    """Return a 1280×720 PNG thumbnail for the given stock symbol."""
    symbol = symbol.upper().strip()
    chip = _get_chip_data(symbol, days)
    daily = chip.get("daily", [])
    if not daily:
        raise HTTPException(404, f"No chip data for {symbol}")

    summary      = chip.get("summary", {})
    company_name = _get_company_name(symbol)
    date_range   = f"{daily[0]['date']} ～ {daily[-1]['date']}"
    foreign_net_k = _compute_foreign_net_k(summary, daily)

    png_bytes = make_thumbnail(symbol, company_name, foreign_net_k, date_range)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{symbol}_thumbnail.png"'},
    )


@router.post("/video/generate", summary="Generate a YouTube-style analysis video")
def generate_video(req: VideoRequest) -> FileResponse:
    """
    Generate a ~45-second YouTube analysis video for a Taiwan stock symbol.

    - Fetches institutional chip data for the past `days` days
    - Renders 5 slides (title, 外資, 投信/自營, cumulative, summary)
    - Optionally voices the script via ElevenLabs (set ELEVENLABS_API_KEY)
    - Returns an MP4 file
    - Also saves thumbnail PNG alongside (same tmp dir, deleted after response)
    """
    is_shorts = req.format.lower() == "shorts"

    # ── Sector mode ──────────────────────────────────────────────────────────
    sector_name = req.sector_name.strip()
    symbols_raw = [s.upper().strip() for s in req.symbols if s.strip()]

    # Resolve built-in sector if no explicit symbols provided
    if sector_name and not symbols_raw:
        key = next((k for k in SECTOR_SYMBOLS if k in sector_name), None)
        symbols_raw = SECTOR_SYMBOLS.get(key or sector_name, [])

    is_sector = bool(sector_name and symbols_raw)

    if is_sector:
        # ── Sector report ────────────────────────────────────────────────────
        chip  = _get_sector_chip(symbols_raw, sector_name, req.days)
        daily = chip["daily"]
        summary = chip["summary"]
        date_range = f"{daily[0]['date']} ～ {daily[-1]['date']}" if daily else "N/A"
        foreign_net_k = _compute_foreign_net_k(summary, daily)
        symbol_label  = sector_name.replace("族群", "").strip()

        # Re-fetch per-symbol daily for breakdown chart
        symbols_data: list[dict] = []
        for sym_info in chip["symbols"]:
            try:
                sd = _get_chip_data(sym_info["symbol"], req.days)
                symbols_data.append({**sym_info, **sd})
            except Exception:
                pass

        frames: list[tuple[np.ndarray, int]] = [
            (_make_sector_title_slide(sector_name, chip["symbols"], date_range), SLIDE_SECONDS["title"]),
            (_make_foreign_chart(daily),                    SLIDE_SECONDS["chart"]),
            (_make_trust_dealer_chart(daily),               SLIDE_SECONDS["chart"]),
            (_make_sector_breakdown_chart(symbols_data, req.days), SLIDE_SECONDS["chart"]),
            (_make_summary_slide(summary, date_range),      SLIDE_SECONDS["summary"]),
        ]
        thumb_label   = sector_name
        thumb_company = sector_name
        filename_base = f"{symbol_label}_sector"

    else:
        # ── Single stock report ──────────────────────────────────────────────
        symbol = req.symbol.upper().strip()
        chip  = _get_chip_data(symbol, req.days)
        daily = chip.get("daily", [])
        if not daily:
            raise HTTPException(404, f"No chip data for {symbol}")

        summary       = chip.get("summary", {})
        company_name  = _get_company_name(symbol)
        date_range    = f"{daily[0]['date']} ～ {daily[-1]['date']}"
        foreign_net_k = _compute_foreign_net_k(summary, daily)

        if is_shorts:
            frames = [
                (_make_shorts_slide(symbol, company_name, date_range, summary, daily), 58),
            ]
        else:
            frames = [
                (_make_title_slide(symbol, company_name, date_range), SLIDE_SECONDS["title"]),
                (_make_foreign_chart(daily),                          SLIDE_SECONDS["chart"]),
                (_make_trust_dealer_chart(daily),                     SLIDE_SECONDS["chart"]),
                (_make_cumulative_chart(daily),                       SLIDE_SECONDS["chart"]),
                (_make_summary_slide(summary, date_range),            SLIDE_SECONDS["summary"]),
            ]
        thumb_company = company_name
        thumb_label   = symbol
        filename_base = f"{symbol}_{'shorts' if is_shorts else 'chip_report'}"

    # ── TTS ──────────────────────────────────────────────────────────────────
    tts_rate = "+35%" if is_shorts else None
    if req.script:
        spoken = _clean_script_for_tts(req.script)
        audio = _tts_edge(spoken[:500] if is_shorts else spoken, rate=tts_rate)
    else:
        audio = None

    # ── Write video ───────────────────────────────────────────────────────────
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp.close()

    if not is_shorts:
        try:
            png_bytes = make_thumbnail(thumb_label, thumb_company, foreign_net_k, date_range)
            thumb_path = Path(tempfile.gettempdir()) / f"{thumb_label}_thumbnail.png"
            thumb_path.write_bytes(png_bytes)
        except Exception:
            logger.exception("Thumbnail generation failed — continuing without")

    try:
        _build_mp4(frames, audio, tmp.name)
    except Exception as exc:
        _cleanup_file(tmp.name)
        logger.exception("Video generation failed")
        raise HTTPException(500, f"Video generation failed: {exc}") from exc

    return FileResponse(
        tmp.name,
        media_type="video/mp4",
        filename=f"{filename_base}.mp4",
        background=BackgroundTask(_cleanup_file, tmp.name),
    )


# ── Pick Stock for n8n ───────────────────────────────────────────────────────

from enum import Enum
from typing import Optional

from domain.calendar.planner import (
    _DEFAULT_SYMBOLS,
    _fetch_chip,
    _generate_title,
    _pick_top,
    _score_symbols,
)


class SlotType(str, Enum):
    morning = "morning"
    afternoon = "afternoon"
    long_tuesday = "long_tuesday"
    long_friday = "long_friday"
    weekly_review = "weekly_review"
    sat_am = "sat_am"
    sat_pm = "sat_pm"
    sun_am = "sun_am"
    sun_pm = "sun_pm"


class PickStockRequest(BaseModel):
    slot: SlotType
    exclude_symbols: list[str] = []


class ChipSummary(BaseModel):
    foreign_net: int
    trust_net: int
    dealer_net: int


class PickStockResponse(BaseModel):
    symbol: str
    title: str
    pick_reason: str
    chip_summary: ChipSummary
    data_date: str
    is_holiday_fallback: bool


class WeeklyReviewResponse(BaseModel):
    symbols: list[PickStockResponse]
    data_date: str
    is_holiday_fallback: bool


def _score_symbols_with_fallback(
    symbols: list[str],
    max_lookback: int = 5,
) -> tuple[list[dict], str, bool]:
    """Score symbols, falling back to previous trading days if today has no data.

    Returns (scored_list, data_date, is_fallback).
    """
    from datetime import date as _date, timedelta as _td

    for offset in range(max_lookback):
        target = _date.today() - _td(days=offset)
        target_str = target.isoformat()

        # _score_symbols fetches chip data from the local API which uses
        # date.today() internally. We need to fetch chip for the target date
        # directly to check availability.
        scored: list[dict] = []
        for sym in symbols:
            end = target_str
            start = (target - _td(days=15)).isoformat()
            url = f"http://localhost:8000/api/chip/{sym}/range?start={start}&end={end}"
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(url, headers={"Accept": "application/json"}),
                    timeout=15,
                ) as resp:
                    chip = json.loads(resp.read())
            except Exception:
                continue

            if not chip or not chip.get("daily"):
                continue

            daily = chip["daily"]

            totals = [d.get("total_net", 0) for d in daily]
            foreign = [d.get("foreign", {}).get("net", 0) for d in daily]
            trust = [d.get("investment_trust", {}).get("net", 0) for d in daily]
            dealer = [d.get("dealer", {}).get("net", 0) for d in daily]

            abs_volume = sum(abs(t) for t in totals)
            momentum = sum(totals)
            mean_total = (
                sum(totals[:-1]) / max(1, len(totals) - 1) if len(totals) > 1 else 0
            )
            reversal = abs(totals[-1] - mean_total) if totals else 0
            trust_surge = max(abs(t) for t in trust) if trust else 0

            scored.append({
                "symbol": sym,
                "abs_volume": abs_volume,
                "momentum": momentum,
                "reversal": reversal,
                "trust_surge": trust_surge,
                "foreign_net": sum(foreign),
                "trust_net": sum(trust),
                "dealer_net": sum(dealer),
                "daily": daily,
            })

        if scored:
            is_fallback = offset > 0
            return scored, target_str, is_fallback

    return [], _date.today().isoformat(), False


def _build_chip_summary(pick: dict) -> ChipSummary:
    """Extract chip summary from a scored pick dict."""
    return ChipSummary(
        foreign_net=pick.get("foreign_net", 0),
        trust_net=pick.get("trust_net", 0),
        dealer_net=pick.get("dealer_net", 0),
    )


def _build_pick_response(
    pick: dict,
    template_type: str,
    reason: str,
    data_date: str,
    is_fallback: bool,
) -> PickStockResponse:
    """Build a PickStockResponse from a scored pick."""
    title = _generate_title(template_type, pick["symbol"], pick)
    return PickStockResponse(
        symbol=pick["symbol"],
        title=title,
        pick_reason=reason,
        chip_summary=_build_chip_summary(pick),
        data_date=data_date,
        is_holiday_fallback=is_fallback,
    )


# Slot → (scoring_key, title_template, reason_template)
_SLOT_CONFIG: dict[str, tuple[str, str, str]] = {
    "morning": (
        "foreign_net",
        "shorts",
        "外資淨買賣最大 ({value:,.0f})",
    ),
    "afternoon": (
        "abs_volume",
        "shorts",
        "法人成交量最大 ({value:,.0f})",
    ),
    "long_tuesday": (
        "momentum",
        "momentum",
        "三大法人淨買超動能最強 ({value:,.0f})",
    ),
    "long_friday": (
        "abs_volume",
        "abs_volume",
        "法人成交量最大 ({value:,.0f})",
    ),
    "sat_am": (
        "foreign_net",
        "shorts",
        "外資淨買賣最大 ({value:,.0f})",
    ),
    "sat_pm": (
        "abs_volume",
        "shorts",
        "法人成交量最大 ({value:,.0f})",
    ),
    "sun_am": (
        "momentum",
        "shorts",
        "三大法人淨買超動能最強 ({value:,.0f})",
    ),
    "sun_pm": (
        "abs_volume",
        "shorts",
        "法人成交量最大 ({value:,.0f})",
    ),
}

_SHORTS_SLOTS = ("morning", "afternoon", "sat_am", "sat_pm", "sun_am", "sun_pm")


@router.post(
    "/video-gen/pick-stock",
    summary="Pick best stock for a video slot (stateless, for n8n)",
    response_model=PickStockResponse | WeeklyReviewResponse,
)
def pick_stock(req: PickStockRequest):
    """Stateless stock picker for n8n video automation.

    Scores portfolio stocks by chip data and returns the best pick
    for the requested slot. Automatically falls back to the last
    trading day with data if today is a weekend or holiday.
    """
    exclude = set(s.upper().strip() for s in req.exclude_symbols)
    symbols = _DEFAULT_SYMBOLS

    scored, data_date, is_fallback = _score_symbols_with_fallback(symbols)
    if not scored:
        raise HTTPException(
            status_code=404,
            detail="No chip data available for the last 5 trading days.",
        )

    slot = req.slot.value

    # ── weekly_review / long_friday: return top 3-5 symbols ────────────────
    if slot in ("weekly_review", "long_friday"):
        candidates = [s for s in scored if s["symbol"] not in exclude]
        candidates.sort(key=lambda x: x.get("abs_volume", 0), reverse=True)
        top = candidates[:5]
        if not top:
            raise HTTPException(
                status_code=404,
                detail="All symbols excluded — no candidates left.",
            )
        items = [
            _build_pick_response(
                pick=p,
                template_type="abs_volume",
                reason=f"本週法人成交量排名 #{i + 1} ({p.get('abs_volume', 0):,.0f})",
                data_date=data_date,
                is_fallback=is_fallback,
            )
            for i, p in enumerate(top)
        ]
        return WeeklyReviewResponse(
            symbols=items,
            data_date=data_date,
            is_holiday_fallback=is_fallback,
        )

    # ── Single-pick slots ────────────────────────────────────────────────────
    config = _SLOT_CONFIG.get(slot)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unknown slot: {slot}")

    scoring_key, title_template, reason_template = config

    # For morning slot, pick by absolute value of foreign_net
    if slot == "morning":
        candidates = [s for s in scored if s["symbol"] not in exclude]
        if not candidates:
            raise HTTPException(
                status_code=404,
                detail="All symbols excluded — no candidates left.",
            )
        pick = max(candidates, key=lambda x: abs(x.get("foreign_net", 0)))
    else:
        pick = _pick_top(scored, scoring_key, exclude)

    if not pick:
        raise HTTPException(
            status_code=404,
            detail="All symbols excluded — no candidates left.",
        )

    reason = reason_template.format(value=pick.get(scoring_key, 0))
    return _build_pick_response(
        pick=pick,
        template_type=title_template,
        reason=reason,
        data_date=data_date,
        is_fallback=is_fallback,
    )


# ── n8n-friendly: Generate + Upload (JSON API) ─────────────────────────────
# Reuses all calendar.py logic: OpenAI script, TTS, CTR titles, SEO descriptions


class N8nGenerateRequest(BaseModel):
    symbol: str
    title: str
    slot: str = "morning"
    is_holiday_fallback: bool = False


class N8nGenerateResponse(BaseModel):
    video_path: str
    thumbnail_path: Optional[str] = None
    title: str
    description: str
    tags: list[str]
    script: str
    symbol: str
    slot: str


@router.post(
    "/video-gen/generate",
    summary="Generate video with full pipeline (script+TTS+CTR title) for n8n",
    response_model=N8nGenerateResponse,
)
def n8n_generate_video(req: N8nGenerateRequest):
    """Full video generation pipeline for n8n, reusing calendar.py logic.

    1. Build episode dict from pick-stock output
    2. Generate OpenAI script (_generate_script)
    3. Render video with TTS (_generate_video)
    4. Generate thumbnail (_generate_thumbnail)
    5. Build CTR title (_build_algo_title)
    6. Build SEO description (_build_algo_description)
    7. Build tags (_build_algo_tags)
    8. Return JSON with all metadata + file paths
    """
    from apps.api.routers.calendar import (
        _generate_script,
        _generate_video,
        _generate_thumbnail,
        _fetch_chip_summary,
        _get_company_name_for_title,
        _build_algo_title,
        _build_algo_description,
        _build_algo_tags,
    )

    symbol = req.symbol.upper().strip()
    is_shorts = req.slot in _SHORTS_SLOTS

    # Map slot to content_type
    slot_content_type = {
        "morning": "single",
        "afternoon": "single",
        "long_tuesday": "single",
        "long_friday": "macro",
        "sat_am": "single",
        "sat_pm": "single",
        "sun_am": "single",
        "sun_pm": "single",
    }
    content_type = slot_content_type.get(req.slot, "single")

    # Build episode dict matching calendar.py's expected format
    episode = {
        "symbol": symbol,
        "title": req.title,
        "content_type": content_type,
        "pick_reason": "",
        "sector_name": "",
        "symbols": [],
        "metadata": {
            "format": "shorts" if is_shorts else "landscape",
            "days": 7,
            "weekly_review": req.slot == "long_friday",
            "breaking": False,
        },
    }

    # Step 1: Generate script via OpenAI
    script = _generate_script(episode)

    # Step 2: Generate video (with script + TTS)
    try:
        video_path = _generate_video(episode, script)
    except Exception as exc:
        raise HTTPException(500, f"Video generation failed: {exc}") from exc

    # Step 3: Generate thumbnail (long-form only)
    thumb_path = _generate_thumbnail(episode)

    # Step 4: Build CTR-optimized title + SEO description + tags
    chip = _fetch_chip_summary(symbol, days=7) if symbol else {}
    company_name = _get_company_name_for_title(symbol) if symbol else ""

    algo_title = _build_algo_title(episode, chip, company_name, is_shorts)
    description = _build_algo_description(episode, chip, company_name, is_shorts, script)
    tags = _build_algo_tags(episode, company_name, is_shorts)

    return N8nGenerateResponse(
        video_path=video_path,
        thumbnail_path=thumb_path,
        title=algo_title,
        description=description,
        tags=tags,
        script=script,
        symbol=symbol,
        slot=req.slot,
    )


class N8nUploadRequest(BaseModel):
    video_path: str
    title: str
    description: str = ""
    tags: list[str] = []
    script: str = ""
    slot: str = "morning"
    privacy: str = "public"
    publish_time: Optional[str] = None  # e.g. "08:00", "14:30"
    thumbnail_path: Optional[str] = None
    symbol: str = ""


class N8nUploadResponse(BaseModel):
    video_id: str
    url: str
    title: str
    privacy: str
    publish_at: Optional[str] = None


@router.post(
    "/video-gen/upload-youtube",
    summary="Upload video to YouTube with publishAt scheduling (for n8n)",
    response_model=N8nUploadResponse,
)
def n8n_upload_youtube(req: N8nUploadRequest):
    """Upload video to YouTube, reusing calendar.py's upload logic.

    Supports publishAt scheduling: pass publish_time (e.g. "08:00") and
    video uploads as private, YouTube auto-publishes at scheduled time.
    """
    from apps.api.routers.youtube_upload import (
        _build_youtube_client,
        _upload_video,
        _set_thumbnail,
        _ensure_playlists,
        _add_to_playlist,
    )

    video_path = req.video_path
    if not Path(video_path).exists():
        raise HTTPException(404, f"Video file not found: {video_path}")

    privacy = req.privacy.lower()
    if privacy not in ("public", "unlisted", "private"):
        raise HTTPException(400, "privacy must be public, unlisted, or private")

    is_shorts = req.slot in _SHORTS_SLOTS

    # Compute publishAt if publish_time provided
    publish_at: str | None = None
    if req.publish_time:
        try:
            from datetime import datetime, date, timezone, timedelta
            hour, minute = (int(x) for x in req.publish_time.split(":"))
            today = date.today()
            taipei_tz = timezone(timedelta(hours=8))
            publish_dt = datetime(today.year, today.month, today.day,
                                 hour, minute, 0, tzinfo=taipei_tz)
            publish_at = publish_dt.isoformat()
            # When using publishAt, upload as private first
            privacy = "private"
        except (ValueError, TypeError):
            logger.warning("Could not parse publish_time: %s", req.publish_time)

    try:
        youtube = _build_youtube_client()
        video_id = _upload_video(
            youtube, video_path, req.title[:100], req.description,
            req.tags, privacy, publish_at,
        )

        # Set thumbnail if available
        if req.thumbnail_path and Path(req.thumbnail_path).exists():
            try:
                _set_thumbnail(youtube, video_id, req.thumbnail_path)
            except Exception:
                logger.exception("Thumbnail upload failed — continuing")

        # Add to playlist
        slot_playlist_map = {
            "morning": "每日快報",
            "afternoon": "每日快報",
            "long_tuesday": "個股分析",
            "long_friday": "大盤週報",
        }
        playlist_name = slot_playlist_map.get(req.slot)
        if playlist_name:
            try:
                playlists = _ensure_playlists(youtube)
                pid = playlists.get(playlist_name)
                if pid:
                    _add_to_playlist(youtube, video_id, pid)
            except Exception:
                logger.exception("Playlist add failed — continuing")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"YouTube upload failed: {exc}") from exc
    finally:
        _cleanup_file(video_path)
        if req.thumbnail_path:
            _cleanup_file(req.thumbnail_path)

    return N8nUploadResponse(
        video_id=video_id,
        url=f"https://youtu.be/{video_id}",
        title=req.title,
        privacy=privacy,
        publish_at=publish_at,
    )


# ── Sector endpoints for n8n weekend/Tuesday workflows ────────────────────────


class PickSectorRequest(BaseModel):
    exclude_themes: list[str] = []
    force_refresh: bool = False


class PickSectorResponse(BaseModel):
    sector_name: str
    symbols: list[dict]
    slot: str
    summary: dict


@router.post(
    "/video-gen/pick-sector-smart",
    summary="Pick best sector for a video (stateless, for n8n)",
    response_model=PickSectorResponse,
)
def pick_sector_smart(req: PickSectorRequest):
    """Score all sector groups by chip activity and return the most active one.

    Used by n8n for Saturday/Sunday族群分析 and Tuesday族群分析.
    """
    from concurrent.futures import ThreadPoolExecutor

    exclude = set(t.strip() for t in req.exclude_themes)
    candidates = {
        name: syms for name, syms in SECTOR_SYMBOLS.items()
        if name not in exclude
    }

    if not candidates:
        raise HTTPException(400, "All sectors excluded")

    # Score each sector by total absolute chip volume
    sector_scores: list[dict] = []
    for sector_name, symbols in candidates.items():
        try:
            sector_data = _get_sector_chip(symbols, sector_name, days=5)
            summary = sector_data["summary"]
            abs_volume = (
                abs(summary.get("foreign_net_total", 0))
                + abs(summary.get("investment_trust_net_total", 0))
                + abs(summary.get("dealer_net_total", 0))
            )
            sector_scores.append({
                "sector_name": sector_name,
                "symbols": sector_data["symbols"],
                "summary": summary,
                "abs_volume": abs_volume,
            })
        except Exception:
            logger.warning("Sector scoring failed for %s", sector_name)

    if not sector_scores:
        raise HTTPException(502, "No sector data available")

    # Pick the sector with highest absolute chip activity
    best = max(sector_scores, key=lambda x: x["abs_volume"])

    # Determine slot based on day of week
    today = date.today()
    weekday = today.weekday()
    if weekday == 1:  # Tuesday
        slot = "long_tuesday"
    elif weekday == 5:  # Saturday
        slot = "weekend_am"
    elif weekday == 6:  # Sunday
        slot = "weekend_pm"
    else:
        slot = "sector"

    return PickSectorResponse(
        sector_name=best["sector_name"],
        symbols=best["symbols"],
        slot=slot,
        summary=best["summary"],
    )


class GenerateSectorRequest(BaseModel):
    sector_name: str
    slot: str = "sector"
    format: str = "landscape"  # "landscape" (1920×1080) | "shorts" (1080×1920)


class GenerateSectorResponse(BaseModel):
    video_path: str
    thumbnail_path: Optional[str] = None
    title: str
    description: str
    tags: list[str]
    script: str
    sector_name: str
    slot: str


@router.post(
    "/video-gen/generate-sector",
    summary="Generate sector analysis video (for n8n)",
    response_model=GenerateSectorResponse,
)
def generate_sector_video(req: GenerateSectorRequest):
    """Generate a sector/族群 analysis video with chip data.

    1. Fetch chip data for all symbols in the sector
    2. Build slides (title + breakdown chart + cumulative chart)
    3. Generate OpenAI script
    4. TTS + ffmpeg → MP4
    """
    sector_name = req.sector_name
    if sector_name not in SECTOR_SYMBOLS:
        raise HTTPException(400, f"Unknown sector: {sector_name}")

    symbols = SECTOR_SYMBOLS[sector_name]
    days = 5

    # Fetch sector chip data
    sector_data = _get_sector_chip(symbols, sector_name, days)
    summary = sector_data["summary"]
    daily = sector_data["daily"]
    sym_list = sector_data["symbols"]

    if not daily:
        raise HTTPException(502, f"No chip data for sector {sector_name}")

    date_range = f"{daily[0]['date']} ~ {daily[-1]['date']}"

    is_shorts = req.format.lower() == "shorts"

    # Build slides
    _setup_matplotlib_fonts()

    # Re-fetch per-symbol daily for breakdown chart
    symbols_data: list[dict] = []
    for s in sym_list:
        try:
            sd = _get_chip_data(s["symbol"], days)
            symbols_data.append({**s, **sd})
        except Exception:
            pass

    # Generate script via OpenAI
    foreign = summary.get("foreign_net_total", 0)
    trust = summary.get("investment_trust_net_total", 0)
    dealer = summary.get("dealer_net_total", 0)
    f_sign = "買超" if foreign >= 0 else "賣超"
    t_sign = "買超" if trust >= 0 else "賣超"
    d_sign = "買超" if dealer >= 0 else "賣超"

    # Convert 股 → 張 (1張 = 1000股)
    foreign_k = round(foreign / 1000)
    trust_k = round(trust / 1000)
    dealer_k = round(dealer / 1000)

    if is_shorts:
        # Shorts: single portrait slide, 60-second script
        slide = _make_shorts_slide(
            f"{sector_name}族群", f"{sector_name}族群", date_range, summary, daily,
        )
        frames = [(slide, 58)]

        prompt = (
            f"你是台股分析 YouTuber。請用 60 秒口語化的中文講稿，快速分析"
            f"「{sector_name}」族群本週三大法人動態。\n"
            f"成分股：{'、'.join(s['name'] for s in sym_list)}\n"
            f"外資合計{f_sign} {abs(foreign_k):,} 張，"
            f"投信合計{t_sign} {abs(trust_k):,} 張。\n"
            f"請給出族群趨勢判斷和重點觀察。語氣活潑但專業。"
        )
        script = _openai_script(prompt, max_tokens=500)
    else:
        # Long-form: 5 slides, 4-5 minute script
        slide1 = _make_sector_title_slide(sector_name, sym_list, date_range)
        slide2 = _make_foreign_chart(daily)
        slide3 = _make_trust_dealer_chart(daily)
        slide4 = _make_sector_breakdown_chart(symbols_data, days)
        slide5 = _make_summary_slide(summary, date_range)

        frames = [
            (slide1, SLIDE_SECONDS["title"]),
            (slide2, SLIDE_SECONDS["chart"]),
            (slide3, SLIDE_SECONDS["chart"]),
            (slide4, SLIDE_SECONDS["chart"]),
            (slide5, SLIDE_SECONDS["summary"]),
        ]

        prompt = (
            f"你是台股分析 YouTuber。請寫一篇至少 1200 字的口語化中文講稿（約 4-5 分鐘），"
            f"深入分析「{sector_name}」族群本週三大法人動態。\n\n"
            f"成分股：{'、'.join(s['name'] for s in sym_list)}\n"
            f"外資合計{f_sign} {abs(foreign_k):,} 張，"
            f"投信合計{t_sign} {abs(trust_k):,} 張，"
            f"自營商合計{d_sign} {abs(dealer_k):,} 張。\n\n"
            f"請依以下段落詳細展開（每段至少 200 字）：\n"
            f"1) 開場與本週總覽\n"
            f"2) 外資動向解讀：每日進出節奏、可能原因\n"
            f"3) 投信與自營商動態：是否與外資同向、背離原因\n"
            f"4) 個股亮點：哪些成分股被特別加碼或減碼\n"
            f"5) 下週展望與操作建議\n\n"
            f"重要：講稿必須至少 1200 字，語氣活潑但專業，適合 YouTube 長片觀眾。"
        )
        script = _openai_script(prompt, max_tokens=2500)

    # TTS
    tts_rate = "+35%" if is_shorts else None
    spoken = _clean_script_for_tts(script)
    if is_shorts:
        spoken = spoken[:500]
    audio_bytes = _tts_edge(spoken, rate=tts_rate)
    if not audio_bytes:
        logger.warning("TTS failed for sector %s — generating video without audio", sector_name)

    # Build MP4
    import tempfile
    video_path = os.path.join(
        tempfile.gettempdir(),
        f"sector_{sector_name}_{date.today().strftime('%Y%m%d')}.mp4",
    )
    _build_mp4(frames, audio_bytes, video_path)

    if not Path(video_path).exists():
        raise HTTPException(500, "Video generation failed")

    # Build metadata
    if is_shorts:
        title = f"{sector_name}族群 外資{f_sign}{abs(foreign_k):,}張｜JARVIS 選股 #Shorts"
    else:
        title = f"{sector_name}族群週報 外資{f_sign}{abs(foreign_k):,}張｜JARVIS 選股"
    description = (
        f"{sector_name}族群 三大法人籌碼分析\n\n"
        f"{script}\n\n"
        f"成分股：{'、'.join(s['symbol'] + ' ' + s['name'] for s in sym_list)}\n\n"
        f"訂閱 JARVIS 選股｜每天更新\n"
        f"免責聲明：本內容僅供參考，不構成投資建議。\n\n"
        f"#台股 #{sector_name} #三大法人 #籌碼分析 #族群分析 #JARVIS選股"
    )
    tags = [
        "台股", sector_name, "三大法人", "籌碼分析", "族群分析",
        "外資", "投信", "JARVIS選股", "台股分析", "法人動態",
    ] + [s["symbol"] for s in sym_list]

    return GenerateSectorResponse(
        video_path=video_path,
        title=title,
        description=description,
        tags=tags,
        script=script,
        sector_name=sector_name,
        slot=req.slot,
    )
