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

import json
import logging
import sqlite3
import subprocess
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.background import BackgroundTask

from domain.calendar.planner import _DEFAULT_SYMBOLS, _pick_top

from apps.api.deps import require_api_key as _check_api_key
from apps.api.services.video_engine import (
    SECTOR_SYMBOLS,
    SHORTS_SLOTS,
    SLIDE_SECONDS,
    SLOT_CONFIG,
    build_mp4,
    build_pick_response,
    clean_script_for_tts,
    compute_foreign_net_k,
    get_chip_data,
    get_company_name,
    get_sector_chip,
    make_cumulative_chart,
    make_foreign_chart,
    make_rotation_shorts_slide,
    make_sector_breakdown_chart,
    make_sector_title_slide,
    make_shorts_slide,
    make_stock_summary_slide,
    make_summary_slide,
    make_tdcc_shorts_slide,
    make_trends_shorts_slide,
    make_thumbnail,
    make_title_slide,
    make_trust_dealer_chart,
    make_weekly_review_summary_slide,
    make_weekly_review_title_slide,
    openai_script,
    render_slides_parallel,
    score_symbols_with_fallback,
    tts_edge,
)
from apps.api.services.video_engine.models import (
    CheckMissedResponse,
    CommunityPostRequest,
    CommunityPostResponse,
    GenerateSectorRequest,
    GenerateSectorResponse,
    N8nGenerateRequest,
    N8nGenerateResponse,
    N8nUploadRequest,
    N8nUploadResponse,
    OutlookRequest,
    OutlookResponse,
    PickSectorRequest,
    PickSectorResponse,
    PickStockRequest,
    PickStockResponse,
    RotationPickResponse,
    TdccPickResponse,
    TdccSummary,
    VideoRequest,
    WeeklyRecapRequest,
    WeeklyRecapResponse,
    WeeklyReviewResponse,
)
from apps.api.services.video_engine.sector import generate_sector
from apps.api.services.video_engine.upload import (
    compute_publish_at,
    upload_to_youtube,
    _cleanup_file,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Backward-compatible alias for test imports
_compute_foreign_net_k = compute_foreign_net_k


def _fmt_lots(net_k: int) -> str:
    """Format foreign_net_k (千股 = 張) for display. e.g. 107370 → '10.7萬', 3255 → '3,255'."""
    v = abs(net_k)
    return f"{v/10000:.1f}萬" if v >= 10000 else f"{v:,}"


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("/video/thumbnail", summary="Generate YouTube thumbnail PNG")
def get_thumbnail(symbol: str, days: int = 7, _api_key: None = Depends(_check_api_key)) -> Response:
    """Return a 1280x720 PNG thumbnail for the given stock symbol."""
    symbol = symbol.upper().strip()
    chip = get_chip_data(symbol, days)
    daily = chip.get("daily", [])
    if not daily:
        raise HTTPException(404, f"No chip data for {symbol}")

    summary      = chip.get("summary", {})
    company_name = get_company_name(symbol)
    date_range   = f"{daily[0]['date']} ~ {daily[-1]['date']}"
    foreign_net_k = compute_foreign_net_k(summary, daily)

    png_bytes = make_thumbnail(symbol, company_name, foreign_net_k, date_range)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{symbol}_thumbnail.png"'},
    )


@router.post("/video/generate", summary="Generate a YouTube-style analysis video")
def generate_video(req: VideoRequest, _api_key: None = Depends(_check_api_key)) -> FileResponse:
    """Generate a ~45-second YouTube analysis video for a Taiwan stock symbol."""
    is_shorts = req.format.lower() == "shorts"

    sector_name = req.sector_name.strip()
    symbols_raw = [s.upper().strip() for s in req.symbols if s.strip()]

    if sector_name and not symbols_raw:
        key = next((k for k in SECTOR_SYMBOLS if k in sector_name), None)
        symbols_raw = SECTOR_SYMBOLS.get(key or sector_name, [])

    is_sector = bool(sector_name and symbols_raw)
    is_weekly_review = bool(len(symbols_raw) > 1 and not sector_name)

    if is_weekly_review:
        # ── Weekly review mode: one slide per featured stock ──
        stock_chips: list[dict] = []
        for sym in symbols_raw[:5]:
            try:
                chip_data = get_chip_data(sym, req.days)
                daily_data = chip_data.get("daily", [])
                if daily_data:
                    stock_chips.append({
                        "symbol": sym,
                        "name": get_company_name(sym),
                        "chip": chip_data,
                        "daily": daily_data,
                    })
            except Exception:
                logger.warning("Weekly review: failed to fetch chip data for %s", sym)

        if not stock_chips:
            raise HTTPException(404, "No chip data found for any of the supplied symbols")

        # Date range from first stock's data
        first_daily = stock_chips[0]["daily"]
        date_range = f"{first_daily[0]['date']} ~ {first_daily[-1]['date']}"

        # Build symbols_info for title slide
        symbols_info = [{"symbol": sc["symbol"], "name": sc["name"]} for sc in stock_chips]

        # Build per-stock summary data for the final summary slide
        symbols_summaries: list[dict] = []
        for sc in stock_chips:
            daily_vals = sc["daily"]
            fnet_k = sum(
                round(d.get("foreign", {}).get("net", 0) / 1000) for d in daily_vals[-5:]
            )
            symbols_summaries.append({
                "symbol": sc["symbol"],
                "name": sc["name"],
                "foreign_net_k": fnet_k,
            })

        # Slide tasks: title + one per stock + summary
        slide_tasks = [
            (make_weekly_review_title_slide, (symbols_info, date_range)),
        ]
        slide_durations = [SLIDE_SECONDS["title"]]

        for sc in stock_chips:
            slide_tasks.append((
                make_stock_summary_slide,
                (sc["symbol"], sc["name"], sc["daily"], sc["daily"]),
            ))
            slide_durations.append(SLIDE_SECONDS["chart"])

        slide_tasks.append((make_weekly_review_summary_slide, (symbols_summaries, date_range)))
        slide_durations.append(SLIDE_SECONDS["summary"])

        rendered = render_slides_parallel(slide_tasks)
        frames: list[tuple] = list(zip(rendered, slide_durations))

        # Use the first stock for thumbnail
        first_summary = stock_chips[0]["chip"].get("summary", {})
        foreign_net_k = compute_foreign_net_k(first_summary, first_daily)
        thumb_label = "weekly_review"
        thumb_company = "本週精選回顧"
        filename_base = "weekly_review"

    elif is_sector:
        chip  = get_sector_chip(symbols_raw, sector_name, req.days)
        daily = chip["daily"]
        summary = chip["summary"]
        date_range = f"{daily[0]['date']} ~ {daily[-1]['date']}" if daily else "N/A"
        foreign_net_k = compute_foreign_net_k(summary, daily)
        symbol_label  = sector_name.replace("族群", "").strip()

        symbols_data: list[dict] = []
        for sym_info in chip["symbols"]:
            try:
                sd = get_chip_data(sym_info["symbol"], req.days)
                symbols_data.append({**sym_info, **sd})
            except Exception:
                pass

        slide_tasks = [
            (make_sector_title_slide, (sector_name, chip["symbols"], date_range)),
            (make_foreign_chart, (daily,)),
            (make_trust_dealer_chart, (daily,)),
            (make_sector_breakdown_chart, (symbols_data, req.days)),
            (make_summary_slide, (summary, date_range)),
        ]
        slide_durations = [
            SLIDE_SECONDS["title"],
            SLIDE_SECONDS["chart"],
            SLIDE_SECONDS["chart"],
            SLIDE_SECONDS["chart"],
            SLIDE_SECONDS["summary"],
        ]
        rendered = render_slides_parallel(slide_tasks)
        frames: list[tuple] = list(zip(rendered, slide_durations))
        thumb_label   = sector_name
        thumb_company = sector_name
        filename_base = f"{symbol_label}_sector"
    else:
        symbol = req.symbol.upper().strip()
        chip  = get_chip_data(symbol, req.days)
        daily = chip.get("daily", [])
        if not daily:
            raise HTTPException(404, f"No chip data for {symbol}")

        summary       = chip.get("summary", {})
        company_name  = get_company_name(symbol)
        date_range    = f"{daily[0]['date']} ~ {daily[-1]['date']}"
        foreign_net_k = compute_foreign_net_k(summary, daily)

        if is_shorts:
            frames = [
                (make_shorts_slide(symbol, company_name, date_range, summary, daily, compute_foreign_net_k), 58),
            ]
        else:
            slide_tasks = [
                (make_title_slide, (symbol, company_name, date_range)),
                (make_foreign_chart, (daily,)),
                (make_trust_dealer_chart, (daily,)),
                (make_cumulative_chart, (daily,)),
                (make_summary_slide, (summary, date_range)),
            ]
            slide_durations = [
                SLIDE_SECONDS["title"],
                SLIDE_SECONDS["chart"],
                SLIDE_SECONDS["chart"],
                SLIDE_SECONDS["chart"],
                SLIDE_SECONDS["summary"],
            ]
            rendered = render_slides_parallel(slide_tasks)
            frames = list(zip(rendered, slide_durations))
        thumb_company = company_name
        thumb_label   = symbol
        filename_base = f"{symbol}_{'shorts' if is_shorts else 'chip_report'}"

    tts_rate = "+35%" if is_shorts else None
    audio = None
    if req.script:
        spoken = clean_script_for_tts(req.script)
        audio = tts_edge(spoken[:500] if is_shorts else spoken, rate=tts_rate)

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp.close()

    if not is_shorts:
        try:
            png_bytes = make_thumbnail(thumb_label, thumb_company, foreign_net_k, date_range)
            thumb_path = Path(tempfile.gettempdir()) / f"{thumb_label}_thumbnail.png"
            thumb_path.write_bytes(png_bytes)
        except Exception:
            logger.exception("Thumbnail generation failed -- continuing without")

    try:
        build_mp4(frames, audio, tmp.name)
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


@router.post(
    "/video-gen/pick-stock",
    summary="Pick best stock for a video slot (stateless, for n8n)",
    response_model=PickStockResponse | WeeklyReviewResponse,
)
def pick_stock(req: PickStockRequest, _api_key: None = Depends(_check_api_key)):
    """Stateless stock picker for n8n video automation."""
    from domain.calendar.cooldown import get_cooldown_symbols, get_today_sectors, record_pick
    from domain.calendar.planner import get_sector_for_symbol
    from apps.api.config import DB_PATH

    exclude = set(s.upper().strip() for s in req.exclude_symbols)
    if not req.ignore_cooldown:
        cooldown_syms = get_cooldown_symbols(DB_PATH, days=req.cooldown_days)
        if cooldown_syms:
            logger.info("Cooldown active -- excluding: %s", cooldown_syms)
        exclude = exclude | cooldown_syms

    # Get today's already-picked sectors to avoid same-sector picks in one day
    today_sectors = get_today_sectors(DB_PATH)
    if today_sectors:
        logger.info("Today's sectors already picked: %s -- diversifying", today_sectors)

    scored, data_date, is_fallback = score_symbols_with_fallback(_DEFAULT_SYMBOLS)
    if not scored:
        raise HTTPException(404, "No chip data available for the last 5 trading days.")

    slot = req.slot.value
    base_exclude = set(s.upper().strip() for s in req.exclude_symbols)

    if slot in ("weekly_review", "long_friday"):
        candidates = [s for s in scored if s["symbol"] not in exclude]
        if not candidates and exclude != base_exclude:
            logger.warning("All candidates on cooldown for %s -- ignoring cooldown", slot)
            candidates = [s for s in scored if s["symbol"] not in base_exclude]
        candidates.sort(key=lambda x: x.get("abs_volume", 0), reverse=True)
        top = candidates[:5]
        if not top:
            raise HTTPException(404, "All symbols excluded -- no candidates left.")
        for p in top:
            sector = get_sector_for_symbol(p["symbol"])
            record_pick(DB_PATH, p["symbol"], slot=slot, data_date=data_date, sector_name=sector)
        items = [
            build_pick_response(
                pick=p, template_type="abs_volume",
                reason=f"本週法人成交量排名 #{i + 1} ({p.get('abs_volume', 0):,.0f})",
                data_date=data_date, is_fallback=is_fallback,
            )
            for i, p in enumerate(top)
        ]
        return WeeklyReviewResponse(symbols=items, data_date=data_date, is_holiday_fallback=is_fallback)

    config = SLOT_CONFIG.get(slot)
    if not config:
        raise HTTPException(400, f"Unknown slot: {slot}")
    scoring_key, title_template, reason_template = config

    if slot == "morning":
        candidates = [s for s in scored if s["symbol"] not in exclude]
        # Also filter out same-sector as today's picks
        if today_sectors:
            candidates = [
                s for s in candidates
                if get_sector_for_symbol(s["symbol"]) not in today_sectors
            ] or candidates  # fallback to unfiltered if all excluded
        if not candidates and exclude != base_exclude:
            candidates = [s for s in scored if s["symbol"] not in base_exclude]
        if not candidates:
            raise HTTPException(404, "All symbols excluded -- no candidates left.")
        pick = max(candidates, key=lambda x: abs(x.get("foreign_net", 0)))
    else:
        pick = _pick_top(scored, scoring_key, exclude, exclude_sectors=today_sectors)
        if not pick:
            # Retry without sector filter
            pick = _pick_top(scored, scoring_key, exclude)
        if not pick and exclude != base_exclude:
            pick = _pick_top(scored, scoring_key, base_exclude)

    if not pick:
        raise HTTPException(404, "All symbols excluded -- no candidates left.")

    sector = get_sector_for_symbol(pick["symbol"])
    record_pick(DB_PATH, pick["symbol"], slot=slot, data_date=data_date, sector_name=sector)
    reason = reason_template.format(value=pick.get(scoring_key, 0))
    return build_pick_response(
        pick=pick, template_type=title_template,
        reason=reason, data_date=data_date, is_fallback=is_fallback,
    )


@router.get("/video-gen/cooldown-status", summary="Show currently cooled-down symbols and sectors")
def cooldown_status(_api_key: None = Depends(_check_api_key)):
    """Return symbols and sectors currently on cooldown, plus recent pick history."""
    from domain.calendar.cooldown import get_cooldown_symbols, get_cooldown_sectors, get_recent_picks
    from apps.api.config import DB_PATH
    return {
        "cooldown_symbols": sorted(get_cooldown_symbols(DB_PATH)),
        "cooldown_sectors": sorted(get_cooldown_sectors(DB_PATH)),
        "recent_picks": get_recent_picks(DB_PATH, days=7),
    }


# ── Agent perception endpoints ──────────────────────────────────────────────


@router.get("/video-gen/recent-performance", summary="Recent video upload history for agent perception")
def recent_performance(limit: int = 10, _api_key: None = Depends(_check_api_key)):
    """Return recent video uploads so the agent can assess past performance."""
    from domain.calendar.cooldown import get_recent_picks
    from apps.api.config import DB_PATH

    picks = get_recent_picks(DB_PATH, days=14)[:limit]

    # Also get upload log for YouTube video IDs
    db_path = str(DB_PATH)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        uploads = conn.execute(
            "SELECT symbol, slot, data_date, video_id, youtube_url, uploaded_at "
            "FROM video_upload_log ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    except Exception:
        uploads = []
    finally:
        conn.close()

    return {
        "recent_picks": picks,
        "recent_uploads": [dict(u) for u in uploads],
        "total_picks_14d": len(picks),
        "total_uploads": len(uploads),
    }


@router.get("/video-gen/market-snapshot", summary="Market snapshot for agent decision-making")
def market_snapshot(_api_key: None = Depends(_check_api_key)):
    """Return current market overview — TAIEX, top movers, sector trends.

    Used by the autonomous agent to decide video strategy.
    """
    snapshot: dict = {
        "generated_at": datetime.now().isoformat(),
        "taiex": None,
        "us_indices": {},
        "top_movers": [],
        "volatility_level": "medium",
    }

    # TAIEX + key indices via yfinance
    try:
        import yfinance as yf

        indices = {
            "^TWII": "加權指數",
            "^SOX": "費半指數",
            "^GSPC": "S&P 500",
        }
        for symbol, name in indices.items():
            try:
                t = yf.Ticker(symbol)
                hist = t.history(period="5d")
                if hist.empty:
                    continue
                latest = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else hist.iloc[0]
                close_val = float(latest["Close"])
                prev_close = float(prev["Close"])
                change_pct = ((close_val - prev_close) / prev_close * 100) if prev_close else 0

                entry = {
                    "name": name,
                    "close": round(close_val, 2),
                    "change_pct": round(change_pct, 2),
                    "date": str(latest.name.date()) if hasattr(latest.name, "date") else str(date.today()),
                }

                if symbol == "^TWII":
                    snapshot["taiex"] = entry
                else:
                    snapshot["us_indices"][symbol] = entry
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", symbol, e)

        # Determine volatility from TAIEX change
        if snapshot["taiex"]:
            abs_change = abs(snapshot["taiex"]["change_pct"])
            if abs_change > 2.0:
                snapshot["volatility_level"] = "high"
            elif abs_change < 0.5:
                snapshot["volatility_level"] = "low"

    except ImportError:
        logger.warning("yfinance not installed, market snapshot limited")

    # Top movers from chip data (today's biggest foreign buy/sell)
    try:
        from apps.api.config import DB_PATH
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT symbol, foreign_net
               FROM chip_daily
               WHERE trade_date = (SELECT MAX(trade_date) FROM chip_daily)
               ORDER BY ABS(foreign_net) DESC
               LIMIT 5""",
        ).fetchall()
        conn.close()

        snapshot["top_movers"] = [
            {"symbol": r["symbol"], "foreign_net": r["foreign_net"]}
            for r in rows
        ]
    except Exception as e:
        logger.debug("Top movers not available: %s", e)

    return snapshot


# ── Competitor trends cache ─────────────────────────────────────────────────
_competitor_trends_cache: dict = {"data": None, "ts": 0.0}
_COMPETITOR_CACHE_TTL = 4 * 3600  # 4 hours in seconds


@router.get("/video-gen/competitor-trends", summary="Trending stock topics from competitor YouTube channels")
def competitor_trends(_api_key: None = Depends(_check_api_key)):
    """Research trending stock analysis topics from Taiwan investment YouTube channels.

    Uses Gemini CLI to discover what competitors are covering, returning
    structured trending topics, hot stocks, and content gaps.
    Results are cached for 4 hours.
    """
    import time

    now = time.time()
    cached = _competitor_trends_cache
    if cached["data"] is not None and (now - cached["ts"]) < _COMPETITOR_CACHE_TTL:
        return cached["data"]

    prompt = (
        "台灣投資 YouTube 頻道（如柴鼠兄弟、投資嗨嗨、Mr. Market）"
        "最近 7 天最熱門的影片主題是什麼？哪些股票/產業被討論最多？\n\n"
        "請用以下 JSON 格式回覆，不要加任何其他文字：\n"
        "{\n"
        '  "trending_topics": ["主題1", "主題2", ...],\n'
        '  "competitor_hot_stocks": ["股票代號1", "股票代號2", ...],\n'
        '  "content_gaps": ["尚未有人做XX分析", ...]\n'
        "}"
    )

    fallback = {
        "generated_at": datetime.now().isoformat(),
        "trending_topics": [],
        "competitor_hot_stocks": [],
        "content_gaps": [],
        "source": "gemini",
        "error": "Gemini unavailable",
    }

    try:
        result = subprocess.run(
            ["gemini"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            logger.warning("Gemini CLI failed (rc=%d): %s", result.returncode, result.stderr[:200])
            return fallback

        raw = result.stdout.strip()

        # Try to extract JSON from the response (handle markdown fences)
        json_str = raw
        if "```" in raw:
            # Extract content between first ``` and last ```
            parts = raw.split("```")
            for part in parts[1:]:
                cleaned = part.strip()
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
                if cleaned.startswith("{"):
                    json_str = cleaned
                    break

        try:
            parsed = json.loads(json_str)
            response = {
                "generated_at": datetime.now().isoformat(),
                "trending_topics": parsed.get("trending_topics", []),
                "competitor_hot_stocks": parsed.get("competitor_hot_stocks", []),
                "content_gaps": parsed.get("content_gaps", []),
                "source": "gemini",
            }
        except json.JSONDecodeError:
            logger.warning("Failed to parse Gemini JSON, returning raw text")
            response = {
                "generated_at": datetime.now().isoformat(),
                "trending_topics": [],
                "competitor_hot_stocks": [],
                "content_gaps": [],
                "source": "gemini",
                "raw_response": raw[:2000],
            }

        _competitor_trends_cache["data"] = response
        _competitor_trends_cache["ts"] = now
        return response

    except subprocess.TimeoutExpired:
        logger.warning("Gemini CLI timed out after 60s")
        return fallback
    except FileNotFoundError:
        logger.warning("Gemini CLI not found on PATH")
        return fallback
    except Exception as e:
        logger.warning("Competitor trends failed: %s", e)
        return fallback


@router.get("/video-gen/market-heat", summary="Today's hottest stocks/sectors for video content selection")
def market_heat(_api_key: None = Depends(_check_api_key)):
    """Return heat-ranked stocks and sectors based on institutional chip data.

    Heat score formula: abs(foreign_net) + abs(trust_net) * 2
    (投信 weighted higher for retail interest signal).
    """
    from apps.api.config import DB_PATH

    result: dict = {
        "heat_date": None,
        "hot_stocks": [],
        "hot_sectors": [],
        "overall_heat": "low",
    }

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row

        # Find latest trading day
        row = conn.execute("SELECT MAX(trade_date) AS latest FROM chip_daily").fetchone()
        if not row or not row["latest"]:
            conn.close()
            return result

        heat_date = row["latest"]
        result["heat_date"] = heat_date

        # Fetch all chip data for the latest trading day
        chips = conn.execute(
            """SELECT symbol, foreign_net, trust_net, dealer_net, total_net
               FROM chip_daily
               WHERE trade_date = ?""",
            (heat_date,),
        ).fetchall()

        if not chips:
            conn.close()
            return result

        # Compute heat score for each stock
        scored = []
        for c in chips:
            foreign_net = c["foreign_net"] or 0
            trust_net = c["trust_net"] or 0
            heat_score = abs(foreign_net) + abs(trust_net) * 2
            scored.append({
                "symbol": c["symbol"],
                "foreign_net": foreign_net,
                "trust_net": trust_net,
                "dealer_net": c["dealer_net"] or 0,
                "total_net": c["total_net"] or 0,
                "heat_score": heat_score,
            })

        # Sort by heat_score descending
        scored.sort(key=lambda x: x["heat_score"], reverse=True)

        # Top 5 by foreign_net (absolute)
        by_foreign = sorted(scored, key=lambda x: abs(x["foreign_net"]), reverse=True)[:5]
        # Top 5 by trust_net (absolute)
        by_trust = sorted(scored, key=lambda x: abs(x["trust_net"]), reverse=True)[:5]

        # Overall top 10 by heat_score (deduplicated)
        top_symbols_seen: set[str] = set()
        hot_stocks: list[dict] = []
        for s in scored:
            if s["symbol"] in top_symbols_seen:
                continue
            top_symbols_seen.add(s["symbol"])
            hot_stocks.append(s)
            if len(hot_stocks) >= 10:
                break

        result["hot_stocks"] = hot_stocks

        # Sector aggregation via company_master join
        try:
            sector_rows = conn.execute(
                """SELECT cm.sector, SUM(ABS(cd.foreign_net)) AS foreign_abs,
                          SUM(ABS(cd.trust_net)) AS trust_abs,
                          COUNT(*) AS stock_count,
                          SUM(ABS(cd.foreign_net) + ABS(cd.trust_net) * 2) AS sector_heat
                   FROM chip_daily cd
                   JOIN company_master cm ON cd.symbol = cm.symbol
                   WHERE cd.trade_date = ? AND cm.sector IS NOT NULL AND cm.sector != ''
                   GROUP BY cm.sector
                   ORDER BY sector_heat DESC
                   LIMIT 10""",
                (heat_date,),
            ).fetchall()

            result["hot_sectors"] = [
                {
                    "sector": r["sector"],
                    "foreign_abs_total": r["foreign_abs"],
                    "trust_abs_total": r["trust_abs"],
                    "stock_count": r["stock_count"],
                    "sector_heat": r["sector_heat"],
                }
                for r in sector_rows
            ]
        except Exception as e:
            logger.debug("Sector aggregation not available: %s", e)

        conn.close()

        # Determine overall heat level from top stock scores
        if hot_stocks:
            max_heat = hot_stocks[0]["heat_score"]
            if max_heat > 50000:
                result["overall_heat"] = "high"
            elif max_heat > 10000:
                result["overall_heat"] = "medium"

        # Attach breakdown lists for convenience
        result["top_foreign"] = [
            {"symbol": s["symbol"], "foreign_net": s["foreign_net"]} for s in by_foreign
        ]
        result["top_trust"] = [
            {"symbol": s["symbol"], "trust_net": s["trust_net"]} for s in by_trust
        ]

    except Exception as e:
        logger.warning("market-heat query failed: %s", e)

    return result


@router.post(
    "/video-gen/generate",
    summary="Generate video with full pipeline (script+TTS+CTR title) for n8n",
    response_model=N8nGenerateResponse,
)
def n8n_generate_video(req: N8nGenerateRequest, _api_key: None = Depends(_check_api_key)):
    """Full video generation pipeline for n8n, reusing calendar.py logic."""
    from apps.api.routers.calendar import (
        _generate_script, _generate_video, _generate_thumbnail,
        _fetch_chip_summary, _get_company_name_for_title,
        _build_algo_title, _build_algo_description, _build_algo_tags,
    )

    symbol = req.symbol.upper().strip()
    is_shorts = req.slot in SHORTS_SLOTS
    slot_content_type = {
        "morning": "single", "afternoon": "single", "long_tuesday": "single",
        "long_friday": "macro", "sat_am": "single", "sat_pm": "single",
        "sun_am": "single", "sun_pm": "single",
    }
    # ── Fetch chip data BEFORE script generation so GPT uses real numbers ──
    chip = _fetch_chip_summary(symbol, days=7) if symbol else {}
    company_name = _get_company_name_for_title(symbol) if symbol else ""

    chip_data_summary = ""
    if chip:
        # foreign_net_k is in 千股; 1張=1000股, so 千股=張
        fn_lots = chip.get("foreign_net_k", 0)  # unit: 張
        tn_lots = chip.get("trust_net_k", 0)
        f_dir = "買超" if fn_lots >= 0 else "賣超"
        t_dir = "買超" if tn_lots >= 0 else "賣超"
        fn_display = f"{abs(fn_lots)/10000:.1f}萬" if abs(fn_lots) >= 10000 else str(abs(fn_lots))
        tn_display = f"{abs(tn_lots)/10000:.1f}萬" if abs(tn_lots) >= 10000 else str(abs(tn_lots))
        chip_data_summary = (
            f"{company_name}（{symbol}）：外資{f_dir}{fn_display}張、"
            f"投信{t_dir}{tn_display}張"
        )

    episode = {
        "symbol": symbol, "title": req.title,
        "content_type": slot_content_type.get(req.slot, "single"),
        "pick_reason": "", "sector_name": "", "symbols": [],
        "metadata": {
            "format": "shorts" if is_shorts else "landscape",
            "days": 7, "weekly_review": req.slot == "long_friday", "breaking": False,
            "chip_data_summary": chip_data_summary,
        },
    }

    script = _generate_script(episode)
    try:
        video_path = _generate_video(episode, script)
    except Exception as exc:
        raise HTTPException(500, f"Video generation failed: {exc}") from exc

    thumb_path = _generate_thumbnail(episode)

    return N8nGenerateResponse(
        video_path=video_path, thumbnail_path=thumb_path,
        title=_build_algo_title(episode, chip, company_name, is_shorts),
        description=_build_algo_description(episode, chip, company_name, is_shorts, script),
        tags=_build_algo_tags(episode, company_name, is_shorts),
        script=script, symbol=symbol, slot=req.slot,
    )


@router.post(
    "/video-gen/upload-youtube",
    summary="Upload video to YouTube with publishAt scheduling (for n8n)",
    response_model=N8nUploadResponse,
)
def n8n_upload_youtube(req: N8nUploadRequest, _api_key: None = Depends(_check_api_key)):
    """Upload video to YouTube with optional publishAt scheduling."""
    from apps.api.config import DB_PATH
    from domain.calendar.cooldown import (
        find_existing_upload, record_upload,
        get_today_upload_count, get_last_upload_time,
    )

    # ── Rate limiting ──
    if not req.ignore_rate_limit:
        today_count = get_today_upload_count(DB_PATH)
        if today_count >= 3:
            next_midnight = (datetime.now(tz=None).replace(hour=0, minute=0, second=0) + timedelta(days=1))
            return JSONResponse({
                "rate_limited": True,
                "reason": "Max 3 uploads per day reached",
                "today_count": today_count,
                "suggested_retry": next_midnight.isoformat(),
            })

        last_upload = get_last_upload_time(DB_PATH)
        if last_upload:
            from datetime import timezone as _tz
            now_utc = datetime.now(_tz.utc)
            hours_since = (now_utc - last_upload).total_seconds() / 3600
            if hours_since < 4:
                retry_at = last_upload + timedelta(hours=4)
                return JSONResponse({
                    "rate_limited": True,
                    "reason": "Minimum 4-hour spacing between uploads",
                    "hours_since_last": round(hours_since, 2),
                    "suggested_retry": retry_at.isoformat(),
                })

    data_date = req.data_date or date.today().isoformat()
    symbol = req.symbol.upper() if req.symbol else ""
    if symbol and data_date:
        existing = find_existing_upload(DB_PATH, symbol, req.slot, data_date)
        if existing:
            logger.info("Duplicate upload skipped: %s/%s/%s", symbol, req.slot, data_date)
            return N8nUploadResponse(
                video_id=existing["video_id"], url=existing["youtube_url"],
                title=req.title, privacy=req.privacy, publish_at=None,
            )

    if not Path(req.video_path).exists():
        raise HTTPException(404, f"Video file not found: {req.video_path}")

    privacy = req.privacy.lower()
    if privacy not in ("public", "unlisted", "private"):
        raise HTTPException(400, "privacy must be public, unlisted, or private")

    publish_at, priv_override = compute_publish_at(req.publish_time)
    if priv_override:
        privacy = priv_override

    try:
        video_id = upload_to_youtube(
            req.video_path, req.title, req.description, req.tags,
            privacy, publish_at, req.slot, req.thumbnail_path,
            auto_comment=req.auto_comment,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"YouTube upload failed: {exc}") from exc
    finally:
        _cleanup_file(req.video_path)
        if req.thumbnail_path:
            _cleanup_file(req.thumbnail_path)

    youtube_url = f"https://youtu.be/{video_id}"
    if symbol and data_date:
        record_upload(DB_PATH, symbol, req.slot, data_date, video_id, youtube_url)

    return N8nUploadResponse(
        video_id=video_id, url=youtube_url, title=req.title,
        privacy=privacy, publish_at=publish_at,
    )


@router.post(
    "/video-gen/upload-youtube-form",
    summary="Upload video file to YouTube via multipart form (alternative to JSON)",
    response_model=N8nUploadResponse,
)
async def n8n_upload_youtube_form(
    file: UploadFile = File(..., description="MP4 video file"),
    title: str = Form(..., description="YouTube video title"),
    description: str = Form("", description="Video description"),
    tags: str = Form("", description="Comma-separated tags"),
    privacy: str = Form("private", description="public | unlisted | private"),
    slot: str = Form("morning", description="Slot type for playlist routing"),
    publish_time: Optional[str] = Form(None, description="HH:MM publish time"),
    thumbnail: UploadFile | None = File(None, description="Thumbnail PNG"),
    _api_key: None = Depends(_check_api_key),
) -> JSONResponse:
    """Upload video to YouTube via multipart form data."""
    privacy = privacy.lower()
    if privacy not in ("public", "unlisted", "private"):
        raise HTTPException(400, "privacy must be public, unlisted, or private")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp_video.write(await file.read())
    tmp_video.close()
    video_path = tmp_video.name

    tmp_thumb_path: str | None = None
    if thumbnail:
        tmp_thumb = tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=tempfile.gettempdir())
        tmp_thumb.write(await thumbnail.read())
        tmp_thumb.close()
        tmp_thumb_path = tmp_thumb.name

    publish_at, priv_override = compute_publish_at(publish_time)
    if priv_override:
        privacy = priv_override

    try:
        video_id = upload_to_youtube(
            video_path, title, description, tag_list,
            privacy, publish_at, slot, tmp_thumb_path,
            auto_comment=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"YouTube upload failed: {exc}") from exc
    finally:
        _cleanup_file(video_path)
        if tmp_thumb_path:
            _cleanup_file(tmp_thumb_path)

    return JSONResponse({
        "video_id": video_id, "url": f"https://youtu.be/{video_id}",
        "title": title, "privacy": privacy, "publish_at": publish_at,
    })


@router.post(
    "/video-gen/pick-sector-smart",
    summary="Pick best sector for a video (stateless, for n8n)",
    response_model=PickSectorResponse,
)
def pick_sector_smart(req: PickSectorRequest, _api_key: None = Depends(_check_api_key)):
    """Score all sector groups by chip activity and return the most active one."""
    from domain.calendar.cooldown import get_today_sectors, record_pick
    from apps.api.config import DB_PATH

    exclude = set(t.strip() for t in req.exclude_themes)
    if not req.ignore_cooldown:
        # Use same-day cooldown only — with 7 sectors and 5+ sector videos/week,
        # multi-day cooldown exhausts all sectors and falls through to no cooldown.
        cooldown_sectors = get_today_sectors(DB_PATH)
        if cooldown_sectors:
            logger.info("Sector cooldown (today) -- excluding: %s", cooldown_sectors)
        exclude = exclude | cooldown_sectors

    base_exclude = set(t.strip() for t in req.exclude_themes)
    candidates = {n: s for n, s in SECTOR_SYMBOLS.items() if n not in exclude}
    if not candidates and exclude != base_exclude:
        logger.warning("All sectors picked today -- ignoring cooldown")
        candidates = {n: s for n, s in SECTOR_SYMBOLS.items() if n not in base_exclude}
    if not candidates:
        raise HTTPException(400, "All sectors excluded")

    sector_scores: list[dict] = []
    for sn, syms in candidates.items():
        try:
            sd = get_sector_chip(syms, sn, days=5)
            sm = sd["summary"]
            sector_scores.append({
                "sector_name": sn, "symbols": sd["symbols"], "summary": sm,
                "abs_volume": abs(sm.get("foreign_net_total", 0))
                    + abs(sm.get("investment_trust_net_total", 0))
                    + abs(sm.get("dealer_net_total", 0)),
            })
        except Exception:
            logger.warning("Sector scoring failed for %s", sn)

    if not sector_scores:
        raise HTTPException(502, "No sector data available")

    best = max(sector_scores, key=lambda x: x["abs_volume"])
    today = date.today()
    weekday = today.weekday()
    slot = {1: "long_tuesday", 5: "weekend_am", 6: "weekend_pm"}.get(weekday, "sector")

    record_pick(DB_PATH, symbol=best["sector_name"], slot=slot,
                data_date=today.isoformat(), sector_name=best["sector_name"])

    return PickSectorResponse(
        sector_name=best["sector_name"], symbols=best["symbols"],
        slot=slot, summary=best["summary"],
    )


@router.post(
    "/video-gen/generate-sector",
    summary="Generate sector analysis video (for n8n)",
    response_model=GenerateSectorResponse,
)
def generate_sector_video(req: GenerateSectorRequest, _api_key: None = Depends(_check_api_key)):
    """Generate a sector analysis video with chip data."""
    return generate_sector(req.sector_name, req.slot, req.format)


# ── TDCC bracket helpers ────────────────────────────────────────────────────

# Levels whose lower bound >= 400,001 shares (≈400張)
_BIG_HOLDER_LEVELS = {
    "400,001-600,000", "600,001-800,000", "800,001-1,000,000",
    "1,000,001以上", "more than 1,000,001",
}

# Levels whose upper bound <= 10,000 shares (≈10張)
_RETAIL_LEVELS = {
    "1-999", "1,000-5,000", "5,001-10,000",
}


def _sum_pct(rows: list[dict], target_levels: set[str]) -> float:
    """Sum `pct` for rows whose level is in target_levels."""
    total = 0.0
    for r in rows:
        level = r.get("level", "")
        if level in target_levels:
            total += r.get("pct", 0.0) or 0.0
    return total


def _pick_best_tdcc_symbol(db_path: str) -> dict:
    """Scan top default symbols for the most dramatic TDCC bracket shift.

    Returns a dict with keys: symbol, company_name, big_change, retail_change,
    big_pct, retail_pct, latest_date, prev_date, title.
    Raises HTTPException(404) when no usable TDCC data exists.
    """
    from domain.financials.repository import get_tdcc_distribution

    top_symbols = _DEFAULT_SYMBOLS[:5]
    best_symbol: str = ""
    best_change: float = 0.0
    best_big_change: float = 0.0
    best_retail_change: float = 0.0
    best_big_pct: float = 0.0
    best_retail_pct: float = 0.0
    best_latest_date: str = ""
    best_prev_date: str = ""

    for sym in top_symbols:
        rows = get_tdcc_distribution(db_path, sym, limit=2)
        if not rows:
            continue

        dates = sorted({r["date"] for r in rows}, reverse=True)
        if len(dates) < 2:
            continue

        latest_date, prev_date = dates[0], dates[1]
        latest_rows = [r for r in rows if r["date"] == latest_date]
        prev_rows = [r for r in rows if r["date"] == prev_date]

        big_latest = _sum_pct(latest_rows, _BIG_HOLDER_LEVELS)
        big_prev = _sum_pct(prev_rows, _BIG_HOLDER_LEVELS)
        retail_latest = _sum_pct(latest_rows, _RETAIL_LEVELS)
        retail_prev = _sum_pct(prev_rows, _RETAIL_LEVELS)

        big_change = big_latest - big_prev
        retail_change = retail_latest - retail_prev

        if abs(big_change) > abs(best_change):
            best_symbol = sym
            best_change = big_change
            best_big_change = big_change
            best_retail_change = retail_change
            best_big_pct = big_latest
            best_retail_pct = retail_latest
            best_latest_date = latest_date
            best_prev_date = prev_date

    if not best_symbol:
        raise HTTPException(404, "No TDCC data with 2+ dates found for default symbols.")

    company_name = get_company_name(best_symbol)

    if best_big_change > 0:
        title = f"\U0001f525{company_name} 大戶持股暴增！散戶卻在跑？"
    elif best_big_change < 0:
        title = f"\U0001f6a8{company_name} 大戶正在出貨？散戶接刀中"
    else:
        title = f"{company_name} 集保戶數大變動！籌碼面解讀"

    if len(title) > 60:
        title = title[:57] + "..."

    return {
        "symbol": best_symbol,
        "company_name": company_name,
        "big_change": best_big_change,
        "retail_change": best_retail_change,
        "big_pct": best_big_pct,
        "retail_pct": best_retail_pct,
        "latest_date": best_latest_date,
        "prev_date": best_prev_date,
        "title": title,
    }


def _pick_best_rotation_pair() -> dict:
    """Find the top-buy and top-sell stock by foreign net.

    Returns a dict with keys: buy_symbol, buy_name, buy_lots,
    sell_symbol, sell_name, sell_lots, title.
    Raises HTTPException(404) when no data or no valid pair.
    """
    scored, _data_date, _is_fallback = score_symbols_with_fallback(_DEFAULT_SYMBOLS)
    if not scored:
        raise HTTPException(404, "No chip data available for rotation analysis.")

    top_buy = max(scored, key=lambda x: x.get("foreign_net", 0))
    top_sell = min(scored, key=lambda x: x.get("foreign_net", 0))

    if top_buy["symbol"] == top_sell["symbol"]:
        raise HTTPException(404, "Cannot form a rotation pair — all symbols have identical foreign_net.")

    buy_name = get_company_name(top_buy["symbol"])
    sell_name = get_company_name(top_sell["symbol"])

    buy_lots = round(top_buy.get("foreign_net", 0) / 1000)
    sell_lots = round(top_sell.get("foreign_net", 0) / 1000)

    title = f"外資換股！減碼{sell_name} 轉買{buy_name}"
    if len(title) > 60:
        title = title[:57] + "..."

    return {
        "buy_symbol": top_buy["symbol"],
        "buy_name": buy_name,
        "buy_lots": buy_lots,
        "sell_symbol": top_sell["symbol"],
        "sell_name": sell_name,
        "sell_lots": sell_lots,
        "title": title,
    }


@router.post(
    "/video-gen/pick-tdcc",
    summary="Pick stock with most dramatic TDCC shift (for n8n)",
    response_model=TdccPickResponse,
)
def pick_tdcc(_api_key: None = Depends(_check_api_key)):
    """Analyse TDCC distribution for top-5 default symbols and pick the most dramatic shift."""
    from apps.api.config import DB_PATH

    pick = _pick_best_tdcc_symbol(DB_PATH)

    return TdccPickResponse(
        symbol=pick["symbol"],
        title=pick["title"],
        tdcc_summary=TdccSummary(
            big_holder_pct_change=round(pick["big_change"], 2),
            retail_pct_change=round(pick["retail_change"], 2),
            latest_date=pick["latest_date"],
            prev_date=pick["prev_date"],
        ),
    )


@router.post(
    "/video-gen/pick-rotation",
    summary="Pick institutional rotation pair (for n8n)",
    response_model=RotationPickResponse,
)
def pick_rotation(_api_key: None = Depends(_check_api_key)):
    """Find the top-buy and top-sell stock by foreign net and return a rotation pair."""
    pair = _pick_best_rotation_pair()

    return RotationPickResponse(
        buy_symbol=pair["buy_symbol"],
        buy_name=pair["buy_name"],
        buy_lots=pair["buy_lots"],
        sell_symbol=pair["sell_symbol"],
        sell_name=pair["sell_name"],
        sell_lots=pair["sell_lots"],
        title=pair["title"],
    )


# ── Full-pipeline endpoints (pick + generate in one call) ────────────────


def _build_tdcc_description(company_name: str, symbol: str, big_change: float, retail_change: float) -> str:
    """Build SEO description for TDCC shorts video."""
    big_dir = "增加" if big_change >= 0 else "減少"
    retail_dir = "增加" if retail_change >= 0 else "減少"
    parts = [
        f"{company_name}（{symbol}）集保戶數變動速報！",
        f"大戶持股{big_dir}{abs(big_change):.2f}%，散戶持股{retail_dir}{abs(retail_change):.2f}%",
        "\U0001f4ca JARVIS 選股｜每天 60 秒掌握籌碼動態",
        "",
        "\u26a0\ufe0f 免責聲明：本頻道內容僅供參考，不構成任何投資建議。投資有風險，請自行評估。",
        "",
        " ".join([
            "#台股", f"#{company_name}", f"#{symbol}",
            "#集保戶數", "#籌碼分析", "#大戶持股", "#Shorts",
            "#JARVIS選股", "#散戶", "#法人",
        ]),
    ]
    return "\n".join(parts)


def _build_tdcc_tags(company_name: str, symbol: str) -> list[str]:
    """Build tag list for TDCC shorts video."""
    return [
        "集保戶數", "籌碼分析", "台股", "JARVIS選股",
        "大戶持股", "散戶持股", symbol, f"{symbol}分析",
        company_name, f"{company_name}籌碼", "Shorts",
        "台股Shorts", "每日快報", "法人動態", "AI選股",
    ]


def _build_rotation_description(
    sell_name: str, sell_lots: int, buy_name: str, buy_lots: int,
) -> str:
    """Build SEO description for rotation shorts video."""
    parts = [
        f"外資本週換股操作：減碼{sell_name} {abs(sell_lots):,}張，加碼{buy_name} {abs(buy_lots):,}張",
        "\U0001f4ca JARVIS 選股｜每天 60 秒掌握法人資金流向",
        "",
        "\u26a0\ufe0f 免責聲明：本頻道內容僅供參考，不構成任何投資建議。投資有風險，請自行評估。",
        "",
        " ".join([
            "#台股", f"#{sell_name}", f"#{buy_name}",
            "#外資", "#換股", "#法人動態", "#Shorts",
            "#JARVIS選股", "#籌碼分析", "#資金流向",
        ]),
    ]
    return "\n".join(parts)


def _build_rotation_tags(sell_name: str, buy_name: str) -> list[str]:
    """Build tag list for rotation shorts video."""
    return [
        "外資換股", "法人動態", "台股", "JARVIS選股",
        "籌碼分析", sell_name, buy_name, "外資買賣超",
        "資金流向", "Shorts", "台股Shorts", "每日快報",
        "AI選股", "投信買賣超",
    ]


@router.post(
    "/video-gen/generate-tdcc",
    summary="Generate TDCC shorts video (pick + generate)",
    response_model=N8nGenerateResponse,
)
def generate_tdcc_video(_api_key=Depends(_check_api_key)):
    """Full pipeline: pick the most dramatic TDCC shift, generate slide + TTS, return video."""
    from apps.api.config import DB_PATH

    # ── Pick ──
    pick = _pick_best_tdcc_symbol(DB_PATH)
    company_name = pick["company_name"]
    best_symbol = pick["symbol"]
    best_big_change = pick["big_change"]
    best_retail_change = pick["retail_change"]
    title = pick["title"]

    # ── Slide ──
    slide = make_tdcc_shorts_slide(
        company_name=company_name,
        big_holder_change=best_big_change,
        retail_change=best_retail_change,
        big_holder_pct=pick["big_pct"],
        retail_pct=pick["retail_pct"],
    )

    # ── Script + TTS ──
    direction = "增加" if best_big_change >= 0 else "減少"
    retail_direction = "增加" if best_retail_change >= 0 else "減少"
    script_prompt = (
        f"分析 {company_name}（{best_symbol}）最新集保戶數變化："
        f"大戶持股{direction}{abs(best_big_change):.2f}%，"
        f"散戶持股{retail_direction}{abs(best_retail_change):.2f}%。"
        f"用30秒說明這代表什麼籌碼訊號。"
    )
    script = openai_script(script_prompt, max_tokens=300)
    spoken = clean_script_for_tts(script)
    audio = tts_edge(spoken[:500], rate="+35%")

    # ── Assemble MP4 ──
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp.close()
    try:
        build_mp4([(slide, 58)], audio, tmp.name)
    except Exception as exc:
        Path(tmp.name).unlink(missing_ok=True)
        logger.exception("TDCC video generation failed")
        raise HTTPException(500, f"TDCC video generation failed: {exc}") from exc

    return N8nGenerateResponse(
        video_path=tmp.name,
        thumbnail_path=None,
        title=title,
        description=_build_tdcc_description(company_name, best_symbol, best_big_change, best_retail_change),
        tags=_build_tdcc_tags(company_name, best_symbol),
        script=script,
        symbol=best_symbol,
        slot="tdcc",
    )


@router.post(
    "/video-gen/generate-rotation",
    summary="Generate rotation shorts video (pick + generate)",
    response_model=N8nGenerateResponse,
)
def generate_rotation_video(_api_key=Depends(_check_api_key)):
    """Full pipeline: pick top buy/sell rotation pair, generate slide + TTS, return video."""
    # ── Pick ──
    pair = _pick_best_rotation_pair()
    buy_name = pair["buy_name"]
    sell_name = pair["sell_name"]
    buy_lots = pair["buy_lots"]
    sell_lots = pair["sell_lots"]
    title = pair["title"]

    # ── Slide ──
    slide = make_rotation_shorts_slide(
        sell_name=sell_name,
        sell_lots=sell_lots,
        buy_name=buy_name,
        buy_lots=buy_lots,
    )

    # ── Script + TTS ──
    script_prompt = (
        f"外資本週換股操作：減碼{sell_name} {abs(sell_lots)}張，"
        f"同時加碼{buy_name} {abs(buy_lots)}張。"
        f"分析這個資金轉移代表什麼。"
    )
    script = openai_script(script_prompt, max_tokens=300)
    spoken = clean_script_for_tts(script)
    audio = tts_edge(spoken[:500], rate="+35%")

    # ── Assemble MP4 ──
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp.close()
    try:
        build_mp4([(slide, 58)], audio, tmp.name)
    except Exception as exc:
        Path(tmp.name).unlink(missing_ok=True)
        logger.exception("Rotation video generation failed")
        raise HTTPException(500, f"Rotation video generation failed: {exc}") from exc

    return N8nGenerateResponse(
        video_path=tmp.name,
        thumbnail_path=None,
        title=title,
        description=_build_rotation_description(sell_name, sell_lots, buy_name, buy_lots),
        tags=_build_rotation_tags(sell_name, buy_name),
        script=script,
        symbol=pair["buy_symbol"],
        slot="rotation",
    )


# ── Google Trends 熱搜 ─────────────────────────────────────────────────────


def _build_trends_description(stocks: list[dict]) -> str:
    lines = ["Google 搜尋量暴增的台股 vs 法人真實動向！"]
    for s in stocks[:5]:
        arrow = "買超" if s.get("foreign_net_k", 0) >= 0 else "賣超"
        lines.append(f"  {s['name']}（{s['symbol']}）搜尋+{s['pct_change']:.0f}%｜外資{arrow}{_fmt_lots(s.get('foreign_net_k', 0))}張")
    lines.append("")
    lines.append("📊 JARVIS 選股｜散戶熱搜 × 法人籌碼 每日追蹤")
    lines.append("⚠️ 免責聲明：本頻道內容僅供參考，不構成任何投資建議。投資有風險，請自行評估。")
    return "\n".join(lines)


def _build_trends_tags(stocks: list[dict]) -> list[str]:
    tags = ["Google Trends", "台股熱搜", "散戶指標", "法人籌碼", "三大法人",
            "台股", "JARVIS選股", "Shorts", "台股Shorts", "AI選股"]
    for s in stocks[:5]:
        tags.extend([s["name"], s["symbol"]])
    return tags


@router.post(
    "/video-gen/generate-trends",
    summary="Generate Google Trends vs institutional flow shorts video",
    response_model=N8nGenerateResponse,
)
def generate_trends_video(_api_key=Depends(_check_api_key)):
    """Full pipeline: fetch Google Trends spikes, cross-ref with chip data, generate video."""
    from apps.api.services.video_engine.constants import TICKER_NAME
    from domain.trends.service import detect_spikes, fetch_trends_for_symbols

    # ── Fetch trends ──
    trends = fetch_trends_for_symbols(_DEFAULT_SYMBOLS, TICKER_NAME)
    if not trends:
        raise HTTPException(404, "Google Trends returned no data for default symbols.")

    # Try progressively lower thresholds
    spikes = detect_spikes(trends, threshold=200.0)
    if not spikes:
        spikes = detect_spikes(trends, threshold=100.0)
    if not spikes:
        spikes = detect_spikes(trends, threshold=50.0)
    if not spikes:
        # Take top 3 by pct_change regardless of threshold
        sorted_trends = sorted(trends, key=lambda t: t.pct_change, reverse=True)
        spikes = sorted_trends[:3]

    # ── Cross-reference with chip data ──
    trending_stocks: list[dict] = []
    for t in spikes:
        try:
            chip = get_chip_data(t.symbol, 7)
            daily = chip.get("daily", [])
            summary = chip.get("summary", {})
            fnet_k = compute_foreign_net_k(summary, daily)
        except Exception:
            fnet_k = 0

        # Contrarian = search spiking but institutions selling
        signal = "contrarian" if t.pct_change > 0 and fnet_k < 0 else "aligned"
        trending_stocks.append({
            "symbol": t.symbol,
            "name": t.name,
            "pct_change": t.pct_change,
            "foreign_net_k": fnet_k,
            "signal": signal,
        })

    if not trending_stocks:
        raise HTTPException(404, "No trending stocks with chip data found.")

    top = trending_stocks[0]

    # ── Title ──
    if top["signal"] == "contrarian":
        title = f"{top['name']}搜尋量暴增{top['pct_change']:.0f}%，但外資卻在賣…"
    else:
        title = f"外資狂買！{top['name']}搜尋量暴增{top['pct_change']:.0f}%"
    if len(title) > 60:
        title = title[:57] + "..."

    # ── Slide ──
    slide = make_trends_shorts_slide(trending_stocks)

    # ── Script + TTS ──
    stock_desc = "、".join(
        f"{s['name']}搜尋量+{s['pct_change']:.0f}%（外資{'買超' if s['foreign_net_k'] >= 0 else '賣超'}{_fmt_lots(s['foreign_net_k'])}張）"
        for s in trending_stocks[:3]
    )
    script_prompt = (
        f"以下台股的 Google 搜尋量近一週暴增：{stock_desc}。"
        f"分析散戶關注度飆升但法人動向不同的現象，提醒投資人注意。用30秒說完。"
    )
    script = openai_script(script_prompt, max_tokens=300)
    spoken = clean_script_for_tts(script)
    audio = tts_edge(spoken[:500], rate="+35%")

    # ── Assemble MP4 ──
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp.close()
    try:
        build_mp4([(slide, 58)], audio, tmp.name)
    except Exception as exc:
        Path(tmp.name).unlink(missing_ok=True)
        logger.exception("Trends video generation failed")
        raise HTTPException(500, f"Trends video generation failed: {exc}") from exc

    return N8nGenerateResponse(
        video_path=tmp.name,
        thumbnail_path=None,
        title=title,
        description=_build_trends_description(trending_stocks),
        tags=_build_trends_tags(trending_stocks),
        script=script,
        symbol=top["symbol"],
        slot="trends",
    )


# ── Community Post ─────────────────────────────────────────────────────────


@router.post(
    "/video-gen/community-post",
    summary="Generate weekly community post content (poll/text)",
    response_model=CommunityPostResponse,
)
def community_post(
    req: CommunityPostRequest = CommunityPostRequest(),
    _api_key: None = Depends(_check_api_key),
):
    """Generate community post content for the YouTube Community tab.

    YouTube Data API v3 does not support creating community posts or polls
    programmatically. This endpoint generates the suggested content so it
    can be posted manually via YouTube Studio or scheduled via n8n reminder.

    Default poll: "本週最強族群？" with sector options.
    """
    today = date.today()
    week_label = f"{today.isocalendar()[0]}W{today.isocalendar()[1]:02d}"

    poll_text = req.poll_question
    options = req.poll_options[:5]  # YouTube polls support max 5 options

    body_lines = [
        f"📊 {poll_text}",
        "",
        f"本週（{week_label}）你最看好哪個族群？投票告訴我！",
    ]
    if req.additional_text:
        body_lines.append("")
        body_lines.append(req.additional_text)
    body_lines.extend([
        "",
        "🔔 記得訂閱開啟小鈴鐺，每天掌握法人動態！",
        "#台股 #族群分析 #JARVIS選股 #投票",
    ])

    suggested_content = {
        "type": "poll",
        "poll_question": poll_text,
        "poll_options": options,
        "post_body": "\n".join(body_lines),
        "week_label": week_label,
        "instructions": (
            "YouTube Data API v3 不支援社群貼文/投票功能。"
            "請至 YouTube Studio > 社群 手動發布，或透過 n8n 排程提醒。"
        ),
    }

    logger.info(
        "Community post content generated for %s: %s (%d options)",
        week_label, poll_text, len(options),
    )

    return CommunityPostResponse(
        status="content_generated",
        message=(
            "社群貼文內容已產生。YouTube API 不支援自動發布社群貼文，"
            "請至 YouTube Studio 手動貼文。"
        ),
        suggested_content=suggested_content,
    )


# ── Weekly recap ─────────────────────────────────────────────────────────────


def _get_last_monday() -> date:
    """Return the most recent Monday (or today if today is Monday)."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def _build_weekly_recap_description(
    featured: list[dict], week_start: str, week_end: str,
) -> str:
    """Build SEO description for the weekly recap video."""
    parts = [
        f"📊 JARVIS 選股｜{week_start} ～ {week_end} 本週法人籌碼回顧",
        "",
    ]
    for s in featured[:5]:
        f_dir = "買超" if s.get("foreign_net_k", 0) >= 0 else "賣超"
        t_dir = "買超" if s.get("trust_net_k", 0) >= 0 else "賣超"
        parts.append(
            f"  {s['name']}（{s['symbol']}）外資{f_dir}{_fmt_lots(s.get('foreign_net_k', 0))}張"
            f"｜投信{t_dir}{_fmt_lots(s.get('trust_net_k', 0))}張"
        )
    parts.append("")
    parts.append("🔔 訂閱開啟小鈴鐺，每週掌握法人動態！")
    parts.append("")
    parts.append("⚠️ 免責聲明：本頻道內容僅供參考，不構成任何投資建議。投資有風險，請自行評估。")
    parts.append("")
    symbols_tags = " ".join(f"#{s['name']}" for s in featured[:5])
    parts.append(f"#台股 #三大法人 #籌碼分析 #JARVIS選股 #週報 #外資 #投信 {symbols_tags}")
    return "\n".join(parts)


def _build_weekly_recap_tags(featured: list[dict]) -> list[str]:
    """Build tag list for the weekly recap video."""
    tags = [
        "台股週報", "三大法人", "籌碼分析", "JARVIS選股", "外資買賣超",
        "投信買賣超", "法人動態", "台股分析", "本週回顧", "AI選股",
    ]
    for s in featured[:5]:
        tags.extend([s["name"], s["symbol"]])
    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:30]


@router.post(
    "/video-gen/weekly-recap",
    summary="Generate weekly recap video (~2-3 min landscape)",
    response_model=WeeklyRecapResponse,
)
def generate_weekly_recap(
    req: WeeklyRecapRequest,
    _api_key: None = Depends(_check_api_key),
):
    """Generate a 2-3 minute weekly recap video summarising institutional activity."""
    from apps.api.config import DB_PATH
    from apps.api.routers.calendar import (
        _generate_script, _generate_video, _generate_thumbnail,
        _fetch_chip_summary, _get_company_name_for_title,
    )
    from domain.calendar.cooldown import get_recent_picks

    # ── Determine week range ──
    if req.week_start:
        try:
            ws = date.fromisoformat(req.week_start)
        except ValueError:
            raise HTTPException(400, "week_start must be YYYY-MM-DD")
        if ws.weekday() != 0:
            raise HTTPException(400, "week_start must be a Monday")
    else:
        ws = _get_last_monday()

    we = ws + timedelta(days=6)
    week_start_str = ws.isoformat()
    week_end_str = we.isoformat()

    # ── Query past 7 days of video_pick_history for featured stocks ──
    recent_picks = get_recent_picks(DB_PATH, days=7)
    # Deduplicate symbols, preserving order of first appearance
    seen_symbols: set[str] = set()
    unique_symbols: list[str] = []
    for pick in recent_picks:
        sym = pick["symbol"].upper()
        if sym not in seen_symbols:
            seen_symbols.add(sym)
            unique_symbols.append(sym)

    if not unique_symbols:
        raise HTTPException(404, "No video picks found in the past 7 days for weekly recap.")

    # ── Fetch chip data for each featured stock ──
    featured: list[dict] = []
    for sym in unique_symbols[:10]:
        chip = _fetch_chip_summary(sym, days=7)
        if not chip:
            continue
        company_name = _get_company_name_for_title(sym)
        featured.append({
            "symbol": sym,
            "name": company_name,
            "foreign_net": chip.get("foreign_net", 0),
            "foreign_net_k": chip.get("foreign_net_k", 0),
            "trust_net": chip.get("trust_net", 0),
            "trust_net_k": chip.get("trust_net_k", 0),
            "consec_buy": chip.get("consec_buy", 0),
            "consec_sell": chip.get("consec_sell", 0),
        })

    if not featured:
        raise HTTPException(404, "Could not fetch chip data for any featured stocks.")

    # Sort by absolute institutional activity (most active first)
    featured.sort(
        key=lambda s: abs(s["foreign_net_k"]) + abs(s["trust_net_k"]),
        reverse=True,
    )
    top = featured[:5]

    # ── Build structured chip data summary with EXACT real numbers ──
    stock_lines = []
    chip_data_lines = []
    for s in top:
        f_dir = "買超" if s["foreign_net_k"] >= 0 else "賣超"
        t_dir = "買超" if s["trust_net_k"] >= 0 else "賣超"
        # foreign_net_k is 千股; 1張=1000股 → 千股=張
        fn_lots = abs(s['foreign_net_k'])
        tn_lots = abs(s['trust_net_k'])
        fn_d = f"{fn_lots/10000:.1f}萬" if fn_lots >= 10000 else str(fn_lots)
        tn_d = f"{tn_lots/10000:.1f}萬" if tn_lots >= 10000 else str(tn_lots)
        stock_lines.append(
            f"{s['name']}（{s['symbol']}）：外資{f_dir}{fn_d}張、"
            f"投信{t_dir}{tn_d}張"
        )
        # Build per-stock detail line with all available fields
        detail = (
            f"- {s['name']}（{s['symbol']}）："
            f"外資週{f_dir} {fn_d} 張、"
            f"投信週{t_dir} {tn_d} 張"
        )
        if s["consec_buy"] > 0:
            detail += f"、外資連買 {s['consec_buy']} 日"
        if s["consec_sell"] > 0:
            detail += f"、外資連賣 {s['consec_sell']} 日"
        chip_data_lines.append(detail)

    chip_data_summary = "\n".join(chip_data_lines)

    # ── Build episode dict for _generate_script (weekly_review type) ──
    episode = {
        "symbol": top[0]["symbol"],
        "title": f"本週法人重點回顧｜{week_start_str} ～ {week_end_str}",
        "content_type": "macro",
        "pick_reason": f"本週法人活躍個股：{', '.join(s['name'] for s in top)}",
        "sector_name": "",
        "symbols": [s["symbol"] for s in top],
        "metadata": {
            "format": "landscape",
            "days": 7,
            "weekly_review": True,
            "reviewed_symbols": [s["symbol"] for s in top],
            "chip_data_summary": chip_data_summary,
        },
    }

    # ── Generate script with weekly_review prompt ──
    script = _generate_script(episode)

    # If script generation returned empty, build a fallback prompt
    if not script:
        fallback_prompt = (
            f"你是台股 YouTube 頻道「JARVIS 選股」的主持人。\n"
            f"請用 2-3 分鐘回顧 {week_start_str} ～ {week_end_str} 的法人動態。\n\n"
            f"【真實籌碼數據 — 你必須使用以下數據，禁止自行編造或修改任何數字】\n"
            f"{chip_data_summary}\n"
            f"以上數據為系統從資料庫撈取的真實法人買賣超數字。"
            f"腳本中提到的所有數字必須與上方資料完全一致，"
            f"不可四捨五入、不可改用其他單位、不可憑印象捏造。\n\n"
            f"結構：開場用本週最驚人的數字 Hook → 逐一點評 top 3-5 檔 → 下週展望 → CTA\n"
            f"嚴禁給出買賣建議，僅分析籌碼事實。\n"
            f"不要加任何小標題或段落標號，直接寫口語化的台詞。"
        )
        script = openai_script(fallback_prompt, max_tokens=2000)

    # ── Generate video (landscape 1920x1080) ──
    try:
        video_path = _generate_video(episode, script)
    except Exception as exc:
        raise HTTPException(500, f"Weekly recap video generation failed: {exc}") from exc

    thumb_path = _generate_thumbnail(episode)

    # ── Build title / description / tags ──
    title = f"本週法人重點：{'、'.join(s['name'] for s in top[:3])}...｜週報"
    if len(title) > 60:
        title = title[:57] + "..."

    description = _build_weekly_recap_description(top, week_start_str, week_end_str)
    tags = _build_weekly_recap_tags(top)

    return WeeklyRecapResponse(
        video_path=video_path,
        thumbnail_path=thumb_path,
        title=title,
        description=description,
        tags=tags,
        script=script,
        featured_symbols=[s["symbol"] for s in top],
        week_start=week_start_str,
        week_end=week_end_str,
    )


# ── Next-week outlook ─────────────────────────────────────────────────────


def _fetch_next_week_catalysts() -> list[dict]:
    """Return catalysts whose event_date falls in next Mon-Fri."""
    from apps.api.config import DB_PATH
    from domain.catalyst.service import upcoming_catalysts

    today = date.today()
    # Next Monday
    days_until_monday = (7 - today.weekday()) % 7
    if days_until_monday == 0:
        days_until_monday = 7
    next_monday = today + timedelta(days=days_until_monday)

    try:
        cats = upcoming_catalysts(
            db_path=DB_PATH,
            as_of=next_monday.isoformat(),
            days=5,
        )
        return cats
    except Exception:
        logger.warning("Could not fetch catalysts for next-week outlook")
        return []


def _fetch_upcoming_ex_dividends() -> list[dict]:
    """Return ex-dividend dates for default symbols falling in the next 7 days."""
    from domain.dividend.service import fetch_dividends

    today = date.today()
    next_week_end = today + timedelta(days=7)
    results: list[dict] = []

    for sym in _DEFAULT_SYMBOLS[:10]:
        try:
            records = fetch_dividends(sym)
            for rec in records:
                if today.isoformat() <= rec.ex_date <= next_week_end.isoformat():
                    results.append({
                        "symbol": sym,
                        "ex_date": rec.ex_date,
                        "cash_dividend": rec.cash_dividend,
                        "stock_dividend": rec.stock_dividend,
                        "company_name": get_company_name(sym),
                    })
        except Exception:
            logger.debug("Dividend fetch failed for %s — skipping", sym)

    results.sort(key=lambda r: r["ex_date"])
    return results


def _build_outlook_description(
    featured: list[dict],
    catalysts: list[dict],
    ex_divs: list[dict],
) -> str:
    """Build SEO description for the next-week outlook video."""
    parts = [
        "📊 JARVIS 選股｜下週展望：開盤前必看法人動向",
        "",
    ]
    if catalysts:
        parts.append("📅 下週重要事件：")
        for c in catalysts[:3]:
            parts.append(f"  {c.get('event_date', '')} {c.get('title', '')}")
        parts.append("")
    if ex_divs:
        parts.append("💰 下週除息：")
        for d in ex_divs[:3]:
            parts.append(f"  {d['company_name']}（{d['symbol']}）{d['ex_date']} 除息 {d['cash_dividend']} 元")
        parts.append("")
    if featured:
        parts.append("🔍 法人重點關注：")
        for s in featured[:5]:
            f_dir = "買超" if s.get("foreign_net_k", 0) >= 0 else "賣超"
            parts.append(f"  {s['name']}（{s['symbol']}）外資{f_dir}{_fmt_lots(s.get('foreign_net_k', 0))}張")
        parts.append("")
    parts.append("🔔 訂閱開啟小鈴鐺，每天掌握法人動態！")
    parts.append("")
    parts.append("⚠️ 免責聲明：本頻道內容僅供參考，不構成任何投資建議。投資有風險，請自行評估。")
    parts.append("")
    symbol_tags = " ".join(f"#{s['name']}" for s in featured[:5])
    parts.append(f"#台股 #下週展望 #法人動態 #JARVIS選股 #Shorts #外資 #投信 {symbol_tags}")
    return "\n".join(parts)


def _build_outlook_tags(featured: list[dict]) -> list[str]:
    """Build tag list for the next-week outlook video."""
    tags = [
        "下週展望", "台股", "法人動態", "JARVIS選股", "外資買賣超",
        "投信買賣超", "開盤前必看", "Shorts", "台股Shorts", "AI選股",
        "三大法人", "籌碼分析",
    ]
    for s in featured[:5]:
        tags.extend([s["name"], s["symbol"]])
    seen: set[str] = set()
    unique: list[str] = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:30]


@router.post(
    "/video-gen/generate-outlook",
    summary="Generate next-week outlook shorts video (for n8n Sunday evening)",
    response_model=OutlookResponse,
)
def generate_outlook_video(
    req: OutlookRequest = OutlookRequest(),
    _api_key: None = Depends(_check_api_key),
):
    """Generate a 40-second Shorts previewing next week's key events and stocks.

    Data priority:
    1. Catalysts from domain/catalyst (earnings, events)
    2. Upcoming ex-dividend dates from domain/dividend
    3. Fallback: top 3-5 stocks by recent institutional activity
    """
    from apps.api.routers.calendar import (
        _fetch_chip_summary, _get_company_name_for_title,
        _generate_video,
    )

    is_shorts = req.format.lower() == "shorts"

    # ── 1. Gather catalysts ──
    catalysts = _fetch_next_week_catalysts()
    catalyst_symbols = [
        c["symbol"] for c in catalysts
        if c.get("symbol")
    ]

    # ── 2. Gather ex-dividends ──
    ex_divs = _fetch_upcoming_ex_dividends()
    ex_div_symbols = [d["symbol"] for d in ex_divs]

    # ── 3. Merge unique symbols, fallback to chip activity ──
    seen_syms: set[str] = set()
    all_symbols: list[str] = []
    for sym in catalyst_symbols + ex_div_symbols:
        s = sym.upper().strip()
        if s and s not in seen_syms:
            seen_syms.add(s)
            all_symbols.append(s)

    if len(all_symbols) < 3:
        # Fallback: top stocks by institutional activity
        scored, _data_date, _is_fallback = score_symbols_with_fallback(_DEFAULT_SYMBOLS)
        scored.sort(key=lambda x: x.get("abs_volume", 0), reverse=True)
        for s in scored:
            sym = s["symbol"].upper()
            if sym not in seen_syms:
                seen_syms.add(sym)
                all_symbols.append(sym)
            if len(all_symbols) >= 5:
                break

    all_symbols = all_symbols[:5]

    if not all_symbols:
        raise HTTPException(404, "No data available for next-week outlook.")

    # ── 4. Fetch chip data for each featured stock ──
    featured: list[dict] = []
    for sym in all_symbols:
        chip = _fetch_chip_summary(sym, days=7)
        company_name = _get_company_name_for_title(sym)
        if not company_name:
            company_name = get_company_name(sym)
        featured.append({
            "symbol": sym,
            "name": company_name,
            "foreign_net_k": chip.get("foreign_net_k", 0) if chip else 0,
            "trust_net_k": chip.get("trust_net_k", 0) if chip else 0,
        })

    # ── 5. Build script prompt ──
    stock_names = "、".join(s["name"] for s in featured[:3])
    catalyst_lines = ""
    if catalysts:
        catalyst_lines = "；".join(
            f"{c.get('event_date', '')} {c.get('title', '')}"
            for c in catalysts[:3]
        )
        catalyst_lines = f"\n下週重要事件：{catalyst_lines}"

    ex_div_lines = ""
    if ex_divs:
        ex_div_lines = "；".join(
            f"{d['company_name']}({d['symbol']}) {d['ex_date']}除息"
            for d in ex_divs[:3]
        )
        ex_div_lines = f"\n下週除息：{ex_div_lines}"

    chip_lines = "；".join(
        f"{s['name']}外資{'買超' if s['foreign_net_k'] >= 0 else '賣超'}{_fmt_lots(s['foreign_net_k'])}張"
        for s in featured[:3]
    )

    script_prompt = (
        f"你是台股 YouTube 頻道「JARVIS 選股」的主持人。\n"
        f"請用 40 秒（140-170字）預告下週一開盤前必看重點。\n"
        f"法人近期動向：{chip_lines}"
        f"{catalyst_lines}"
        f"{ex_div_lines}\n\n"
        f"結構：\n"
        f"1. 前3秒 Hook — 「下週一開盤前必看！」或類似急迫感開場\n"
        f"2. 重點個股/事件快速點評（3-5檔）\n"
        f"3. 結尾 CTA：訂閱+小鈴鐺\n\n"
        f"嚴禁給出買賣建議，僅分析籌碼事實與事件提醒。\n"
        f"結尾加上：「免責聲明：本頻道內容僅供參考，不構成任何投資建議。」"
    )

    script = openai_script(script_prompt, max_tokens=400)

    # ── 6. Generate video ──
    episode = {
        "symbol": featured[0]["symbol"],
        "title": f"下週展望：{stock_names}",
        "content_type": "macro",
        "pick_reason": f"下週關注個股：{stock_names}",
        "sector_name": "",
        "symbols": [s["symbol"] for s in featured],
        "metadata": {
            "format": "shorts" if is_shorts else "landscape",
            "days": 7,
            "weekly_review": False,
            "breaking": False,
        },
    }

    try:
        video_path = _generate_video(episode, script)
    except Exception as exc:
        raise HTTPException(500, f"Outlook video generation failed: {exc}") from exc

    # ── 7. Build title / description / tags ──
    title = f"【下週關注】{stock_names} 法人動向搶先看"
    if len(title) > 60:
        title = title[:57] + "..."

    description = _build_outlook_description(featured, catalysts, ex_divs)
    tags = _build_outlook_tags(featured)

    return OutlookResponse(
        video_path=video_path,
        thumbnail_path=None,
        title=title,
        description=description,
        tags=tags,
        script=script,
        featured_symbols=[s["symbol"] for s in featured],
    )


# ── Check missed schedule & auto-recover ──────────────────────────────────

# Day-of-week (0=Mon) → list of (slot, hour, pipeline_type)
# Each slot name must be unique per day for dedup matching.
_DAILY_SCHEDULE: dict[int, list[tuple[str, int, str]]] = {
    0: [("morning", 12, "stock"), ("afternoon", 19, "stock")],          # Mon
    1: [("morning", 12, "stock"), ("long_tuesday", 19, "sector")],      # Tue
    2: [("morning", 12, "stock"), ("afternoon", 19, "stock")],          # Wed
    3: [("morning", 12, "stock"), ("afternoon", 19, "stock")],          # Thu
    4: [("morning", 12, "stock"), ("long_friday", 19, "stock")],        # Fri
    5: [("sat_morning", 9, "weekly_recap"), ("sat_noon", 12, "stock"),
        ("sat_evening", 19, "sector")],                                  # Sat
    6: [("sun_morning", 9, "stock"), ("sun_noon", 12, "stock"),
        ("sun_evening", 19, "outlook")],                                 # Sun
}

# Map schedule slot names to equivalent upload-log slot names for matching.
# Uploads may record under different names due to n8n node config or manual fallback.
_SLOT_ALIASES: dict[str, set[str]] = {
    "sat_morning": {"sat_morning", "sat_am", "weekly_review"},
    "sat_noon": {"sat_noon", "sat_pm", "morning"},
    "sat_evening": {"sat_evening", "sector", "long_tuesday"},
    "sun_morning": {"sun_morning", "sun_am", "morning"},
    "sun_noon": {"sun_noon", "sun_pm", "morning"},
    "sun_evening": {"sun_evening", "outlook", "sun_pm"},
}


@router.post(
    "/video-gen/check-missed",
    summary="Check for missed scheduled videos and optionally auto-recover",
    response_model=CheckMissedResponse,
)
def check_missed_videos(
    auto_recover: bool = True,
    dry_run: bool = False,
    _api_key: None = Depends(_check_api_key),
):
    """Compare today's expected schedule against actual uploads and recover missed slots.

    - auto_recover=True (default): automatically pick+generate+upload for each missed slot
    - dry_run=True: only report what's missing, don't generate/upload
    """
    from apps.api.config import DB_PATH

    now = datetime.now()
    today_str = date.today().isoformat()
    dow = date.today().weekday()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    schedule = _DAILY_SCHEDULE.get(dow, [])
    current_hour = now.hour

    # Build expected slots (only those whose scheduled hour has passed)
    expected: list[dict] = []
    for slot, hour, pipeline in schedule:
        if current_hour >= hour:
            expected.append({"slot": slot, "hour": hour, "pipeline": pipeline})

    # Query today's upload log
    with sqlite3.connect(str(DB_PATH), timeout=10) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT symbol, slot, video_id, youtube_url, uploaded_at
               FROM video_upload_log WHERE date(uploaded_at) = ?""",
            (today_str,),
        ).fetchall()

    uploaded = [dict(r) for r in rows]
    uploaded_slot_names = {r["slot"] for r in rows}

    # Determine missed slots — a slot is covered if any of its aliases appear
    missed: list[dict] = []
    for ex in expected:
        slot = ex["slot"]
        aliases = _SLOT_ALIASES.get(slot, {slot})
        if not (aliases & uploaded_slot_names):
            missed.append(ex)

    recovered: list[dict] = []
    errors: list[dict] = []

    if auto_recover and not dry_run and missed:
        for m in missed:
            slot = m["slot"]
            pipeline = m["pipeline"]
            try:
                if pipeline == "stock":
                    result = _recover_stock_slot(slot, _api_key)
                    recovered.append({"slot": slot, "pipeline": pipeline, **result})
                elif pipeline == "outlook":
                    result = _recover_outlook_slot(_api_key)
                    recovered.append({"slot": slot, "pipeline": "outlook", **result})
                elif pipeline == "weekly_recap":
                    result = _recover_weekly_recap_slot(_api_key)
                    recovered.append({"slot": slot, "pipeline": "weekly_recap", **result})
                elif pipeline == "sector":
                    result = _recover_sector_slot(_api_key)
                    recovered.append({"slot": slot, "pipeline": "sector", **result})
                else:
                    errors.append({"slot": slot, "error": f"Unknown pipeline: {pipeline}"})
            except Exception as exc:
                logger.exception("Failed to recover slot %s", slot)
                errors.append({"slot": slot, "error": str(exc)})

    return CheckMissedResponse(
        today=today_str,
        day_of_week=day_names[dow],
        expected_slots=expected,
        uploaded_slots=uploaded,
        missed_slots=[{"slot": m["slot"], "pipeline": m["pipeline"]} for m in missed],
        recovered=recovered,
        errors=errors,
    )


def _recover_stock_slot(slot: str, _api_key: None) -> dict:
    """Pick a stock and generate+upload for the given slot."""
    import requests as _req

    base = "http://localhost:8000"
    headers = {"Content-Type": "application/json", "X-API-Key": "jarvis2330"}

    # Map schedule slot to pick-stock enum value
    pick_slot_map = {
        "sun_morning": "morning", "sun_noon": "morning",
        "sat_noon": "morning", "sat_morning": "morning",
    }
    pick_slot = pick_slot_map.get(slot, slot)

    # Pick
    pick_resp = _req.post(
        f"{base}/api/video-gen/pick-stock",
        json={"slot": pick_slot}, headers=headers, timeout=30,
    )
    pick_resp.raise_for_status()
    pick = pick_resp.json()

    # Generate
    gen_resp = _req.post(
        f"{base}/api/video-gen/generate",
        json={"symbol": pick["symbol"], "title": pick["title"], "slot": pick_slot},
        headers=headers, timeout=600,
    )
    gen_resp.raise_for_status()
    gen = gen_resp.json()

    # Upload — record with the schedule slot name for dedup
    upload_resp = _req.post(
        f"{base}/api/video-gen/upload-youtube",
        json={
            "video_path": gen["video_path"],
            "title": gen["title"],
            "description": gen["description"],
            "tags": gen["tags"],
            "symbol": pick["symbol"],
            "slot": slot,
            "data_date": date.today().isoformat(),
            "ignore_rate_limit": True,
        },
        headers=headers, timeout=120,
    )
    upload_resp.raise_for_status()
    upload = upload_resp.json()

    return {"symbol": pick["symbol"], "title": gen["title"], "url": upload.get("url", "")}


def _recover_outlook_slot(_api_key: None) -> dict:
    """Generate and upload an outlook video."""
    import requests as _req

    base = "http://localhost:8000"
    headers = {"Content-Type": "application/json", "X-API-Key": "jarvis2330"}

    gen_resp = _req.post(
        f"{base}/api/video-gen/generate-outlook",
        json={"format": "shorts"}, headers=headers, timeout=600,
    )
    gen_resp.raise_for_status()
    gen = gen_resp.json()

    upload_resp = _req.post(
        f"{base}/api/video-gen/upload-youtube",
        json={
            "video_path": gen["video_path"],
            "title": gen["title"],
            "description": gen["description"],
            "tags": gen["tags"],
            "symbol": gen.get("featured_symbols", [""])[0],
            "slot": "sun_pm",
            "data_date": date.today().isoformat(),
            "ignore_rate_limit": True,
        },
        headers=headers, timeout=120,
    )
    upload_resp.raise_for_status()
    upload = upload_resp.json()

    return {"title": gen["title"], "url": upload.get("url", "")}


def _recover_weekly_recap_slot(_api_key: None) -> dict:
    """Generate and upload a weekly recap video."""
    import requests as _req

    base = "http://localhost:8000"
    headers = {"Content-Type": "application/json", "X-API-Key": "jarvis2330"}

    gen_resp = _req.post(
        f"{base}/api/video-gen/weekly-recap",
        json={}, headers=headers, timeout=600,
    )
    gen_resp.raise_for_status()
    gen = gen_resp.json()

    upload_resp = _req.post(
        f"{base}/api/video-gen/upload-youtube",
        json={
            "video_path": gen["video_path"],
            "title": gen["title"],
            "description": gen["description"],
            "tags": gen["tags"],
            "symbol": gen.get("featured_symbols", [""])[0],
            "slot": "sat_am",
            "data_date": date.today().isoformat(),
            "ignore_rate_limit": True,
        },
        headers=headers, timeout=120,
    )
    upload_resp.raise_for_status()
    upload = upload_resp.json()

    return {"title": gen["title"], "url": upload.get("url", "")}


def _recover_sector_slot(_api_key: None) -> dict:
    """Pick a sector and generate+upload."""
    import requests as _req

    base = "http://localhost:8000"
    headers = {"Content-Type": "application/json", "X-API-Key": "jarvis2330"}

    pick_resp = _req.post(
        f"{base}/api/video-gen/pick-sector-smart",
        json={}, headers=headers, timeout=30,
    )
    pick_resp.raise_for_status()
    pick = pick_resp.json()

    gen_resp = _req.post(
        f"{base}/api/video-gen/generate-sector",
        json={
            "sector_name": pick["sector_name"],
            "slot": "sector",
            "format": "shorts",
        },
        headers=headers, timeout=600,
    )
    gen_resp.raise_for_status()
    gen = gen_resp.json()

    upload_resp = _req.post(
        f"{base}/api/video-gen/upload-youtube",
        json={
            "video_path": gen["video_path"],
            "title": gen["title"],
            "description": gen["description"],
            "tags": gen["tags"],
            "symbol": gen.get("sector_name", ""),
            "slot": "sector",
            "data_date": date.today().isoformat(),
            "ignore_rate_limit": True,
        },
        headers=headers, timeout=120,
    )
    upload_resp.raise_for_status()
    upload = upload_resp.json()

    return {"sector": pick["sector_name"], "title": gen["title"], "url": upload.get("url", "")}
