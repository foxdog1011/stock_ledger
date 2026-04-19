"""Pre-market US overview Shorts — API endpoint for n8n integration.

POST /api/video-gen/premarket-shorts
  body: { "privacy": "public" }
  returns: { video_id, youtube_url, title, skipped, skip_reason, data }
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

# Add scripts/ to path so we can import premarket_shorts
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)


class PremarketShortsRequest(BaseModel):
    privacy: str = "public"


class PremarketShortsResponse(BaseModel):
    video_id: str = ""
    youtube_url: str = ""
    title: str = ""
    skipped: bool = False
    skip_reason: str = ""
    data: dict = {}


@router.post(
    "/video-gen/premarket-shorts",
    summary="Generate and upload pre-market US overview Shorts",
    response_model=PremarketShortsResponse,
)
def premarket_shorts(req: PremarketShortsRequest):
    """End-to-end pre-market Shorts pipeline for n8n.

    Fetches US data → generates slides → AI script → TTS → MP4 → YouTube upload.
    Automatically skips weekends and US holidays.
    """
    from premarket_shorts import (
        fetch_us_market_data,
        generate_script,
        tts_to_mp3,
        build_mp4,
        _make_premarket_slide,
        _make_mini_chart_slide,
        upload_to_youtube,
    )

    today = date.today()

    # Skip weekends
    if today.weekday() in (5, 6):
        return PremarketShortsResponse(skipped=True, skip_reason="Weekend")

    # Fetch data
    data = fetch_us_market_data()
    if not data:
        raise HTTPException(500, "No US market data available")

    # Skip holidays
    sp = data.get("^GSPC", {})
    if sp and sp.get("change") == 0 and sp.get("change_pct") == 0:
        return PremarketShortsResponse(skipped=True, skip_reason="US market holiday")

    # Generate slides
    slide1 = _make_premarket_slide(data)
    slide2 = _make_mini_chart_slide(data)
    frames = [(slide1, 30), (slide2, 30)]

    # Generate script + TTS
    script = generate_script(data)
    audio = tts_to_mp3(script)

    # Build MP4
    today_str = today.strftime("%Y%m%d")
    output_path = str(Path(tempfile.gettempdir()) / f"premarket_shorts_{today_str}.mp4")
    build_mp4(frames, audio, output_path)

    if not Path(output_path).exists():
        raise HTTPException(500, "Video generation failed")

    # Build metadata
    sp_pct = sp.get("change_pct", 0)
    sox = data.get("^SOX", {})
    sox_pct = sox.get("change_pct", 0)
    sp_sign = "+" if sp_pct >= 0 else ""
    sox_sign = "+" if sox_pct >= 0 else ""
    today_display = today.strftime("%m/%d")

    title = (
        f"\u3010\u76e4\u524d\u901f\u5831\u3011{today_display} "
        f"S&P {sp_sign}{sp_pct:.1f}% "
        f"\u8cbb\u534a {sox_sign}{sox_pct:.1f}% "
        f"\u4eca\u5929\u53f0\u80a1\u600e\u9ebc\u770b\uff1f#Shorts"
    )
    description = (
        f"\U0001f4ca {today_display} \u7f8e\u80a1\u76e4\u524d 60 \u79d2\u901f\u5831\n\n"
        f"{script}\n\n"
        f"\u26a0\ufe0f \u672c\u983b\u9053\u5167\u5bb9\u50c5\u4f9b\u53c3\u8003\uff0c"
        f"\u4e0d\u69cb\u6210\u6295\u8cc7\u5efa\u8b70\n\n"
        f"#\u7f8e\u80a1 #\u53f0\u80a1 #\u76e4\u524d\u901f\u5831 #S&P500 "
        f"#\u8cbb\u534a #\u53f0\u7a4d\u96fbADR #VIX #JARVIS\u9078\u80a1"
    )
    tags = [
        "\u7f8e\u80a1", "\u53f0\u80a1", "\u76e4\u524d\u901f\u5831",
        "S&P500", "\u8cbb\u534a", "\u53f0\u7a4d\u96fb", "ADR",
        "VIX", "\u6295\u8cc7", "\u80a1\u7968", "JARVIS\u9078\u80a1", "Shorts",
    ]

    # Upload
    result = upload_to_youtube(output_path, title, description, tags, req.privacy)

    # Flatten data for response
    flat_data = {}
    for ticker, d in data.items():
        flat_data[ticker] = {
            "name": d["name"],
            "close": d["close"],
            "change_pct": round(d["change_pct"], 2),
        }

    return PremarketShortsResponse(
        video_id=result.get("video_id", ""),
        youtube_url=result.get("youtube_url", ""),
        title=title,
        data=flat_data,
    )
