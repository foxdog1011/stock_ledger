"""Matplotlib chart/slide rendering functions for video generation."""
from __future__ import annotations

import io

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image, ImageDraw

from apps.api.services.video_engine.constants import (
    ACCENT,
    BG,
    BLUE,
    CARD_BG,
    GREEN,
    GRID,
    MUTED,
    ORANGE,
    RED,
    SHORTS_H,
    SHORTS_W,
    TEXT,
    THUMB_H,
    THUMB_W,
    WIDTH,
    HEIGHT,
)
from apps.api.services.video_engine.fonts import fp, hex_to_rgb, pil_font


# ── Utility ──────────────────────────────────────────────────────────────────

def _fig_to_array(fig: plt.Figure) -> np.ndarray:
    """Render matplotlib figure -> RGB numpy array at target resolution."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    return np.array(img)


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


# ── Single-stock slides ──────────────────────────────────────────────────────

def make_title_slide(symbol: str, company_name: str, date_range: str) -> np.ndarray:
    fig = plt.figure(figsize=(19.2, 10.8), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    ax.axhline(0.86, xmin=0.08, xmax=0.92, color=ACCENT, lw=3)
    ax.axhline(0.14, xmin=0.08, xmax=0.92, color=ACCENT, lw=2, alpha=0.4)

    ax.text(0.5, 0.93, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(26), fontweight="bold")
    ax.text(0.5, 0.73, f"{company_name}（{symbol}）", transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(68), fontweight="bold")
    ax.text(0.5, 0.57, "三大法人週報", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(54))
    ax.text(0.5, 0.43, date_range, transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(30))
    ax.text(0.5, 0.25, "本週機構買賣超 完整分析", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(26))
    ax.text(0.5, 0.07, "訂閱 JARVIS 選股｜每天更新",
            transform=ax.transAxes, ha="center", va="center",
            color=ACCENT, alpha=0.8, fontproperties=fp(22))

    plt.tight_layout(pad=0)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def make_foreign_chart(daily: list[dict]) -> np.ndarray:
    dates = [d["date"][-5:] for d in daily]
    nets  = [round(d["foreign"]["net"] / 1000) for d in daily]
    colors = [GREEN if n >= 0 else RED for n in nets]

    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=BG)
    ax.set_facecolor(BG)

    bars = ax.bar(dates, nets, color=colors, width=0.55, edgecolor="none", zorder=3)

    for bar, val in zip(bars, nets):
        offset = max(abs(val) * 0.06, 30)
        va = "bottom" if val >= 0 else "top"
        y  = val + offset if val >= 0 else val - offset
        ax.text(bar.get_x() + bar.get_width() / 2, y,
                f"{val:+,}", ha="center", va=va,
                fontsize=20, color=TEXT, fontweight="bold")

    ax.axhline(0, color=MUTED, lw=1.5, alpha=0.5, zorder=2)
    ax.set_title("外資近週買賣超（張）", fontproperties=fp(40), color=TEXT, pad=18)
    ax.set_ylabel("張", fontproperties=fp(20), color=MUTED)
    ax.tick_params(colors=TEXT, labelsize=20)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    ax.grid(axis="y", color=GRID, lw=1, zorder=1)

    plt.tight_layout(pad=1.5)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def make_trust_dealer_chart(daily: list[dict]) -> np.ndarray:
    dates   = [d["date"][-5:] for d in daily]
    trusts  = [round(d["investment_trust"]["net"] / 1000) for d in daily]
    dealers = [round(d["dealer"]["net"] / 1000) for d in daily]

    x = np.arange(len(dates))
    w = 0.35

    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=BG)
    ax.set_facecolor(BG)

    ax.bar(x - w / 2, trusts,  w, label="投信",
           color=[GREEN if v >= 0 else RED for v in trusts],
           alpha=0.9, edgecolor="none", zorder=3)
    ax.bar(x + w / 2, dealers, w, label="自營商",
           color=[BLUE if v >= 0 else ORANGE for v in dealers],
           alpha=0.9, edgecolor="none", zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(dates, fontsize=20)
    ax.axhline(0, color=MUTED, lw=1.5, alpha=0.5, zorder=2)
    ax.set_title("投信 / 自營商 近週買賣超（張）", fontproperties=fp(40), color=TEXT, pad=18)
    ax.set_ylabel("張", fontproperties=fp(20), color=MUTED)
    ax.tick_params(colors=TEXT, labelsize=20)
    ax.legend(prop=fp(22), facecolor=CARD_BG, edgecolor=ACCENT, labelcolor=TEXT)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    ax.grid(axis="y", color=GRID, lw=1, zorder=1)

    plt.tight_layout(pad=1.5)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def make_cumulative_chart(daily: list[dict]) -> np.ndarray:
    dates = [d["date"][-5:] for d in daily]
    running, total = [], 0
    for d in daily:
        total += round(d["total_net"] / 1000)
        running.append(total)

    final_color = GREEN if (running[-1] >= 0 if running else True) else RED

    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=BG)
    ax.set_facecolor(BG)

    x = range(len(dates))
    ax.fill_between(x, running, alpha=0.25, color=final_color, zorder=2)
    ax.plot(x, running, color=final_color, lw=4,
            marker="o", markersize=14, zorder=3)

    span = max(running) - min(running) if len(running) > 1 else 1
    for i, (v, _d) in enumerate(zip(running, dates)):
        ax.text(i, v + span * 0.08, f"{v:+,}",
                ha="center", fontsize=19, color=TEXT, fontweight="bold")

    ax.set_xticks(list(x))
    ax.set_xticklabels(dates, fontsize=20)
    ax.axhline(0, color=MUTED, lw=1.5, alpha=0.5, zorder=1)
    ax.set_title("三大法人 累積淨買超（張）", fontproperties=fp(40), color=TEXT, pad=18)
    ax.set_ylabel("張", fontproperties=fp(20), color=MUTED)
    ax.tick_params(colors=TEXT, labelsize=20)
    for sp in ax.spines.values():
        sp.set_edgecolor(GRID)
    ax.grid(color=GRID, lw=1, zorder=0)

    plt.tight_layout(pad=1.5)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def make_summary_slide(summary: dict, date_range: str) -> np.ndarray:
    foreign_k = round(summary.get("foreign_net_total", 0) / 1000)
    trust_k   = round(summary.get("investment_trust_net_total", 0) / 1000)
    dealer_k  = round(summary.get("dealer_net_total", 0) / 1000)

    fig = plt.figure(figsize=(19.2, 10.8), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    ax.axhline(0.86, xmin=0.06, xmax=0.94, color=ACCENT, lw=2.5)
    ax.text(0.5, 0.93, f"本週總結  {date_range}", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(36))

    metrics = [
        ("外資", foreign_k, ACCENT),
        ("投信", trust_k,   GREEN),
        ("自營商", dealer_k, BLUE),
    ]
    xs = [0.20, 0.50, 0.80]
    for (label, val, clr), cx in zip(metrics, xs):
        val_color = GREEN if val >= 0 else RED
        trend_txt = "▲ 買超" if val >= 0 else "▼ 賣超"
        sign = "+" if val >= 0 else ""

        rect = plt.Rectangle(
            (cx - 0.135, 0.33), 0.27, 0.45,
            transform=ax.transAxes, clip_on=False,
            facecolor=CARD_BG, edgecolor=clr, linewidth=3
        )
        ax.add_patch(rect)

        ax.text(cx, 0.70, label, transform=ax.transAxes,
                ha="center", va="center", color=clr, fontproperties=fp(34))
        ax.text(cx, 0.54, f"{sign}{val:,} 張", transform=ax.transAxes,
                ha="center", va="center", color=val_color, fontproperties=fp(30))
        ax.text(cx, 0.40, trend_txt, transform=ax.transAxes,
                ha="center", va="center", color=val_color, fontproperties=fp(24))

    ax.axhline(0.28, xmin=0.06, xmax=0.94, color=GRID, lw=1.5)
    ax.text(0.5, 0.20, "以上資訊僅供參考，不構成任何投資建議，請自行評估風險。",
            transform=ax.transAxes, ha="center", va="center",
            color=MUTED, fontproperties=fp(20))
    ax.text(0.5, 0.10, "按讚 + 訂閱 JARVIS 選股，每週一掌握三大法人動向！",
            transform=ax.transAxes, ha="center", va="center",
            color=ACCENT, fontproperties=fp(22))

    plt.tight_layout(pad=0)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


# ── YouTube Thumbnail ────────────────────────────────────────────────────────

def make_thumbnail(
    symbol: str,
    company_name: str,
    foreign_net_k: int,
    date_range: str,
) -> bytes:
    """Generate a YouTube-optimised thumbnail (1280x720) as PNG bytes.

    Layout:
      Left half  -- channel badge + company name + ticker
      Right half -- BIG number (外資 net) + 買超/賣超 label
    """
    img = Image.new("RGB", (THUMB_W, THUMB_H), hex_to_rgb(BG))
    draw = ImageDraw.Draw(img)

    # ── Gradient-ish left band ────────────────────────────────────────────
    for x in range(0, THUMB_W // 2):
        alpha = int(30 * (1 - x / (THUMB_W // 2)))
        for y in range(THUMB_H):
            r, g, b = img.getpixel((x, y))
            img.putpixel((x, y), (r + alpha, g + alpha, b + alpha))

    # ── Vertical accent bar ───────────────────────────────────────────────
    draw.rectangle([0, 0, 12, THUMB_H], fill=hex_to_rgb(ACCENT))

    # ── Channel name ──────────────────────────────────────────────────────
    font_channel = pil_font(38)
    draw.text((52, 52), "JARVIS 選股", font=font_channel, fill=hex_to_rgb(ACCENT))

    # ── Company name (large) ──────────────────────────────────────────────
    font_company = pil_font(110)
    draw.text((52, 120), company_name, font=font_company, fill=hex_to_rgb(TEXT))

    # ── Ticker badge ──────────────────────────────────────────────────────
    font_ticker = pil_font(52)
    _pad_x, _pad_y = 22, 10
    tbbox = draw.textbbox((0, 0), symbol, font=font_ticker)
    tw, th = tbbox[2] - tbbox[0], tbbox[3] - tbbox[1]
    bx, by = 52, 270
    rect_w, rect_h = tw + _pad_x * 2, th + _pad_y * 2
    _draw_rounded_rect(draw, (bx, by, bx + rect_w, by + rect_h), 14, hex_to_rgb(ACCENT))
    draw.text((bx + _pad_x - tbbox[0], by + _pad_y - tbbox[1]),
              symbol, font=font_ticker, fill=hex_to_rgb(BG))

    # ── Date range ────────────────────────────────────────────────────────
    font_date = pil_font(34)
    draw.text((52, THUMB_H - 80), date_range, font=font_date, fill=hex_to_rgb(MUTED))

    # ── Divider ───────────────────────────────────────────────────────────
    draw.rectangle([THUMB_W // 2 - 2, 40, THUMB_W // 2 + 2, THUMB_H - 40],
                   fill=hex_to_rgb(GRID))

    # ── Right side: main metric ───────────────────────────────────────────
    is_buy    = foreign_net_k >= 0
    val_color = hex_to_rgb(GREEN) if is_buy else hex_to_rgb(RED)
    label     = "外資買超" if is_buy else "外資賣超"
    sign      = "+" if is_buy else ""
    abs_k     = abs(foreign_net_k)

    if abs_k >= 10000:
        num_str  = f"{sign}{abs_k / 10000:.1f}萬"
        unit_str = "張"
    else:
        num_str  = f"{sign}{abs_k:,}"
        unit_str = "張"

    rx_start  = THUMB_W // 2 + 40
    right_w   = THUMB_W - rx_start
    ry_center = THUMB_H // 2

    def _rcenter(text_w: int) -> int:
        return rx_start + max(0, (right_w - text_w) // 2)

    # Label pill
    font_label = pil_font(52)
    lbbox = draw.textbbox((0, 0), label, font=font_label)
    lw, lh = lbbox[2] - lbbox[0], lbbox[3] - lbbox[1]
    l_pad_x, l_pad_y = 28, 12
    pill_w = lw + l_pad_x * 2
    lx = _rcenter(pill_w)
    pill_top = ry_center - 215
    _draw_rounded_rect(draw, (lx, pill_top, lx + pill_w, pill_top + lh + l_pad_y * 2),
                       22, val_color)
    draw.text((lx + l_pad_x - lbbox[0], pill_top + l_pad_y - lbbox[1]),
              label, font=font_label, fill=hex_to_rgb(BG))

    # Big number
    for num_pt in (180, 150, 120, 96):
        font_number = pil_font(num_pt)
        nbbox = draw.textbbox((0, 0), num_str, font=font_number)
        nw = nbbox[2] - nbbox[0]
        if nw <= right_w - 20:
            break
    nx = _rcenter(nw)
    draw.text((nx, ry_center - 130), num_str, font=font_number, fill=val_color)

    # Unit
    font_unit = pil_font(56)
    ubbox = draw.textbbox((0, 0), unit_str, font=font_unit)
    uw = ubbox[2] - ubbox[0]
    draw.text((_rcenter(uw), ry_center + 110), unit_str, font=font_unit, fill=hex_to_rgb(MUTED))

    # Suggested title at bottom
    font_title = pil_font(32)
    title_hint = f"{symbol} {company_name} 本週三大法人籌碼分析"
    tbbox = draw.textbbox((0, 0), title_hint, font=font_title)
    tw = tbbox[2] - tbbox[0]
    draw.text((_rcenter(tw), THUMB_H - 72), title_hint, font=font_title, fill=hex_to_rgb(MUTED))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Sector slides ────────────────────────────────────────────────────────────

def make_sector_title_slide(sector_name: str, symbols: list[dict], date_range: str) -> np.ndarray:
    fig = plt.figure(figsize=(19.2, 10.8), facecolor=BG)
    ax  = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    ax.axhline(0.86, xmin=0.08, xmax=0.92, color=ACCENT, lw=3)
    ax.axhline(0.14, xmin=0.08, xmax=0.92, color=ACCENT, lw=2, alpha=0.4)

    ax.text(0.5, 0.93, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(26), fontweight="bold")
    ax.text(0.5, 0.74, f"{sector_name}　族群週報", transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(62), fontweight="bold")
    ax.text(0.5, 0.57, date_range, transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(30))

    names = [f"{s['symbol']} {s['name']}" for s in symbols[:6]]
    badge_str = "　".join(names)
    ax.text(0.5, 0.42, badge_str, transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(22), alpha=0.9)

    ax.text(0.5, 0.25, "三大法人合計買賣超分析", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(26))
    ax.text(0.5, 0.07, "訂閱 JARVIS 選股｜每天更新",
            transform=ax.transAxes, ha="center", va="center",
            color=ACCENT, alpha=0.8, fontproperties=fp(22))

    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def make_sector_breakdown_chart(symbols_data: list[dict], days: int) -> np.ndarray:
    """Horizontal bar chart: each symbol's total foreign net for the period."""
    fig, ax = plt.subplots(figsize=(19.2, 10.8), facecolor=BG)
    ax.set_facecolor(BG)

    names  = [f"{s['symbol']}\n{s['name']}" for s in symbols_data]
    totals = []
    for s in symbols_data:
        foreign_total = sum(
            d.get("foreign", {}).get("net", 0) for d in s.get("daily", [])
        )
        totals.append(round(foreign_total / 1000))

    colors = [GREEN if v >= 0 else RED for v in totals]
    bars = ax.barh(names, totals, color=colors, height=0.6)
    ax.axvline(0, color=GRID, lw=1.5)

    for bar, val in zip(bars, totals):
        sign = "+" if val >= 0 else ""
        ax.text(bar.get_width() + (max(abs(t) for t in totals) * 0.02),
                bar.get_y() + bar.get_height() / 2,
                f"{sign}{val:,}", va="center", color=TEXT, fontproperties=fp(18))

    ax.set_title("各股外資買賣超（張）", fontproperties=fp(28), color=TEXT, pad=16)
    ax.set_xlabel("張", fontproperties=fp(20), color=MUTED)
    ax.tick_params(colors=MUTED, labelsize=16)
    for tick in ax.get_yticklabels():
        tick.set_fontproperties(fp(18))
    for spine in ax.spines.values():
        spine.set_edgecolor(GRID)
    ax.set_facecolor(CARD_BG)
    fig.patch.set_facecolor(BG)

    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


# ── Shorts slide (1080x1920 vertical) ───────────────────────────────────────

def make_shorts_slide(
    symbol: str,
    company_name: str,
    date_range: str,
    summary: dict,
    daily: list[dict],
    compute_foreign_net_k_fn: "callable",
) -> np.ndarray:
    """Single vertical slide for YouTube Shorts (1080x1920) -- key metrics only."""
    fig = plt.figure(figsize=(10.8, 19.2), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    # Header
    ax.text(0.5, 0.98, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(26), fontweight="bold")
    ax.axhline(0.955, xmin=0.05, xmax=0.95, color=ACCENT, lw=3)
    if symbol == company_name or not symbol.isdigit():
        header_text = f"{company_name} 三大法人週報"
    else:
        header_text = f"{company_name}（{symbol}）三大法人週報"
    ax.text(0.5, 0.925, header_text,
            transform=ax.transAxes, ha="center", va="center",
            color=TEXT, fontproperties=fp(40), fontweight="bold")
    ax.text(0.5, 0.89, date_range, transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(26))

    # Foreign net big number
    foreign_k = compute_foreign_net_k_fn(summary, daily)
    is_buy = foreign_k >= 0
    val_color = GREEN if is_buy else RED
    label = "外資買超" if is_buy else "外資賣超"
    abs_k = abs(foreign_k)
    if abs_k >= 10000:
        num_str = f"{abs_k / 10000:.1f}".rstrip("0").rstrip(".")
        unit_str = "萬張"
    else:
        num_str = f"{abs_k:,}"
        unit_str = "張"

    ax.text(0.5, 0.82, label, transform=ax.transAxes,
            ha="center", va="center", color=val_color, fontproperties=fp(48), fontweight="bold")
    ax.text(0.5, 0.74, num_str, transform=ax.transAxes,
            ha="center", va="center", color=val_color, fontproperties=fp(88), fontweight="bold")
    ax.text(0.5, 0.69, unit_str, transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(32))

    # Daily bar mini chart
    recent = daily[-5:] if len(daily) >= 5 else daily
    dates_short = [d["date"][-5:] for d in recent]
    vals = [round(d.get("foreign", {}).get("net", 0) / 1000) for d in recent]
    colors = [GREEN if v >= 0 else RED for v in vals]

    ax_bar = fig.add_axes([0.12, 0.18, 0.76, 0.33], facecolor=CARD_BG)
    ax_bar.bar(dates_short, vals, color=colors, width=0.45)
    ax_bar.axhline(0, color=GRID, lw=1)
    ax_bar.set_facecolor(CARD_BG)
    ax_bar.tick_params(axis="x", colors=MUTED, labelsize=22)
    ax_bar.tick_params(axis="y", colors=MUTED, labelsize=16)
    ax_bar.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax_bar.set_title("近期外資買賣超（張）", fontproperties=fp(24), color=MUTED, pad=16)
    for spine in ax_bar.spines.values():
        spine.set_edgecolor(GRID)
    max_abs_val = max((abs(x) for x in vals), default=1)
    y_min, y_max = ax_bar.get_ylim()
    y_margin = (y_max - y_min) * 0.12
    ax_bar.set_ylim(y_min - y_margin, y_max + y_margin)
    for i, v in enumerate(vals):
        if v != 0:
            offset = max_abs_val * 0.04 * (1 if v >= 0 else -1)
            ax_bar.text(i, v + offset,
                        f"{v:,}", ha="center", va="bottom" if v >= 0 else "top",
                        color=TEXT, fontproperties=fp(14), clip_on=True)

    # Footer CTA
    fig.text(0.5, 0.06, "━" * 30, ha="center", va="center",
             color=ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.035, "訂閱 JARVIS 選股｜每天更新",
             ha="center", va="center", color=ACCENT,
             fontproperties=fp(28), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((SHORTS_W, SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)
