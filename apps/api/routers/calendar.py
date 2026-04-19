"""Content calendar router — plan, manage, and auto-produce YouTube episodes.

Key endpoints:
  POST /calendar/plan-week  — auto-fill a week based on chip data signals
  POST /calendar/next       — pick next pending episode, generate video, upload to YouTube
  GET  /calendar            — list episodes (filter by date, status, type)
  CRUD on individual episodes
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

_DB_PATH = Path(os.environ.get("DB_PATH", "/data/ledger.db"))


# ── Request models ────────────────────────────────────────────────────────────

class EpisodeCreate(BaseModel):
    scheduled_date: str
    content_type: str          # single | sector | macro | shorts
    title: str = ""
    symbol: str | None = None
    sector_name: str | None = None
    symbols: list[str] = []
    priority: int = 0
    metadata: dict = {}


class EpisodeUpdate(BaseModel):
    scheduled_date: str | None = None
    content_type: str | None = None
    title: str | None = None
    symbol: str | None = None
    sector_name: str | None = None
    symbols: list[str] | None = None
    status: str | None = None
    priority: int | None = None
    metadata: dict | None = None


class PlanWeekRequest(BaseModel):
    week_start: str            # YYYY-MM-DD (must be a Monday)
    force_replan: bool = False
    symbols: list[str] = []    # override universe (empty = use defaults)


class NextRequest(BaseModel):
    dry_run: bool = False
    privacy: str = "public"


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/calendar", summary="List episodes")
def list_calendar(
    start: str | None = Query(None),
    end: str | None = Query(None),
    status: str | None = Query(None),
    content_type: str | None = Query(None),
):
    from domain.calendar.repository import list_episodes
    return list_episodes(_DB_PATH, start=start, end=end, status=status, content_type=content_type)


@router.get("/calendar/{episode_id}", summary="Get episode")
def get_episode(episode_id: int):
    from domain.calendar.repository import get_episode as _get
    ep = _get(_DB_PATH, episode_id)
    if not ep:
        raise HTTPException(404, "Episode not found")
    return ep


@router.post("/calendar", summary="Create episode (manual)")
def create_episode(body: EpisodeCreate):
    from domain.calendar.repository import insert_episode
    data = body.model_dump()
    data["source"] = "manual"
    return insert_episode(_DB_PATH, data)


@router.put("/calendar/{episode_id}", summary="Update episode")
def update_episode(episode_id: int, body: EpisodeUpdate):
    from domain.calendar.repository import update_episode as _update
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    result = _update(_DB_PATH, episode_id, updates)
    if not result:
        raise HTTPException(404, "Episode not found")
    return result


@router.delete("/calendar/{episode_id}", summary="Delete episode")
def delete_calendar_episode(episode_id: int):
    from domain.calendar.repository import delete_episode
    if not delete_episode(_DB_PATH, episode_id):
        raise HTTPException(404, "Episode not found")
    return {"deleted": True}


# ── Auto-plan ─────────────────────────────────────────────────────────────────

@router.post("/calendar/plan-week", summary="Auto-plan a week of content")
def plan_week(body: PlanWeekRequest):
    from domain.calendar.planner import plan_week as _plan
    from domain.calendar.repository import clear_auto_episodes

    try:
        ws = date.fromisoformat(body.week_start)
    except ValueError:
        raise HTTPException(400, "week_start must be YYYY-MM-DD")

    if ws.weekday() != 0:
        raise HTTPException(400, "week_start must be a Monday")

    we = ws + timedelta(days=6)
    if body.force_replan:
        cleared = clear_auto_episodes(_DB_PATH, ws.isoformat(), we.isoformat())
        logger.info("Cleared %d auto episodes for replan", cleared)

    episodes = _plan(
        _DB_PATH,
        ws,
        portfolio_symbols=body.symbols or None,
    )
    return {
        "week": body.week_start,
        "episodes_created": len(episodes),
        "episodes": episodes,
    }


# ── The main orchestration endpoint ──────────────────────────────────────────

@router.post("/calendar/next", summary="Produce next pending episode")
def produce_next(body: NextRequest):
    """Find the next pending episode, generate video, upload to YouTube.

    This is the single endpoint that n8n calls on a schedule.
    Returns the episode with status updated and YouTube URL.
    """
    from domain.calendar.repository import get_next_pending, mark_status

    episode = get_next_pending(_DB_PATH)
    if not episode:
        return {"status": "idle", "message": "No pending episodes"}

    ep_id = episode["id"]
    is_retry = episode.get("status") == "failed"
    retry_count = episode.get("retry_count", 0)
    if is_retry:
        logger.info("Retrying episode #%d (attempt %d): %s", ep_id, retry_count + 1, episode["title"])
    else:
        logger.info("Producing episode #%d: %s (%s)", ep_id, episode["title"], episode["content_type"])

    if body.dry_run:
        return {"status": "dry_run", "episode": episode}

    # Mark generating
    mark_status(_DB_PATH, ep_id, "generating")

    # ── Step 1: Generate script via OpenAI ────────────────────────────────
    script = _generate_script(episode)

    # ── Step 2: Generate video ────────────────────────────────────────────
    try:
        video_path = _generate_video(episode, script)
        mark_status(_DB_PATH, ep_id, "generated", video_path=video_path)
    except Exception as exc:
        mark_status(_DB_PATH, ep_id, "failed", error_message=f"Video gen: {exc}")
        logger.exception("Video generation failed for episode #%d", ep_id)
        return {"status": "failed", "episode_id": ep_id, "error": str(exc)}

    # ── Step 3: Generate thumbnail ────────────────────────────────────────
    thumb_path = _generate_thumbnail(episode)

    # ── Step 4: Upload to YouTube ─────────────────────────────────────────
    try:
        publish_at = _compute_publish_at(episode)
        yt_result = _upload_youtube(episode, video_path, thumb_path, body.privacy, script, publish_at)
        mark_status(
            _DB_PATH, ep_id, "uploaded",
            youtube_id=yt_result["video_id"],
            youtube_url=yt_result["url"],
        )
        logger.info("Episode #%d uploaded: %s", ep_id, yt_result["url"])
    except Exception as exc:
        mark_status(_DB_PATH, ep_id, "failed", error_message=f"Upload: {exc}")
        logger.exception("YouTube upload failed for episode #%d", ep_id)
        return {
            "status": "video_generated",
            "episode_id": ep_id,
            "video_path": video_path,
            "error": str(exc),
        }
    finally:
        # Cleanup temp files
        Path(video_path).unlink(missing_ok=True)
        if thumb_path:
            Path(thumb_path).unlink(missing_ok=True)

    return {
        "status": "uploaded",
        "episode_id": ep_id,
        "title": episode["title"],
        "content_type": episode["content_type"],
        "youtube_url": yt_result["url"],
        "youtube_id": yt_result["video_id"],
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _generate_script(episode: dict) -> str:
    """Call OpenAI to generate a video script based on the episode."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        logger.warning("No OPENAI_API_KEY — returning empty script")
        return ""

    ctype = episode["content_type"]
    symbol = episode.get("symbol", "")
    sector = episode.get("sector_name", "")
    title  = episode.get("title", "")
    reason = episode.get("pick_reason", "")
    meta   = episode.get("metadata", {})
    is_shorts = meta.get("format") == "shorts"

    if ctype == "sector":
        subject = f"{sector}（{', '.join(episode.get('symbols', [])[:5])}）"
    elif meta.get("weekly_review"):
        reviewed = meta.get("reviewed_symbols", [])
        subject = f"本週選股回顧：{', '.join(reviewed)}"
    elif ctype == "macro":
        subject = "本週台股大盤"
    else:
        subject = symbol

    duration = "60秒 YouTube Shorts" if is_shorts else "4-5分鐘 YouTube"
    if is_shorts:
        structure = (
            "1. 開場（10秒衝擊性數字）\n"
            "2. 核心結論（30秒）\n"
            "3. 一句話建議\n"
            "4. CTA（訂閱+留言）\n\n"
            "語氣：快速直接。"
        )
    elif meta.get("breaking"):
        structure = (
            "1. 突發新聞開場（10秒，用數據衝擊觀眾）\n"
            "2. 異常訊號解讀（為什麼法人突然大量進出）\n"
            "3. 歷史類似情況對比\n"
            "4. 散戶應對策略\n"
            "5. CTA（訂閱+開啟小鈴鐺）\n\n"
            "語氣：緊迫但理性，像財經快報。"
        )
    elif meta.get("weekly_review"):
        structure = (
            "1. 開場（本週選股成績單）\n"
            "2. 逐一回顧每檔表現（股價變化 + 法人動向）\n"
            "3. 命中率統計\n"
            "4. 下週展望\n"
            "5. CTA（訂閱+留言你最想看哪檔）\n\n"
            "語氣：復盤檢討風格，誠實面對對錯。"
        )
    else:
        structure = (
            "1. 開場 Hook（前15秒讓人想繼續看）\n"
            "2. 籌碼重點解讀\n"
            "3. 市場訊號解讀\n"
            "4. 對散戶的操作建議（具體但不構成投資建議）\n"
            "5. 結尾 CTA（訂閱+留言）\n\n"
            "語氣：像朋友在聊天，有觀點、有數據。"
        )

    prompt = (
        f"你是台股 YouTube 頻道「JARVIS 選股」的主持人，用 AI 工具分析台股籌碼。\n\n"
        f"本集主題：{title}\n"
        f"分析標的：{subject}\n"
        f"選題原因：{reason}\n\n"
        f"請寫一支 {duration} 影片腳本：\n"
        f"{structure}\n\n"
        f"不要加任何小標題或段落標號，直接寫口語化的台詞。"
    )

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1500 if is_shorts else 2000,
    }).encode()

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception:
        logger.exception("Script generation failed")
        return ""


def _generate_video(episode: dict, script: str) -> str:
    """Call the local video generation endpoint. Returns temp file path."""
    meta = episode.get("metadata", {})
    payload = {
        "symbol": episode.get("symbol") or "0050",
        "script": script,
        "days": meta.get("days", 7),
        "format": meta.get("format", "landscape"),
        "sector_name": episode.get("sector_name") or "",
        "symbols": episode.get("symbols") or [],
    }

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp.close()

    req = urllib.request.Request(
        "http://localhost:8000/api/video/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        Path(tmp.name).write_bytes(resp.read())

    return tmp.name


def _generate_thumbnail(episode: dict) -> str | None:
    """Fetch thumbnail PNG from API. Returns temp file path or None."""
    if episode.get("metadata", {}).get("format") == "shorts":
        return None

    symbol = episode.get("symbol", "0050")
    days   = episode.get("metadata", {}).get("days", 7)
    url    = f"http://localhost:8000/api/video/thumbnail?symbol={symbol}&days={days}"

    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=tempfile.gettempdir())
            tmp.write(resp.read())
            tmp.close()
            return tmp.name
    except Exception:
        logger.exception("Thumbnail generation failed")
        return None


def _fetch_chip_summary(symbol: str, days: int = 7) -> dict:
    """Fetch chip data for title generation. Returns {foreign_net, trust_net, daily}.

    Fetches extra calendar days to account for weekends/holidays, then trims
    to the last *days* trading days so the numbers match the weekly scope.
    """
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days + 10)).isoformat()
    url = f"http://localhost:8000/api/chip/{symbol}/range?start={start}&end={end}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=20,
        ) as resp:
            data = json.loads(resp.read())
    except Exception:
        logger.warning("Could not fetch chip data for title generation")
        return {}

    daily = data.get("daily", data) if isinstance(data, dict) else data
    if not isinstance(daily, list) or not daily:
        return {}

    # Keep only the last N trading days to match the requested scope
    daily = daily[-days:]

    foreign_net = sum(d.get("foreign", {}).get("net", 0) for d in daily)
    trust_net = sum(d.get("investment_trust", {}).get("net", 0) for d in daily)

    # Count consecutive foreign buy/sell days (from most recent)
    consec_buy, consec_sell = 0, 0
    for d in reversed(daily):
        fn = d.get("foreign", {}).get("net", 0)
        if fn > 0:
            consec_buy += 1
        else:
            break
    for d in reversed(daily):
        fn = d.get("foreign", {}).get("net", 0)
        if fn < 0:
            consec_sell += 1
        else:
            break

    return {
        "foreign_net": foreign_net,
        "foreign_net_k": round(foreign_net / 1000),
        "trust_net": trust_net,
        "trust_net_k": round(trust_net / 1000),
        "consec_buy": consec_buy,
        "consec_sell": consec_sell,
        "daily": daily,
        "date_range": f"{daily[0]['date']} ～ {daily[-1]['date']}",
    }


def _get_company_name_for_title(symbol: str) -> str:
    """Fetch company name via research API, fallback to known tickers."""
    _names = {
        "2330": "台積電", "2317": "鴻海", "2454": "聯發科", "2382": "廣達",
        "2308": "台達電", "2881": "富邦金", "2882": "國泰金", "2886": "兆豐金",
        "2891": "中信金", "2884": "玉山金", "3008": "大立光", "2412": "中華電",
        "2303": "聯電", "2357": "華碩", "2395": "研華", "3711": "日月光投控",
    }
    try:
        url = f"http://localhost:8000/api/research/{symbol}"
        with urllib.request.urlopen(
            urllib.request.Request(url, headers={"Accept": "application/json"}),
            timeout=10,
        ) as resp:
            name = json.loads(resp.read()).get("name", "")
            if name and name != symbol:
                return name
    except Exception:
        pass
    return _names.get(symbol, symbol)


def _fmt_lots(n: int) -> str:
    """Format lot count for titles: 66104 → '6.6 萬', 3500 → '3,500'."""
    abs_n = abs(n)
    if abs_n >= 10000:
        wan = abs_n / 10000
        return f"{wan:.1f} 萬".replace(".0 ", " ")
    return f"{abs_n:,}"


def _build_algo_title(
    episode: dict, chip: dict, company_name: str, is_shorts: bool,
) -> str:
    """Build CTR-optimized title using chip data.

    Formula (long):  [股名] [衝擊性數字+動作] [懸念問句]｜[代號] 籌碼分析
    Formula (short): [股名] [一句話結論]  (hashtags go in description)
    """
    symbol = episode.get("symbol") or ""
    ctype = episode["content_type"]
    meta = episode.get("metadata") or {}
    foreign_k = chip.get("foreign_net_k", 0)
    trust_k = chip.get("trust_net_k", 0)
    consec_buy = chip.get("consec_buy", 0)
    consec_sell = chip.get("consec_sell", 0)
    abs_foreign = abs(foreign_k)
    lots_str = _fmt_lots(foreign_k)

    # Pick the most dramatic angle
    if foreign_k > 0:
        if abs_foreign >= 10000:
            hook = f"外資狂買 {lots_str} 張！"
        elif consec_buy >= 3:
            hook = f"外資連 {consec_buy} 買 累計 {lots_str} 張！"
        else:
            hook = f"外資買超 {lots_str} 張！"
        question = "三大法人都在搶？" if trust_k > 0 else "散戶該跟嗎？"
    else:
        if abs_foreign >= 10000:
            hook = f"外資狂賣 {lots_str} 張！"
        elif consec_sell >= 3:
            hook = f"外資連 {consec_sell} 賣 累計 {lots_str} 張！"
        else:
            hook = f"外資賣超 {lots_str} 張！"
        question = "法人大逃殺什麼訊號？" if trust_k < 0 else "散戶該注意什麼？"

    if ctype == "sector":
        sector = episode.get("sector_name") or ""
        if is_shorts:
            return f"{sector}族群 {hook}30秒看懂"
        return f"{sector}族群 {hook}{question}｜籌碼分析"

    if ctype == "macro":
        if is_shorts:
            return f"台股本週法人動向！30秒掌握｜JARVIS 選股"
        return f"台股週報 本週三大法人怎麼買？大盤籌碼全解析｜JARVIS 選股"

    # single stock (default)
    if is_shorts:
        return f"{company_name} {hook}30秒看懂"

    return f"{company_name} {hook}{question}｜{symbol} 籌碼分析"


def _build_algo_description(
    episode: dict, chip: dict, company_name: str,
    is_shorts: bool, script: str,
) -> str:
    """Build SEO-optimized description with timestamps and keywords."""
    symbol = episode.get("symbol") or ""
    sector = episode.get("sector_name") or ""
    foreign_k = chip.get("foreign_net_k", 0)
    trust_k = chip.get("trust_net_k", 0)
    date_range = chip.get("date_range", "")
    parts: list[str] = []

    subject = f"{company_name}（{symbol}）" if symbol else sector

    if is_shorts:
        parts.append(f"{subject} 三大法人動態速報！")
        parts.append("📊 JARVIS 選股｜每天 60 秒掌握法人籌碼")
        parts.append("")
        parts.append(f"⚠️ 免責聲明：本頻道內容僅供參考，不構成投資建議。")
        parts.append("")
        hashtags = ["#台股", "#三大法人", "#Shorts", "#籌碼分析", "#外資", "#投信"]
        if symbol:
            hashtags.insert(1, f"#{company_name}")
            hashtags.insert(2, f"#{symbol}")
        if sector:
            hashtags.insert(1, f"#{sector}")
        parts.append(" ".join(hashtags))
        return "\n".join(parts)

    # Long-form description
    parts.append(f"🔍 {subject} 本週三大法人籌碼完整解析！")
    parts.append("")

    # Key metrics summary
    parts.append("📊 本集重點：")
    action = "買超" if foreign_k >= 0 else "賣超"
    parts.append(f"• 外資本週淨{action} {_fmt_lots(foreign_k)} 張")
    trust_action = "買超" if trust_k >= 0 else "賣超"
    parts.append(f"• 投信本週淨{trust_action} {_fmt_lots(trust_k)} 張")
    if date_range:
        parts.append(f"• 資料區間：{date_range}")
    parts.append("")

    # Timestamps
    if script:
        parts.append("⏱ 時間戳：")
        parts.append("00:00 開場｜本週發生什麼事？")
        parts.append("00:30 外資籌碼解讀")
        parts.append("01:30 投信＋自營動向")
        parts.append("02:30 綜合判斷與操作建議")
        parts.append("03:30 總結")
        parts.append("")

    parts.append("📈 JARVIS 選股 — AI 驅動台股籌碼分析")
    parts.append("🔔 訂閱開啟小鈴鐺，每天掌握法人動態！")
    parts.append("")
    parts.append("⚠️ 免責聲明：本頻道內容僅供參考，不構成投資建議。")
    parts.append("投資有風險，請自行評估。")
    parts.append("")

    # SEO keywords block
    kw = []
    if symbol:
        kw.extend([
            f"{symbol} 分析", f"{symbol} 三大法人",
            f"{company_name}可以買嗎", f"{company_name}法人",
        ])
    if sector:
        kw.extend([f"{sector}族群", f"{sector}概念股"])
    kw.extend(["三大法人籌碼分析", "外資買賣超", "投信買賣超", "台股分析"])
    parts.append("🔍 " + "、".join(kw))
    parts.append("")

    hashtags = ["#三大法人", "#籌碼分析", "#台股", "#JARVIS選股", "#外資", "#投信"]
    if symbol:
        hashtags.extend([f"#{symbol}", f"#{company_name}"])
    if sector:
        hashtags.extend([f"#{sector}", f"#{sector}族群"])
    parts.append(" ".join(hashtags))

    return "\n".join(parts)


def _build_algo_tags(episode: dict, company_name: str, is_shorts: bool) -> list[str]:
    """Build expanded tag list (max 30) targeting search intent."""
    symbol = episode.get("symbol") or ""
    sector = episode.get("sector_name") or ""
    ctype = episode["content_type"]

    tags = ["三大法人", "籌碼分析", "台股", "JARVIS選股", "外資買賣超",
            "投信買賣超", "台股分析", "法人籌碼", "股票分析"]

    if symbol:
        tags.extend([
            symbol, f"{symbol}分析", f"{symbol}可以買嗎",
            company_name, f"{company_name}分析", f"{company_name}法人",
            f"{company_name}外資", f"{company_name}籌碼",
            f"{company_name}股價", f"{company_name}2026",
        ])
    if sector:
        tags.extend([
            sector, f"{sector}族群", f"{sector}概念股", f"{sector}分析",
        ])
    if is_shorts:
        tags.extend(["Shorts", "台股Shorts", "每日快報", "法人動態"])
    if ctype == "macro":
        tags.extend(["台股週報", "大盤分析", "本週回顧", "AI選股"])

    tags.extend(["AI選股", "台股投資"])
    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:30]


def _compute_publish_at(episode: dict) -> str | None:
    """Compute RFC 3339 publishAt from episode metadata.

    If metadata.publish_time is set (e.g. "08:00"), combines it with
    scheduled_date in Asia/Taipei timezone. Returns None if no publish_time.
    """
    meta = episode.get("metadata") or {}
    publish_time = meta.get("publish_time")
    sched_date = episode.get("scheduled_date")
    if not publish_time or not sched_date:
        return None

    try:
        hour, minute = (int(x) for x in publish_time.split(":"))
        dt = date.fromisoformat(sched_date)
        # Asia/Taipei = UTC+8
        taipei_offset = timezone(timedelta(hours=8))
        publish_dt = datetime(dt.year, dt.month, dt.day, hour, minute, 0, tzinfo=taipei_offset)
        return publish_dt.isoformat()
    except (ValueError, TypeError):
        logger.warning("Could not parse publish_time: %s", publish_time)
        return None


def _upload_youtube(
    episode: dict,
    video_path: str,
    thumb_path: str | None,
    privacy: str,
    script: str,
    publish_at: str | None = None,
) -> dict:
    """Upload video to YouTube with algorithm-optimized title/description/tags."""
    from apps.api.routers.youtube_upload import (
        _build_youtube_client, _upload_video, _set_thumbnail,
        _ensure_playlists, _add_to_playlist,
    )

    ctype = episode["content_type"]
    symbol = episode.get("symbol") or ""
    meta = episode.get("metadata") or {}
    is_shorts = meta.get("format") == "shorts"

    # Fetch chip data for dynamic title generation
    chip = _fetch_chip_summary(symbol, days=7) if symbol else {}
    company_name = _get_company_name_for_title(symbol) if symbol else ""

    title = _build_algo_title(episode, chip, company_name, is_shorts)
    description = _build_algo_description(episode, chip, company_name, is_shorts, script)
    tags = _build_algo_tags(episode, company_name, is_shorts)

    logger.info("YouTube title: %s", title)

    yt = _build_youtube_client()
    video_id = _upload_video(yt, video_path, title[:100], description, tags, privacy, publish_at)

    if thumb_path:
        try:
            _set_thumbnail(yt, video_id, thumb_path)
        except Exception:
            logger.exception("Thumbnail set failed for %s", video_id)

    # ── Add to playlist ──
    try:
        playlists = _ensure_playlists(yt)
        if is_shorts and "每日快報" in playlists:
            _add_to_playlist(yt, video_id, playlists["每日快報"])
        elif ctype == "sector" and "族群分析" in playlists:
            _add_to_playlist(yt, video_id, playlists["族群分析"])
        elif ctype == "macro" and "大盤週報" in playlists:
            _add_to_playlist(yt, video_id, playlists["大盤週報"])
        elif ctype == "single" and "個股分析" in playlists:
            _add_to_playlist(yt, video_id, playlists["個股分析"])
    except Exception:
        logger.exception("Playlist assignment failed for %s", video_id)

    return {"video_id": video_id, "url": f"https://www.youtube.com/watch?v={video_id}"}
