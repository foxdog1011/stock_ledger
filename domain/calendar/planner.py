"""Auto-planning algorithm — selects stocks/sectors for the weekly content calendar.

Signals used:
  - abs_volume:  sum(abs(total_net)) → most actively traded by institutions
  - momentum:    sum(total_net)      → strongest net buying
  - reversal:    abs(day[-1] - mean) → sudden single-day spike
  - trust_surge: max(abs(投信 net))  → investment trust anomaly

Weekly template (optimized for algorithm growth):
  Tue 12:00: 個股深度分析  — momentum top stock
  Fri 12:00: 三大法人週報  — abs_volume top stock + weekly review
  Daily 08:00 Short: 盤前快報  — previous day's top foreign mover
  Daily 14:30 Short: 盤後速報  — today's anomaly / secondary mover
  Breaking:   — extra episodes when extreme anomalies detected (max 2/week)

Target: 10 Shorts/week + 2 long-form/week = 12 uploads/week
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default universe when portfolio is empty
_DEFAULT_SYMBOLS = [
    "2330", "2317", "2454", "2382", "2308", "2881", "2882", "2886",
    "2891", "2884", "3008", "2412", "2303", "3034", "3711",
]

_SECTOR_DEFINITIONS: dict[str, list[str]] = {
    "散熱":   ["2230", "3017", "6245", "8016", "3520", "2243"],
    "AI伺服器": ["2382", "3231", "6669", "5274", "6414"],
    "台積電供應鏈": ["2330", "3711", "2454", "2308", "3034"],
    "金融": ["2881", "2882", "2886", "2891", "2884"],
    "鋼鐵": ["2002", "2006", "2007", "2008"],
    "電動車": ["2308", "1515", "2207", "6116"],
    "記憶體": ["4256", "3443", "2408"],
}

# Anomaly thresholds for breaking episodes
_REVERSAL_THRESHOLD = int(os.environ.get("REVERSAL_THRESHOLD", "10000"))
_TRUST_SURGE_THRESHOLD = int(os.environ.get("TRUST_SURGE_THRESHOLD", "5000"))
_MAX_BREAKING_PER_WEEK = 1


def _fetch_chip(symbol: str, days: int = 10) -> dict | None:
    """Fetch chip range data from local API."""
    end   = date.today().isoformat()
    start = (date.today() - timedelta(days=days + 10)).isoformat()
    url   = f"http://localhost:8000/api/chip/{symbol}/range?start={start}&end={end}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=15,
        ) as resp:
            return json.loads(resp.read())
    except Exception:
        logger.debug("Chip fetch failed for %s", symbol)
        return None


def _score_symbols(symbols: list[str]) -> list[dict]:
    """Fetch chip data and compute ranking signals for each symbol."""
    scored: list[dict] = []
    for sym in symbols:
        chip = _fetch_chip(sym)
        if not chip or not chip.get("daily"):
            continue
        daily = chip["daily"]

        totals = [d.get("total_net", 0) for d in daily]
        foreign = [d.get("foreign", {}).get("net", 0) for d in daily]
        trust  = [d.get("investment_trust", {}).get("net", 0) for d in daily]

        abs_volume = sum(abs(t) for t in totals)
        momentum   = sum(totals)
        mean_total = sum(totals[:-1]) / max(1, len(totals) - 1) if len(totals) > 1 else 0
        reversal   = abs(totals[-1] - mean_total) if totals else 0
        trust_surge = max(abs(t) for t in trust) if trust else 0

        scored.append({
            "symbol": sym,
            "abs_volume": abs_volume,
            "momentum": momentum,
            "reversal": reversal,
            "trust_surge": trust_surge,
            "foreign_net": sum(foreign),
            "daily": daily,
        })

    return scored


def _pick_top(scored: list[dict], key: str, exclude: set[str]) -> dict | None:
    candidates = [s for s in scored if s["symbol"] not in exclude]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x.get(key, 0))


def _score_sectors(sectors: dict[str, list[str]]) -> list[dict]:
    """For each sector, sum foreign net across member symbols."""
    results = []
    for name, members in sectors.items():
        total_foreign = 0
        valid = 0
        for sym in members:
            chip = _fetch_chip(sym, days=7)
            if not chip or not chip.get("daily"):
                continue
            total_foreign += sum(d.get("foreign", {}).get("net", 0) for d in chip["daily"])
            valid += 1
        if valid > 0:
            results.append({
                "sector_name": name,
                "symbols": members,
                "foreign_net": total_foreign,
                "abs_foreign": abs(total_foreign),
            })
    return results


# ── SEO Title Generation ─────────────────────────────────────────────────────

def _format_lots(n: float) -> str:
    """Format raw share count into 張 display.

    Raw data is in 股 (shares); 1張 = 1000股.
    Display: ≥1萬張 → '2.9 萬', <1萬張 → '3,500'.
    """
    lots = abs(n) / 1000  # 股 → 張
    if lots >= 10000:
        return f"{lots / 10000:.1f} 萬".replace(".0 ", " ")
    return f"{lots:,.0f}"


def _generate_title(template_type: str, symbol: str, data: dict, sector_name: str = "") -> str:
    """Generate SEO-optimized clickbait title from chip data."""
    momentum = data.get("momentum", 0)
    abs_vol = data.get("abs_volume", 0)
    reversal = data.get("reversal", 0)
    trust_surge = data.get("trust_surge", 0)
    foreign_net = data.get("foreign_net", 0)

    if template_type == "abs_volume":
        lots = _format_lots(abs_vol)
        if momentum > 0:
            title = f"法人狂買 {symbol}！成交 {lots} 張 散戶該跟嗎？"
        else:
            title = f"法人砍殺 {symbol} 共 {lots} 張！發生什麼事？"

    elif template_type == "momentum":
        lots = _format_lots(momentum)
        if momentum > 0:
            title = f"法人連買 {symbol} 淨買超 {lots} 張 還能追嗎？"
        else:
            title = f"{symbol} 被法人倒貨 {lots} 張 底部訊號？"

    elif template_type == "reversal":
        lots = _format_lots(reversal)
        title = f"突發！{symbol} 單日爆量 {lots} 張 反轉訊號來了？"

    elif template_type == "trust_surge":
        lots = _format_lots(trust_surge)
        title = f"投信狂掃 {symbol} {lots} 張！跟著投信買？"

    elif template_type == "sector":
        lots = _format_lots(foreign_net)
        if foreign_net > 0:
            title = f"{sector_name}族群外資大舉進場！買超 {lots} 張"
        else:
            title = f"外資撤離{sector_name}！{lots} 張大逃殺"

    elif template_type == "breaking":
        lots = _format_lots(max(reversal, trust_surge))
        title = f"🚨 {symbol} 異常訊號！法人單日爆量 {lots} 張"

    elif template_type == "shorts":
        f_lots = _format_lots(foreign_net)
        if foreign_net > 0:
            title = f"{symbol} 外資買超 {f_lots} 張！30秒看懂"
        elif foreign_net < 0:
            title = f"{symbol} 外資賣超 {f_lots} 張！30秒看懂"
        else:
            lots = _format_lots(abs_vol)
            title = f"{symbol} 法人成交 {lots} 張！30秒看懂"

    else:
        title = f"{symbol} 三大法人籌碼分析"

    # YouTube title limit ~100 chars, keep under 60 for best CTR
    if len(title) > 60:
        title = title[:57] + "..."
    return title


# ── Anomaly Detection ────────────────────────────────────────────────────────

def _detect_anomalies(scored: list[dict]) -> list[dict]:
    """Return symbols with extreme reversal or trust_surge signals."""
    anomalies: list[dict] = []
    for s in scored:
        signals: list[str] = []
        if s.get("reversal", 0) >= _REVERSAL_THRESHOLD:
            signals.append(f"reversal:{s['reversal']:,.0f}")
        if s.get("trust_surge", 0) >= _TRUST_SURGE_THRESHOLD:
            signals.append(f"trust_surge:{s['trust_surge']:,.0f}")
        if signals:
            anomalies.append({**s, "anomaly_signals": signals})
    anomalies.sort(
        key=lambda x: x.get("reversal", 0) + x.get("trust_surge", 0),
        reverse=True,
    )
    return anomalies


# ── Main Planner ─────────────────────────────────────────────────────────────

def plan_week(
    db_path: Path,
    week_start: date,
    portfolio_symbols: list[str] | None = None,
    sectors: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Auto-plan a week of content. Returns list of created episodes.

    Respects existing manual entries — never overwrites them.
    """
    from .repository import insert_episode, list_episodes

    symbols = portfolio_symbols or _DEFAULT_SYMBOLS
    sector_defs = sectors or _SECTOR_DEFINITIONS

    # Check what's already manually planned for this week
    week_end = week_start + timedelta(days=6)
    existing = list_episodes(
        db_path,
        start=week_start.isoformat(),
        end=week_end.isoformat(),
    )
    existing_keys: set[tuple[str, str]] = {
        (e["scheduled_date"], e["content_type"]) for e in existing
        if e["source"] == "manual"
    }

    logger.info("Planning week %s — scoring %d symbols", week_start, len(symbols))
    scored = _score_symbols(symbols)
    if not scored:
        logger.warning("No chip data available — cannot auto-plan")
        return []

    used: set[str] = set()
    episodes: list[dict] = []

    def _add(dt: date, ctype: str, episode: dict) -> None:
        key = (dt.isoformat(), ctype)
        if key in existing_keys:
            logger.info("Skipping %s %s — manual entry exists", dt, ctype)
            return
        episode.update({
            "scheduled_date": dt.isoformat(),
            "content_type": ctype,
            "source": "auto",
            "status": "planned",
        })
        episodes.append(insert_episode(db_path, episode))

    # ── Tuesday 12:00: 個股深度分析 (strongest momentum) ──
    tue = week_start + timedelta(days=1)
    pick = _pick_top(scored, "momentum", used)
    if pick:
        used.add(pick["symbol"])
        _add(tue, "single", {
            "title": _generate_title("momentum", pick["symbol"], pick),
            "symbol": pick["symbol"],
            "priority": 10,
            "pick_reason": f"三大法人淨買超動能最強 ({pick['momentum']:,.0f})",
            "metadata": {"publish_time": "12:00"},
        })

    # ── Breaking episodes: extreme anomalies (schedule mid-week) ──
    wed = week_start + timedelta(days=2)
    anomalies = _detect_anomalies(scored)
    breaking_count = 0
    for anom in anomalies:
        if anom["symbol"] in used:
            continue
        if breaking_count >= _MAX_BREAKING_PER_WEEK:
            break
        breaking_day = wed + timedelta(days=breaking_count)
        if breaking_day.weekday() > 4:
            break
        used.add(anom["symbol"])
        _add(breaking_day, "single", {
            "title": _generate_title("breaking", anom["symbol"], anom),
            "symbol": anom["symbol"],
            "priority": 15,
            "pick_reason": f"異常訊號：{', '.join(anom['anomaly_signals'])}",
            "metadata": {"breaking": True, "publish_time": "12:00"},
        })
        breaking_count += 1
        logger.info("Breaking episode: %s — %s", anom["symbol"], anom["anomaly_signals"])

    # ── Friday 12:00: 三大法人週報 + 週回顧 ──
    fri = week_start + timedelta(days=4)
    pick = _pick_top(scored, "abs_volume", used)
    if pick:
        used.add(pick["symbol"])

    week_picks = [ep for ep in episodes if ep.get("content_type") == "single" and ep.get("symbol")]
    week_symbols = [ep["symbol"] for ep in week_picks]
    if pick:
        week_symbols.append(pick["symbol"])
    pick_summary = "、".join(week_symbols) if week_symbols else "本週精選"

    review_title = f"本週選股回顧｜{pick_summary} 表現如何？該續抱還是停損？"
    if len(review_title) > 60:
        review_title = f"本週 {len(week_symbols)} 檔選股回顧｜該續抱還是停損？"

    _add(fri, "macro", {
        "title": review_title,
        "symbol": pick["symbol"] if pick else "0050",
        "symbols": week_symbols,
        "priority": 10,
        "pick_reason": f"每週五固定回顧：{', '.join(week_symbols)}",
        "metadata": {"weekly_review": True, "reviewed_symbols": week_symbols,
                     "publish_time": "12:00"},
    })

    # ── Daily Shorts x2 (Mon–Fri): 08:00 盤前 + 14:30 盤後 ──
    by_abs = sorted(scored, key=lambda s: s["abs_volume"], reverse=True)
    for i in range(5):  # Mon-Fri
        dt = week_start + timedelta(days=i)

        # 08:00 盤前快報 — rotate through top movers
        idx_am = (i * 2) % len(by_abs)
        sym_am = by_abs[idx_am]["symbol"]
        _add(dt, "shorts", {
            "title": _generate_title("shorts", sym_am, by_abs[idx_am]),
            "symbol": sym_am,
            "priority": 6,
            "pick_reason": "盤前快報 08:00",
            "metadata": {"format": "shorts", "days": 3,
                         "publish_time": "08:00", "slot": "morning"},
        })

        # 14:30 盤後速報 — secondary mover
        idx_pm = (i * 2 + 1) % len(by_abs)
        sym_pm = by_abs[idx_pm]["symbol"]
        _add(dt, "shorts", {
            "title": _generate_title("shorts", sym_pm, by_abs[idx_pm]),
            "symbol": sym_pm,
            "priority": 5,
            "pick_reason": "盤後速報 14:30",
            "metadata": {"format": "shorts", "days": 3,
                         "publish_time": "14:30", "slot": "afternoon"},
        })

    logger.info("Auto-planned %d episodes for week %s", len(episodes), week_start)
    return episodes
