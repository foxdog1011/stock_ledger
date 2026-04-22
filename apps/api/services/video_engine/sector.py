"""Sector video generation orchestration."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import HTTPException

from apps.api.services.video_engine.assembler import build_mp4
from apps.api.services.video_engine.constants import SECTOR_SYMBOLS, SLIDE_SECONDS
from apps.api.services.video_engine.data import (
    compute_foreign_net_k,
    get_chip_data,
    get_sector_chip,
)
from apps.api.services.video_engine.fonts import setup_matplotlib_fonts
from apps.api.services.video_engine.models import GenerateSectorResponse
from apps.api.services.video_engine.script_gen import openai_script
from apps.api.services.video_engine.slides import (
    make_foreign_chart,
    make_sector_breakdown_chart,
    make_sector_title_slide,
    make_shorts_slide,
    make_summary_slide,
    make_trust_dealer_chart,
)
from apps.api.services.video_engine.tts import clean_script_for_tts, tts_edge

logger = logging.getLogger(__name__)


def generate_sector(sector_name: str, slot: str, fmt: str) -> GenerateSectorResponse:
    """Full sector video generation pipeline.

    Returns GenerateSectorResponse with video_path, metadata, script, etc.
    """
    if sector_name not in SECTOR_SYMBOLS:
        raise HTTPException(400, f"Unknown sector: {sector_name}")

    symbols = SECTOR_SYMBOLS[sector_name]
    days = 5

    sector_data = get_sector_chip(symbols, sector_name, days)
    summary = sector_data["summary"]
    daily = sector_data["daily"]
    sym_list = sector_data["symbols"]

    if not daily:
        raise HTTPException(502, f"No chip data for sector {sector_name}")

    date_range = f"{daily[0]['date']} ~ {daily[-1]['date']}"
    is_shorts = fmt.lower() == "shorts"

    setup_matplotlib_fonts()

    symbols_data: list[dict] = []
    for s in sym_list:
        try:
            sd = get_chip_data(s["symbol"], days)
            symbols_data.append({**s, **sd})
        except Exception:
            pass

    foreign = summary.get("foreign_net_total", 0)
    trust = summary.get("investment_trust_net_total", 0)
    dealer = summary.get("dealer_net_total", 0)
    f_sign = "買超" if foreign >= 0 else "賣超"
    t_sign = "買超" if trust >= 0 else "賣超"
    d_sign = "買超" if dealer >= 0 else "賣超"

    foreign_k = round(foreign / 1000)
    trust_k = round(trust / 1000)
    dealer_k = round(dealer / 1000)

    if is_shorts:
        slide = make_shorts_slide(
            f"{sector_name}族群", f"{sector_name}族群", date_range, summary, daily,
            compute_foreign_net_k,
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
        script = openai_script(prompt, max_tokens=500)
    else:
        frames = [
            (make_sector_title_slide(sector_name, sym_list, date_range), SLIDE_SECONDS["title"]),
            (make_foreign_chart(daily), SLIDE_SECONDS["chart"]),
            (make_trust_dealer_chart(daily), SLIDE_SECONDS["chart"]),
            (make_sector_breakdown_chart(symbols_data, days), SLIDE_SECONDS["chart"]),
            (make_summary_slide(summary, date_range), SLIDE_SECONDS["summary"]),
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
        script = openai_script(prompt, max_tokens=2500)

    # TTS
    tts_rate = "+35%" if is_shorts else None
    spoken = clean_script_for_tts(script)
    if is_shorts:
        spoken = spoken[:500]
    audio_bytes = tts_edge(spoken, rate=tts_rate)
    if not audio_bytes:
        logger.warning("TTS failed for sector %s -- generating video without audio", sector_name)

    # Build MP4
    _tmp_sector = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    _tmp_sector.close()
    video_path = _tmp_sector.name
    build_mp4(frames, audio_bytes, video_path)

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
        slot=slot,
    )
