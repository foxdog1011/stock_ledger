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

import logging
import tempfile
from datetime import date
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
    make_sector_breakdown_chart,
    make_sector_title_slide,
    make_shorts_slide,
    make_summary_slide,
    make_thumbnail,
    make_title_slide,
    make_trust_dealer_chart,
    score_symbols_with_fallback,
    tts_edge,
)
from apps.api.services.video_engine.models import (
    GenerateSectorRequest,
    GenerateSectorResponse,
    N8nGenerateRequest,
    N8nGenerateResponse,
    N8nUploadRequest,
    N8nUploadResponse,
    PickSectorRequest,
    PickSectorResponse,
    PickStockRequest,
    PickStockResponse,
    VideoRequest,
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

    if is_sector:
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

        frames: list[tuple] = [
            (make_sector_title_slide(sector_name, chip["symbols"], date_range), SLIDE_SECONDS["title"]),
            (make_foreign_chart(daily),                    SLIDE_SECONDS["chart"]),
            (make_trust_dealer_chart(daily),               SLIDE_SECONDS["chart"]),
            (make_sector_breakdown_chart(symbols_data, req.days), SLIDE_SECONDS["chart"]),
            (make_summary_slide(summary, date_range),      SLIDE_SECONDS["summary"]),
        ]
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
            frames = [
                (make_title_slide(symbol, company_name, date_range), SLIDE_SECONDS["title"]),
                (make_foreign_chart(daily),                          SLIDE_SECONDS["chart"]),
                (make_trust_dealer_chart(daily),                     SLIDE_SECONDS["chart"]),
                (make_cumulative_chart(daily),                       SLIDE_SECONDS["chart"]),
                (make_summary_slide(summary, date_range),            SLIDE_SECONDS["summary"]),
            ]
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
    from domain.calendar.cooldown import get_cooldown_symbols, record_pick
    from apps.api.config import DB_PATH

    exclude = set(s.upper().strip() for s in req.exclude_symbols)
    if not req.ignore_cooldown:
        cooldown_syms = get_cooldown_symbols(DB_PATH, days=req.cooldown_days)
        if cooldown_syms:
            logger.info("Cooldown active -- excluding: %s", cooldown_syms)
        exclude = exclude | cooldown_syms

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
            record_pick(DB_PATH, p["symbol"], slot=slot, data_date=data_date)
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
        if not candidates and exclude != base_exclude:
            candidates = [s for s in scored if s["symbol"] not in base_exclude]
        if not candidates:
            raise HTTPException(404, "All symbols excluded -- no candidates left.")
        pick = max(candidates, key=lambda x: abs(x.get("foreign_net", 0)))
    else:
        pick = _pick_top(scored, scoring_key, exclude)
        if not pick and exclude != base_exclude:
            pick = _pick_top(scored, scoring_key, base_exclude)

    if not pick:
        raise HTTPException(404, "All symbols excluded -- no candidates left.")

    record_pick(DB_PATH, pick["symbol"], slot=slot, data_date=data_date)
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
    episode = {
        "symbol": symbol, "title": req.title,
        "content_type": slot_content_type.get(req.slot, "single"),
        "pick_reason": "", "sector_name": "", "symbols": [],
        "metadata": {
            "format": "shorts" if is_shorts else "landscape",
            "days": 7, "weekly_review": req.slot == "long_friday", "breaking": False,
        },
    }

    script = _generate_script(episode)
    try:
        video_path = _generate_video(episode, script)
    except Exception as exc:
        raise HTTPException(500, f"Video generation failed: {exc}") from exc

    thumb_path = _generate_thumbnail(episode)
    chip = _fetch_chip_summary(symbol, days=7) if symbol else {}
    company_name = _get_company_name_for_title(symbol) if symbol else ""

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
    from domain.calendar.cooldown import find_existing_upload, record_upload

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
    from domain.calendar.cooldown import get_cooldown_sectors, record_pick
    from apps.api.config import DB_PATH

    exclude = set(t.strip() for t in req.exclude_themes)
    if not req.ignore_cooldown:
        cooldown_sectors = get_cooldown_sectors(DB_PATH)
        if cooldown_sectors:
            logger.info("Sector cooldown active -- excluding: %s", cooldown_sectors)
        exclude = exclude | cooldown_sectors

    base_exclude = set(t.strip() for t in req.exclude_themes)
    candidates = {n: s for n, s in SECTOR_SYMBOLS.items() if n not in exclude}
    if not candidates and exclude != base_exclude:
        logger.warning("All sectors on cooldown -- ignoring cooldown")
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
