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

    bars = ax.bar(dates, nets, color=colors, width=0.55,
                  edgecolor=TEXT, linewidth=1.5, zorder=3)

    # Add shadow bars behind for depth
    shadow_offset = 0.04
    ax.bar([i + shadow_offset for i in range(len(dates))], nets,
           color="#000000", width=0.55, alpha=0.2, zorder=2)

    for bar, val in zip(bars, nets):
        offset = max(abs(val) * 0.06, 30)
        va = "bottom" if val >= 0 else "top"
        y  = val + offset if val >= 0 else val - offset
        # Directional arrow next to value
        arrow = "↑" if val >= 0 else "↓"
        ax.text(bar.get_x() + bar.get_width() / 2, y,
                f"{arrow} {val:+,}", ha="center", va=va,
                fontsize=22, color=TEXT, fontweight="bold",
                bbox={"boxstyle": "round,pad=0.15", "facecolor": BG,
                      "edgecolor": "none", "alpha": 0.6})

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

    # Big directional arrow (visual anchor)
    arrow_str = "▲" if is_buy else "▼"
    font_arrow = pil_font(80)
    abbox = draw.textbbox((0, 0), arrow_str, font=font_arrow)
    aw = abbox[2] - abbox[0]
    draw.text((_rcenter(aw), ry_center - 280), arrow_str, font=font_arrow, fill=val_color)

    # Label pill
    font_label = pil_font(52)
    lbbox = draw.textbbox((0, 0), label, font=font_label)
    lw, lh = lbbox[2] - lbbox[0], lbbox[3] - lbbox[1]
    l_pad_x, l_pad_y = 28, 12
    pill_w = lw + l_pad_x * 2
    lx = _rcenter(pill_w)
    pill_top = ry_center - 175
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
    draw.text((nx, ry_center - 80), num_str, font=font_number, fill=val_color)

    # Unit
    font_unit = pil_font(56)
    ubbox = draw.textbbox((0, 0), unit_str, font=font_unit)
    uw = ubbox[2] - ubbox[0]
    draw.text((_rcenter(uw), ry_center + 140), unit_str, font=font_unit, fill=hex_to_rgb(MUTED))

    # Bottom accent bar (colored by buy/sell)
    draw.rectangle([THUMB_W // 2 + 20, THUMB_H - 12, THUMB_W - 20, THUMB_H],
                   fill=val_color)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Weekly review slides ────────────────────────────────────────────────────


def make_weekly_review_title_slide(
    symbols_info: list[dict],
    date_range: str,
) -> np.ndarray:
    """Title slide for weekly recap video (1920x1080 landscape).

    *symbols_info* items should have keys ``symbol`` and ``name``.
    """
    fig = plt.figure(figsize=(19.2, 10.8), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    ax.axhline(0.86, xmin=0.08, xmax=0.92, color=ACCENT, lw=3)
    ax.axhline(0.14, xmin=0.08, xmax=0.92, color=ACCENT, lw=2, alpha=0.4)

    ax.text(0.5, 0.93, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(26), fontweight="bold")
    ax.text(0.5, 0.73, "本週精選回顧", transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(62), fontweight="bold")
    ax.text(0.5, 0.57, date_range, transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(30))

    names = [f"{s['symbol']} {s['name']}" for s in symbols_info[:5]]
    badge_str = "　".join(names)
    ax.text(0.5, 0.42, badge_str, transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(22), alpha=0.9)

    ax.text(0.5, 0.25, "三大法人週報 完整分析", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(26))
    ax.text(0.5, 0.07, "訂閱 JARVIS 選股｜每天更新",
            transform=ax.transAxes, ha="center", va="center",
            color=ACCENT, alpha=0.8, fontproperties=fp(22))

    plt.tight_layout(pad=0)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def make_stock_summary_slide(
    symbol: str,
    company_name: str,
    foreign_net_data: list[dict],
    daily: list[dict],
) -> np.ndarray:
    """Compact per-stock slide for weekly recap (1920x1080 landscape).

    Shows stock name, a 5-day foreign net bar chart, and total foreign net.

    Parameters
    ----------
    symbol : str
        Ticker, e.g. ``"2330"``.
    company_name : str
        Chinese company name, e.g. ``"台積電"``.
    foreign_net_data : list[dict]
        Raw daily chip dicts (must contain ``date`` and ``foreign.net``).
    daily : list[dict]
        Same as *foreign_net_data* (kept for interface consistency).
    """
    recent = foreign_net_data[-5:] if len(foreign_net_data) >= 5 else foreign_net_data
    dates_short = [d["date"][-5:] for d in recent]
    vals = [round(d.get("foreign", {}).get("net", 0) / 1000) for d in recent]
    total_foreign = sum(vals)
    colors = [GREEN if v >= 0 else RED for v in vals]

    fig = plt.figure(figsize=(19.2, 10.8), facecolor=BG)

    # ── Top header area (using main axes) ──
    ax_header = fig.add_axes([0.0, 0.78, 1.0, 0.20], facecolor=BG)
    ax_header.axis("off")

    ax_header.text(0.5, 0.85, "JARVIS 選股", transform=ax_header.transAxes,
                   ha="center", va="center", color=ACCENT, fontproperties=fp(22))
    ax_header.axhline(0.65, xmin=0.08, xmax=0.92, color=ACCENT, lw=2)
    ax_header.text(0.5, 0.35, f"{company_name}（{symbol}）",
                   transform=ax_header.transAxes,
                   ha="center", va="center", color=TEXT,
                   fontproperties=fp(52), fontweight="bold")

    # ── Bar chart area ──
    ax_bar = fig.add_axes([0.10, 0.18, 0.55, 0.55], facecolor=CARD_BG)

    bars = ax_bar.bar(dates_short, vals, color=colors, width=0.55,
                      edgecolor=TEXT, linewidth=1.5, zorder=3)
    ax_bar.axhline(0, color=MUTED, lw=1.5, alpha=0.5, zorder=2)

    for bar, val in zip(bars, vals):
        offset = max(abs(val) * 0.08, 20)
        va_pos = "bottom" if val >= 0 else "top"
        y = val + offset if val >= 0 else val - offset
        arrow = "↑" if val >= 0 else "↓"
        ax_bar.text(bar.get_x() + bar.get_width() / 2, y,
                    f"{arrow} {val:+,}", ha="center", va=va_pos,
                    fontsize=20, color=TEXT, fontweight="bold",
                    bbox={"boxstyle": "round,pad=0.12", "facecolor": CARD_BG,
                          "edgecolor": "none", "alpha": 0.7})

    ax_bar.set_title("外資近 5 日買賣超（張）", fontproperties=fp(28), color=TEXT, pad=14)
    ax_bar.tick_params(colors=TEXT, labelsize=18)
    for sp in ax_bar.spines.values():
        sp.set_edgecolor(GRID)
    ax_bar.grid(axis="y", color=GRID, lw=1, zorder=1)

    # ── Right-side total metric card ──
    ax_metric = fig.add_axes([0.70, 0.22, 0.26, 0.48], facecolor=BG)
    ax_metric.axis("off")

    is_buy = total_foreign >= 0
    val_color = GREEN if is_buy else RED
    arrow_str = "▲" if is_buy else "▼"
    label = "外資買超" if is_buy else "外資賣超"
    sign = "+" if is_buy else ""

    rect = plt.Rectangle(
        (0.0, 0.0), 1.0, 1.0,
        transform=ax_metric.transAxes, clip_on=False,
        facecolor=CARD_BG, edgecolor=val_color, linewidth=3,
    )
    ax_metric.add_patch(rect)

    ax_metric.text(0.5, 0.85, label, transform=ax_metric.transAxes,
                   ha="center", va="center", color=val_color,
                   fontproperties=fp(28), fontweight="bold")
    ax_metric.text(0.5, 0.60, arrow_str, transform=ax_metric.transAxes,
                   ha="center", va="center", color=val_color,
                   fontproperties=fp(64), fontweight="bold", alpha=0.8)
    ax_metric.text(0.5, 0.35, f"{sign}{total_foreign:,}", transform=ax_metric.transAxes,
                   ha="center", va="center", color=val_color,
                   fontproperties=fp(48), fontweight="bold")
    ax_metric.text(0.5, 0.15, "張（5日合計）", transform=ax_metric.transAxes,
                   ha="center", va="center", color=MUTED, fontproperties=fp(20))

    # ── Footer ──
    fig.text(0.5, 0.06, "以上資訊僅供參考，不構成任何投資建議",
             ha="center", va="center", color=MUTED, fontproperties=fp(18))

    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


def make_weekly_review_summary_slide(
    symbols_summaries: list[dict],
    date_range: str,
) -> np.ndarray:
    """Final summary slide for weekly recap (1920x1080 landscape).

    *symbols_summaries* items should have ``symbol``, ``name``, and ``foreign_net_k``.
    """
    fig = plt.figure(figsize=(19.2, 10.8), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    ax.axhline(0.88, xmin=0.06, xmax=0.94, color=ACCENT, lw=2.5)
    ax.text(0.5, 0.94, f"本週精選總結  {date_range}", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(36))

    n = min(len(symbols_summaries), 5)
    xs = [0.5] if n == 1 else [round(0.12 + i * (0.76 / (n - 1)), 2) for i in range(n)]

    for i, ss in enumerate(symbols_summaries[:n]):
        cx = xs[i]
        val = ss.get("foreign_net_k", 0)
        val_color = GREEN if val >= 0 else RED
        sign = "+" if val >= 0 else ""
        trend_txt = "▲ 買超" if val >= 0 else "▼ 賣超"

        card_w = min(0.16, 0.7 / n)
        rect = plt.Rectangle(
            (cx - card_w / 2, 0.30), card_w, 0.48,
            transform=ax.transAxes, clip_on=False,
            facecolor=CARD_BG, edgecolor=ACCENT, linewidth=2,
        )
        ax.add_patch(rect)

        ax.text(cx, 0.70, ss.get("name", ss["symbol"]), transform=ax.transAxes,
                ha="center", va="center", color=TEXT, fontproperties=fp(26), fontweight="bold")
        ax.text(cx, 0.62, ss["symbol"], transform=ax.transAxes,
                ha="center", va="center", color=MUTED, fontproperties=fp(18))
        ax.text(cx, 0.50, f"{sign}{val:,} 張", transform=ax.transAxes,
                ha="center", va="center", color=val_color, fontproperties=fp(24))
        ax.text(cx, 0.38, trend_txt, transform=ax.transAxes,
                ha="center", va="center", color=val_color, fontproperties=fp(20))

    ax.axhline(0.24, xmin=0.06, xmax=0.94, color=GRID, lw=1.5)
    ax.text(0.5, 0.16, "以上資訊僅供參考，不構成任何投資建議，請自行評估風險。",
            transform=ax.transAxes, ha="center", va="center",
            color=MUTED, fontproperties=fp(20))
    ax.text(0.5, 0.08, "按讚 + 訂閱 JARVIS 選股，每週一掌握三大法人動向！",
            transform=ax.transAxes, ha="center", va="center",
            color=ACCENT, fontproperties=fp(22))

    plt.tight_layout(pad=0)
    arr = _fig_to_array(fig)
    plt.close(fig)
    return arr


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
    """Single vertical slide for YouTube Shorts (1080x1920) — high-impact layout.

    Visual hierarchy: dramatic headline → big arrow + number → 3-metric row → bar chart.
    """
    fig = plt.figure(figsize=(10.8, 19.2), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    # ── Compute derived data from daily ──
    foreign_k = compute_foreign_net_k_fn(summary, daily)
    is_buy = foreign_k >= 0
    val_color = GREEN if is_buy else RED
    abs_k = abs(foreign_k)

    # Consecutive buy/sell streak
    consec = 0
    for d in reversed(daily):
        fn = d.get("foreign", {}).get("net", 0)
        if (is_buy and fn > 0) or (not is_buy and fn < 0):
            consec += 1
        else:
            break

    # Trust & dealer totals
    trust_k = round(sum(d.get("investment_trust", {}).get("net", 0) for d in daily) / 1000)
    dealer_k = round(sum(d.get("dealer", {}).get("net", 0) for d in daily) / 1000)

    # ── Header: channel badge ──
    ax.text(0.5, 0.98, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(24), fontweight="bold")
    ax.axhline(0.962, xmin=0.05, xmax=0.95, color=ACCENT, lw=3)

    # ── Dynamic headline (not boring "三大法人週報") ──
    if symbol == company_name or not symbol.isdigit():
        name_str = company_name
    else:
        name_str = f"{company_name}（{symbol}）"

    if consec >= 3:
        action = "買" if is_buy else "賣"
        headline = f"外資連{consec}天{action}！"
    elif abs_k >= 5000:
        headline = "外資狂掃！" if is_buy else "外資大撤退！"
    else:
        headline = "外資買超" if is_buy else "外資賣超"

    ax.text(0.5, 0.935, name_str,
            transform=ax.transAxes, ha="center", va="center",
            color=TEXT, fontproperties=fp(44), fontweight="bold")
    ax.text(0.5, 0.895, headline,
            transform=ax.transAxes, ha="center", va="center",
            color=val_color, fontproperties=fp(38), fontweight="bold")
    ax.text(0.5, 0.865, date_range, transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(22))

    # ── Hero number with big arrow ──
    arrow = "▲" if is_buy else "▼"
    if abs_k >= 10000:
        num_str = f"{abs_k / 10000:.1f}".rstrip("0").rstrip(".")
        unit_str = "萬張"
    else:
        num_str = f"{abs_k:,}"
        unit_str = "張"

    # Trend indicator (secondary arrow showing momentum direction)
    if len(daily) >= 2:
        last_fn = daily[-1].get("foreign", {}).get("net", 0)
        prev_fn = daily[-2].get("foreign", {}).get("net", 0)
        if last_fn > prev_fn:
            trend_arrow = "↗"
        elif last_fn < prev_fn:
            trend_arrow = "↘"
        else:
            trend_arrow = "→"
    else:
        trend_arrow = ""

    # Giant arrow with glow effect (larger faded arrow behind)
    ax.text(0.5, 0.79, arrow, transform=ax.transAxes,
            ha="center", va="center", color=val_color, fontproperties=fp(90),
            fontweight="bold", alpha=0.15)
    ax.text(0.5, 0.79, arrow, transform=ax.transAxes,
            ha="center", va="center", color=val_color, fontproperties=fp(72),
            fontweight="bold", alpha=0.85)
    # Big number
    ax.text(0.5, 0.715, num_str, transform=ax.transAxes,
            ha="center", va="center", color=val_color, fontproperties=fp(96), fontweight="bold")
    # Unit with trend arrow
    trend_label = f"{unit_str}  {trend_arrow}" if trend_arrow else unit_str
    ax.text(0.5, 0.665, trend_label, transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(30))

    # ── 3-metric summary row (外資 / 投信 / 自營) ──
    metrics = [
        ("外資", foreign_k, ACCENT),
        ("投信", trust_k, GREEN),
        ("自營", dealer_k, BLUE),
    ]
    for i, (label, val, base_color) in enumerate(metrics):
        cx = 0.18 + i * 0.32
        m_color = GREEN if val >= 0 else RED
        sign = "+" if val >= 0 else ""
        m_arrow = "▲" if val >= 0 else "▼"

        # Card background
        rect = plt.Rectangle(
            (cx - 0.12, 0.575), 0.24, 0.07,
            transform=ax.transAxes, clip_on=False,
            facecolor=CARD_BG, edgecolor=base_color, linewidth=2, alpha=0.9,
        )
        ax.add_patch(rect)

        ax.text(cx, 0.63, label, transform=ax.transAxes,
                ha="center", va="center", color=base_color, fontproperties=fp(20))
        ax.text(cx, 0.595, f"{m_arrow}{sign}{val:,}", transform=ax.transAxes,
                ha="center", va="center", color=m_color, fontproperties=fp(22), fontweight="bold")

    # ── Streak badge (if consecutive >= 2) ──
    if consec >= 2:
        action = "連買" if is_buy else "連賣"
        badge_text = f"🔥 {action} {consec} 天"
        badge_color = val_color
        rect_badge = plt.Rectangle(
            (0.28, 0.535), 0.44, 0.03,
            transform=ax.transAxes, clip_on=False,
            facecolor=badge_color, edgecolor="none", alpha=0.2,
        )
        ax.add_patch(rect_badge)
        ax.text(0.5, 0.55, badge_text, transform=ax.transAxes,
                ha="center", va="center", color=badge_color, fontproperties=fp(22), fontweight="bold")

    # ── Daily bar chart ──
    recent = daily[-5:] if len(daily) >= 5 else daily
    dates_short = [d["date"][-5:] for d in recent]
    vals = [round(d.get("foreign", {}).get("net", 0) / 1000) for d in recent]
    colors = [GREEN if v >= 0 else RED for v in vals]

    chart_bottom = 0.14
    ax_bar = fig.add_axes([0.12, chart_bottom, 0.76, 0.36], facecolor=CARD_BG)

    # Shadow bars for depth effect
    shadow_offset = 0.03
    ax_bar.bar([i + shadow_offset for i in range(len(dates_short))], vals,
               color="#000000", width=0.5, alpha=0.2, zorder=2)

    bars = ax_bar.bar(dates_short, vals, color=colors, width=0.5,
                      edgecolor=TEXT, linewidth=1.5, zorder=3)
    ax_bar.axhline(0, color=GRID, lw=1.5, zorder=2)
    ax_bar.set_facecolor(CARD_BG)
    ax_bar.tick_params(axis="x", colors=MUTED, labelsize=22)
    ax_bar.tick_params(axis="y", colors=MUTED, labelsize=16)
    ax_bar.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax_bar.set_title("外資近期買賣超（張）", fontproperties=fp(24), color=MUTED, pad=16)
    for spine in ax_bar.spines.values():
        spine.set_edgecolor(GRID)
    max_abs_val = max((abs(x) for x in vals), default=1)
    y_min, y_max = ax_bar.get_ylim()
    y_margin = (y_max - y_min) * 0.18
    ax_bar.set_ylim(y_min - y_margin, y_max + y_margin)
    for i, v in enumerate(vals):
        if v != 0:
            offset = max_abs_val * 0.06 * (1 if v >= 0 else -1)
            arrow = "↑" if v >= 0 else "↓"
            ax_bar.text(i, v + offset,
                        f"{arrow}{v:+,}", ha="center", va="bottom" if v >= 0 else "top",
                        color=TEXT, fontproperties=fp(18), fontweight="bold", clip_on=True,
                        bbox={"boxstyle": "round,pad=0.12", "facecolor": CARD_BG,
                              "edgecolor": "none", "alpha": 0.7})

    # ── Footer CTA ──
    fig.text(0.5, 0.05, "━" * 30, ha="center", va="center",
             color=ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.03, "按讚＋訂閱 JARVIS 選股｜每天更新",
             ha="center", va="center", color=ACCENT,
             fontproperties=fp(26), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((SHORTS_W, SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)


# ── TDCC Shorts slide (1080x1920 vertical) ────────────────────────────────

def make_tdcc_shorts_slide(
    company_name: str,
    big_holder_change: float,
    retail_change: float,
    big_holder_pct: float,
    retail_pct: float,
) -> np.ndarray:
    """Vertical slide for TDCC (集保戶數) YouTube Shorts (1080x1920).

    Layout: header -> hero big-holder change -> retail change -> bar -> footer.
    """
    fig = plt.figure(figsize=(10.8, 19.2), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    # ── Header ──
    ax.text(0.5, 0.98, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(24), fontweight="bold")
    ax.axhline(0.962, xmin=0.05, xmax=0.95, color=ACCENT, lw=3)
    ax.text(0.5, 0.935, company_name, transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(44), fontweight="bold")
    ax.text(0.5, 0.895, "集保戶數變動分析", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(28))

    # ── Hero: 大戶持股 change ──
    big_arrow = "▲" if big_holder_change >= 0 else "▼"
    big_color = GREEN if big_holder_change >= 0 else RED
    ax.text(0.5, 0.82, "大戶持股", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(32))
    ax.text(0.5, 0.73, f"{big_arrow}{abs(big_holder_change):.1f}%", transform=ax.transAxes,
            ha="center", va="center", color=big_color, fontproperties=fp(96), fontweight="bold")
    ax.text(0.5, 0.685, "（≥400張）", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(22))

    # ── Retail change ──
    retail_arrow = "▲" if retail_change >= 0 else "▼"
    retail_color = RED if retail_change >= 0 else GREEN  # retail increase = bearish
    ax.text(0.5, 0.62, "散戶持股", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(32))
    ax.text(0.5, 0.55, f"{retail_arrow}{abs(retail_change):.1f}%", transform=ax.transAxes,
            ha="center", va="center", color=retail_color, fontproperties=fp(72), fontweight="bold")
    ax.text(0.5, 0.515, "（≤10張）", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(22))

    # ── Horizontal proportion bar (大戶 vs 散戶) ──
    bar_y = 0.42
    bar_h = 0.04
    bar_left = 0.1
    bar_width = 0.8
    total_pct = big_holder_pct + retail_pct
    if total_pct > 0:
        big_ratio = big_holder_pct / total_pct
    else:
        big_ratio = 0.5

    # Big holder portion (green)
    rect_big = plt.Rectangle(
        (bar_left, bar_y), bar_width * big_ratio, bar_h,
        transform=ax.transAxes, clip_on=False,
        facecolor=GREEN, edgecolor="none", alpha=0.85,
    )
    ax.add_patch(rect_big)
    # Retail portion (red)
    rect_retail = plt.Rectangle(
        (bar_left + bar_width * big_ratio, bar_y), bar_width * (1 - big_ratio), bar_h,
        transform=ax.transAxes, clip_on=False,
        facecolor=RED, edgecolor="none", alpha=0.85,
    )
    ax.add_patch(rect_retail)

    # Labels on bar
    ax.text(bar_left + bar_width * big_ratio * 0.5, bar_y - 0.025,
            f"大戶 {big_holder_pct:.1f}%", transform=ax.transAxes,
            ha="center", va="center", color=GREEN, fontproperties=fp(20), fontweight="bold")
    ax.text(bar_left + bar_width * big_ratio + bar_width * (1 - big_ratio) * 0.5, bar_y - 0.025,
            f"散戶 {retail_pct:.1f}%", transform=ax.transAxes,
            ha="center", va="center", color=RED, fontproperties=fp(20), fontweight="bold")

    # ── Interpretation text ──
    if big_holder_change > 0:
        interp = "大戶加碼中，籌碼趨於集中"
        interp_color = GREEN
    elif big_holder_change < 0:
        interp = "大戶減碼中，籌碼趨於分散"
        interp_color = RED
    else:
        interp = "籌碼結構持平"
        interp_color = MUTED
    ax.text(0.5, 0.34, interp, transform=ax.transAxes,
            ha="center", va="center", color=interp_color, fontproperties=fp(28), fontweight="bold")

    # ── Footer CTA ──
    fig.text(0.5, 0.05, "━" * 30, ha="center", va="center",
             color=ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.03, "按讚＋訂閱 JARVIS 選股｜每天更新",
             ha="center", va="center", color=ACCENT,
             fontproperties=fp(26), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((SHORTS_W, SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)


# ── Rotation Shorts slide (1080x1920 vertical) ────────────────────────────

def make_rotation_shorts_slide(
    sell_name: str,
    sell_lots: int,
    buy_name: str,
    buy_lots: int,
) -> np.ndarray:
    """Vertical slide for institutional rotation (法人換股) YouTube Shorts (1080x1920).

    Layout: header -> two columns (sell | arrow | buy) -> footer.
    """
    fig = plt.figure(figsize=(10.8, 19.2), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    # ── Header ──
    ax.text(0.5, 0.98, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(24), fontweight="bold")
    ax.axhline(0.962, xmin=0.05, xmax=0.95, color=ACCENT, lw=3)
    ax.text(0.5, 0.935, "外資換股追蹤", transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(44), fontweight="bold")

    # ── Left column: 減碼 (sell) ──
    left_cx = 0.25
    # Card background
    rect_sell = plt.Rectangle(
        (left_cx - 0.18, 0.55), 0.36, 0.32,
        transform=ax.transAxes, clip_on=False,
        facecolor=CARD_BG, edgecolor=RED, linewidth=3, alpha=0.9,
    )
    ax.add_patch(rect_sell)

    ax.text(left_cx, 0.83, "▼", transform=ax.transAxes,
            ha="center", va="center", color=RED, fontproperties=fp(60), fontweight="bold")
    ax.text(left_cx, 0.76, "減碼", transform=ax.transAxes,
            ha="center", va="center", color=RED, fontproperties=fp(32), fontweight="bold")
    ax.text(left_cx, 0.69, sell_name, transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(40), fontweight="bold")
    sell_lots_str = f"{abs(sell_lots):,} 張"
    ax.text(left_cx, 0.61, sell_lots_str, transform=ax.transAxes,
            ha="center", va="center", color=RED, fontproperties=fp(28))

    # ── Center arrow ──
    ax.text(0.5, 0.71, "→", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(72), fontweight="bold")

    # ── Right column: 加碼 (buy) ──
    right_cx = 0.75
    rect_buy = plt.Rectangle(
        (right_cx - 0.18, 0.55), 0.36, 0.32,
        transform=ax.transAxes, clip_on=False,
        facecolor=CARD_BG, edgecolor=GREEN, linewidth=3, alpha=0.9,
    )
    ax.add_patch(rect_buy)

    ax.text(right_cx, 0.83, "▲", transform=ax.transAxes,
            ha="center", va="center", color=GREEN, fontproperties=fp(60), fontweight="bold")
    ax.text(right_cx, 0.76, "加碼", transform=ax.transAxes,
            ha="center", va="center", color=GREEN, fontproperties=fp(32), fontweight="bold")
    ax.text(right_cx, 0.69, buy_name, transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(40), fontweight="bold")
    buy_lots_str = f"{abs(buy_lots):,} 張"
    ax.text(right_cx, 0.61, buy_lots_str, transform=ax.transAxes,
            ha="center", va="center", color=GREEN, fontproperties=fp(28))

    # ── Subtitle ──
    ax.text(0.5, 0.48, "外資資金流向追蹤", transform=ax.transAxes,
            ha="center", va="center", color=MUTED, fontproperties=fp(26))

    # ── Disclaimer ──
    ax.text(0.5, 0.38, "以上資訊僅供參考，不構成任何投資建議",
            transform=ax.transAxes, ha="center", va="center",
            color=MUTED, fontproperties=fp(20))

    # ── Footer CTA ──
    fig.text(0.5, 0.05, "━" * 30, ha="center", va="center",
             color=ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.03, "按讚＋訂閱 JARVIS 選股｜每天更新",
             ha="center", va="center", color=ACCENT,
             fontproperties=fp(26), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((SHORTS_W, SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)


# ── Google Trends slide ─────────────────────────────────────────────────────


def make_trends_shorts_slide(
    trending_stocks: list[dict],
) -> np.ndarray:
    """Vertical slide for Google Trends hot stocks (1080x1920).

    Each item in *trending_stocks* should have:
        symbol, name, pct_change, foreign_net_k, signal ("contrarian"|"aligned")
    """
    fig = plt.figure(figsize=(10.8, 19.2), facecolor=BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(BG)
    ax.axis("off")

    # ── Header ──
    ax.text(0.5, 0.98, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=ACCENT, fontproperties=fp(24), fontweight="bold")
    ax.axhline(0.962, xmin=0.05, xmax=0.95, color=ACCENT, lw=3)
    ax.text(0.5, 0.935, "Google 熱搜股 vs 法人動向", transform=ax.transAxes,
            ha="center", va="center", color=TEXT, fontproperties=fp(40), fontweight="bold")

    # ── Stock rows ──
    n = min(len(trending_stocks), 5)
    row_h = 0.12
    start_y = 0.85

    contrarian_count = 0
    for i, stock in enumerate(trending_stocks[:n]):
        y = start_y - i * (row_h + 0.02)
        signal = stock.get("signal", "aligned")
        is_contrarian = signal == "contrarian"
        if is_contrarian:
            contrarian_count += 1
        border_color = RED if is_contrarian else GREEN

        # Card background
        rect = plt.Rectangle(
            (0.05, y - row_h / 2), 0.90, row_h,
            transform=ax.transAxes, clip_on=False,
            facecolor=CARD_BG, edgecolor=border_color, linewidth=2.5, alpha=0.9,
        )
        ax.add_patch(rect)

        # Left: name + ticker
        ax.text(0.10, y + 0.02, stock["name"], transform=ax.transAxes,
                ha="left", va="center", color=TEXT, fontproperties=fp(32), fontweight="bold")
        ax.text(0.10, y - 0.03, stock["symbol"], transform=ax.transAxes,
                ha="left", va="center", color=MUTED, fontproperties=fp(20))

        # Center: search volume change
        pct = stock.get("pct_change", 0)
        pct_text = f"+{pct:.0f}%" if pct > 0 else f"{pct:.0f}%"
        ax.text(0.50, y, pct_text, transform=ax.transAxes,
                ha="center", va="center", color=ACCENT, fontproperties=fp(36), fontweight="bold")
        ax.text(0.50, y - 0.035, "搜尋量", transform=ax.transAxes,
                ha="center", va="center", color=MUTED, fontproperties=fp(16))

        # Right: foreign net
        fnet = stock.get("foreign_net_k", 0)
        arrow = "▲" if fnet >= 0 else "▼"
        arrow_color = GREEN if fnet >= 0 else RED
        ax.text(0.80, y + 0.01, f"{arrow} {abs(fnet):,} 千張", transform=ax.transAxes,
                ha="center", va="center", color=arrow_color, fontproperties=fp(26), fontweight="bold")
        ax.text(0.80, y - 0.03, "外資", transform=ax.transAxes,
                ha="center", va="center", color=MUTED, fontproperties=fp(16))

        # Contrarian badge
        if is_contrarian:
            ax.text(0.93, y + 0.03, "反向", transform=ax.transAxes,
                    ha="center", va="center", color=RED, fontproperties=fp(16),
                    fontweight="bold", bbox={"boxstyle": "round,pad=0.2",
                    "facecolor": RED, "edgecolor": "none", "alpha": 0.2})

    # ── Interpretation ──
    interp_y = start_y - n * (row_h + 0.02) - 0.02
    if contrarian_count > 0:
        interp_text = f"{contrarian_count} 檔熱搜股遭法人反向操作"
        interp_color = RED
    else:
        interp_text = "法人與散戶方向一致"
        interp_color = GREEN
    ax.text(0.5, interp_y, interp_text, transform=ax.transAxes,
            ha="center", va="center", color=interp_color, fontproperties=fp(28), fontweight="bold")

    # ── Disclaimer ──
    ax.text(0.5, 0.12, "以上資訊僅供參考，不構成任何投資建議",
            transform=ax.transAxes, ha="center", va="center",
            color=MUTED, fontproperties=fp(20))

    # ── Footer CTA ──
    fig.text(0.5, 0.05, "━" * 30, ha="center", va="center",
             color=ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.03, "按讚＋訂閱 JARVIS 選股｜每天更新",
             ha="center", va="center", color=ACCENT,
             fontproperties=fp(26), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((SHORTS_W, SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)
