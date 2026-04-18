"""Pre-market US overview Shorts generator.

Fetches US market data (S&P 500, VIX, SOX, 10Y Treasury, TSM ADR),
generates a 60-second vertical video with TTS narration,
and uploads to YouTube.

Usage:
    cd C:/Users/Administrator/stock_ledger
    python scripts/premarket_shorts.py [--no-upload] [--privacy unlisted]
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from PIL import Image

import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("premarket_shorts")

# ── Constants ─────────────────────────────────────────────────────────────────

_SHORTS_W, _SHORTS_H = 1080, 1920
_BG       = "#0f1423"
_ACCENT   = "#00d4ff"
_GREEN    = "#00e676"
_RED      = "#ff5252"
_TEXT     = "#ffffff"
_MUTED    = "#b0b4c8"
_CARD_BG  = "#1a2040"
_GRID     = "#2a3050"
_ORANGE   = "#ff9800"

# Tickers to fetch
TICKERS = {
    "^GSPC":  {"name": "S&P 500",     "type": "index"},
    "^VIX":   {"name": "VIX 恐慌指數", "type": "fear"},
    "^SOX":   {"name": "費半指數",     "type": "index"},
    "^TNX":   {"name": "10Y 美債殖利率", "type": "yield"},
    "TSM":    {"name": "台積電 ADR",   "type": "adr"},
}

# CJK font paths
_CJK_FONT_PATHS = [
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]
_CJK_FONT_PATH = ""
_CJK_FONT_PROP = None


def _setup_fonts() -> None:
    global _CJK_FONT_PATH, _CJK_FONT_PROP
    if _CJK_FONT_PROP:
        return
    for p in _CJK_FONT_PATHS:
        if Path(p).exists():
            _CJK_FONT_PATH = p
            _CJK_FONT_PROP = fm.FontProperties(fname=p)
            fm.fontManager.addfont(p)
            plt.rcParams["font.family"] = _CJK_FONT_PROP.get_name()
            logger.info("Using CJK font: %s", p)
            return
    logger.warning("No CJK font found — text may not render correctly")


def _fp(size: int) -> fm.FontProperties:
    if _CJK_FONT_PATH:
        return fm.FontProperties(fname=_CJK_FONT_PATH, size=size)
    return fm.FontProperties(size=size)


# ── Data fetching ─────────────────────────────────────────────────────────────

def fetch_us_market_data() -> dict:
    """Fetch latest US market data via yfinance."""
    results = {}
    for ticker, meta in TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if hist.empty:
                logger.warning("No data for %s", ticker)
                continue
            latest = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else hist.iloc[0]
            close = float(latest["Close"])
            prev_close = float(prev["Close"])
            change = close - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0

            # Get 5-day history for mini chart
            closes = [float(r["Close"]) for _, r in hist.iterrows()]

            results[ticker] = {
                "name": meta["name"],
                "type": meta["type"],
                "close": close,
                "prev_close": prev_close,
                "change": change,
                "change_pct": change_pct,
                "history": closes,
                "date": str(latest.name.date()) if hasattr(latest.name, 'date') else str(date.today()),
            }
            logger.info("%s: %.2f (%.2f%%)", meta["name"], close, change_pct)
        except Exception as e:
            logger.error("Failed to fetch %s: %s", ticker, e)
    return results


# ── Slide generation ──────────────────────────────────────────────────────────

def _make_premarket_slide(data: dict) -> np.ndarray:
    """Create a single vertical Shorts slide (1080x1920) with US market overview."""
    _setup_fonts()
    fig = plt.figure(figsize=(7.2, 12.8), facecolor=_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(_BG)
    ax.axis("off")

    # Header — brand
    ax.text(0.5, 0.97, "JARVIS 選股", transform=ax.transAxes,
            ha="center", va="center", color=_ACCENT, fontproperties=_fp(24), fontweight="bold")
    ax.axhline(0.955, xmin=0.08, xmax=0.92, color=_ACCENT, lw=3)

    # Title
    today_str = date.today().strftime("%m/%d")
    ax.text(0.5, 0.91, f"美股盤前速報", transform=ax.transAxes,
            ha="center", va="center", color=_TEXT, fontproperties=_fp(38), fontweight="bold")
    ax.text(0.5, 0.865, today_str, transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(22))

    # Market data cards
    order = ["^GSPC", "^SOX", "^VIX", "^TNX", "TSM"]
    y_start = 0.80
    y_step = 0.135

    for i, ticker in enumerate(order):
        if ticker not in data:
            continue
        d = data[ticker]
        y = y_start - i * y_step
        is_up = d["change_pct"] >= 0

        # For VIX, up is bad (red), down is good (green)
        if d["type"] == "fear":
            val_color = _RED if is_up else _GREEN
        else:
            val_color = _GREEN if is_up else _RED

        sign = "+" if d["change_pct"] >= 0 else ""

        # Name (left)
        ax.text(0.08, y, d["name"], transform=ax.transAxes,
                ha="left", va="center", color=_TEXT, fontproperties=_fp(22), fontweight="bold")

        # Price (center-right)
        if d["type"] == "yield":
            price_str = f"{d['close']:.2f}%"
        else:
            price_str = f"{d['close']:,.2f}"
        ax.text(0.65, y, price_str, transform=ax.transAxes,
                ha="right", va="center", color=_TEXT, fontproperties=_fp(24), fontweight="bold")

        # Change % (right)
        ax.text(0.92, y, f"{sign}{d['change_pct']:.2f}%", transform=ax.transAxes,
                ha="right", va="center", color=val_color, fontproperties=_fp(22), fontweight="bold")

        # Divider line
        if i < len(order) - 1:
            ax.axhline(y - y_step / 2 + 0.01, xmin=0.08, xmax=0.92, color=_GRID, lw=1, alpha=0.5)

    # ── Verdict section ───────────────────────────────────────────────────────
    sp = data.get("^GSPC", {})
    vix = data.get("^VIX", {})
    sox = data.get("^SOX", {})

    # Determine market sentiment
    sp_pct = sp.get("change_pct", 0)
    vix_close = vix.get("close", 20)
    sox_pct = sox.get("change_pct", 0)

    if sp_pct > 0.5 and sox_pct > 0.5 and vix_close < 20:
        verdict = "偏多看待"
        verdict_color = _GREEN
        verdict_icon = "▲"
    elif sp_pct < -0.5 or vix_close > 25:
        verdict = "偏空看待"
        verdict_color = _RED
        verdict_icon = "▼"
    else:
        verdict = "觀望震盪"
        verdict_color = _ORANGE
        verdict_icon = "■"

    # Verdict box
    y_verdict = 0.14
    ax.text(0.5, y_verdict + 0.04, "今日台股方向", transform=ax.transAxes,
            ha="center", va="center", color=_MUTED, fontproperties=_fp(22))
    ax.text(0.5, y_verdict - 0.02, f"{verdict_icon} {verdict}", transform=ax.transAxes,
            ha="center", va="center", color=verdict_color, fontproperties=_fp(44), fontweight="bold")

    # Footer CTA
    fig.text(0.5, 0.06, "━" * 25, ha="center", va="center",
             color=_ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.035, "訂閱 JARVIS 選股｜每天盤前 60 秒掌握美股動態",
             ha="center", va="center", color=_ACCENT,
             fontproperties=_fp(18), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((_SHORTS_W, _SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)


def _make_mini_chart_slide(data: dict) -> np.ndarray:
    """Create a second slide showing 5-day mini charts for key indices."""
    _setup_fonts()
    fig = plt.figure(figsize=(7.2, 12.8), facecolor=_BG)

    # Header
    ax_top = fig.add_subplot(111)
    ax_top.set_facecolor(_BG)
    ax_top.axis("off")
    ax_top.text(0.5, 0.97, "JARVIS 選股", transform=ax_top.transAxes,
                ha="center", va="center", color=_ACCENT, fontproperties=_fp(24), fontweight="bold")
    ax_top.axhline(0.955, xmin=0.08, xmax=0.92, color=_ACCENT, lw=3)
    ax_top.text(0.5, 0.91, "近 5 日走勢", transform=ax_top.transAxes,
                ha="center", va="center", color=_TEXT, fontproperties=_fp(34), fontweight="bold")

    # Mini charts for S&P, SOX, TSM
    chart_tickers = ["^GSPC", "^SOX", "TSM"]
    chart_data = [(t, data[t]) for t in chart_tickers if t in data]

    for i, (ticker, d) in enumerate(chart_data):
        ax_chart = fig.add_axes([0.12, 0.55 - i * 0.24, 0.76, 0.18], facecolor=_CARD_BG)
        hist = d["history"]
        x = list(range(len(hist)))
        color = _GREEN if hist[-1] >= hist[0] else _RED
        ax_chart.plot(x, hist, color=color, lw=3, zorder=3)
        ax_chart.fill_between(x, hist, min(hist), color=color, alpha=0.15, zorder=2)
        ax_chart.set_title(d["name"], fontproperties=_fp(22), color=_TEXT, pad=10)
        ax_chart.tick_params(axis="y", colors=_MUTED, labelsize=14)
        ax_chart.tick_params(axis="x", colors=_MUTED, labelsize=14)
        ax_chart.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        for spine in ax_chart.spines.values():
            spine.set_edgecolor(_GRID)
        ax_chart.spines["top"].set_visible(False)
        ax_chart.spines["right"].set_visible(False)
        ax_chart.grid(axis="y", color=_GRID, lw=0.5, alpha=0.5)

    # Footer
    fig.text(0.5, 0.06, "━" * 25, ha="center", va="center",
             color=_ACCENT, fontsize=14, alpha=0.4)
    fig.text(0.5, 0.035, "訂閱 JARVIS 選股｜每天盤前 60 秒掌握美股動態",
             ha="center", va="center", color=_ACCENT,
             fontproperties=_fp(18), alpha=0.9)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100,
                facecolor=fig.get_facecolor(), edgecolor="none")
    buf.seek(0)
    img = Image.open(buf).convert("RGB").resize((_SHORTS_W, _SHORTS_H), Image.LANCZOS)
    plt.close(fig)
    return np.array(img)


# ── Script generation ─────────────────────────────────────────────────────────

def generate_script(data: dict) -> str:
    """Generate a 60-second narration script using OpenAI."""
    from openai import OpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.warning("No OPENAI_API_KEY — using template script")
        return _template_script(data)

    client = OpenAI(api_key=api_key)

    # Build data summary for prompt
    lines = []
    for ticker in ["^GSPC", "^SOX", "^VIX", "^TNX", "TSM"]:
        if ticker not in data:
            continue
        d = data[ticker]
        sign = "+" if d["change_pct"] >= 0 else ""
        lines.append(f"- {d['name']}: {d['close']:.2f} ({sign}{d['change_pct']:.2f}%)")

    data_summary = "\n".join(lines)

    prompt = f"""你是 JARVIS 選股的 AI 主播，請根據以下美股收盤數據，撰寫一段 60 秒的台灣盤前速報旁白。

數據：
{data_summary}

要求：
1. 使用繁體中文，口語化但專業
2. 開場：「各位投資朋友早安，我是 JARVIS，今天盤前 60 秒重點來了」
3. 依序講解：美股大盤表現 → 費半/科技 → VIX 情緒 → 台積電 ADR → 今天台股方向判斷
4. 結尾：「以上是今天的盤前速報，記得訂閱 JARVIS 選股，我們明天見」
5. 總字數控制在 180-220 字（約 45 秒語速，語速 +15% 後約 40 秒）
6. 不要加標題、標點符號說明或格式標記，直接輸出旁白文字
7. 加入「本頻道內容僅供參考，不構成投資建議」的免責聲明（融入結尾）"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.7,
        )
        script = resp.choices[0].message.content.strip()
        logger.info("Generated script: %d chars", len(script))
        return script
    except Exception as e:
        logger.error("OpenAI failed: %s — using template", e)
        return _template_script(data)


def _template_script(data: dict) -> str:
    """Fallback template script when OpenAI is unavailable."""
    sp = data.get("^GSPC", {})
    sox = data.get("^SOX", {})
    vix = data.get("^VIX", {})
    tnx = data.get("^TNX", {})
    tsm = data.get("TSM", {})

    sp_dir = "上漲" if sp.get("change_pct", 0) >= 0 else "下跌"
    sox_dir = "上漲" if sox.get("change_pct", 0) >= 0 else "下跌"
    tsm_dir = "上漲" if tsm.get("change_pct", 0) >= 0 else "下跌"

    return (
        f"各位投資朋友早安，我是 JARVIS，盤前重點來了。"
        f"S&P 500 {sp_dir} {abs(sp.get('change_pct', 0)):.1f}%，"
        f"費半{sox_dir} {abs(sox.get('change_pct', 0)):.1f}%。"
        f"VIX 收在 {vix.get('close', 0):.1f}，"
        f"{'情緒偏謹慎' if vix.get('close', 0) > 20 else '情緒穩定'}。"
        f"台積電 ADR {tsm_dir} {abs(tsm.get('change_pct', 0)):.1f}%。"
        f"綜合來看，今天台股{'偏多' if sp.get('change_pct', 0) > 0 else '偏空'}看待。"
        f"以上是盤前速報，訂閱 JARVIS 選股，明天見。"
        f"本頻道內容僅供參考，不構成投資建議。"
    )


# ── TTS ───────────────────────────────────────────────────────────────────────

def tts_to_mp3(script: str) -> bytes | None:
    """Generate TTS audio from script."""
    import re
    # Clean non-spoken content
    cleaned = re.sub(r"[\[\]【】{}（）\(\)]", "", script)
    cleaned = re.sub(r"[#*_~`]", "", cleaned)
    cleaned = re.sub(r"\n+", "。", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return None

    try:
        import asyncio
        import edge_tts

        rate = os.getenv("EDGE_TTS_RATE", "+15%")
        voice = os.getenv("EDGE_TTS_VOICE", "zh-TW-HsiaoChenNeural")

        async def _gen():
            buf = io.BytesIO()
            communicate = edge_tts.Communicate(cleaned[:3000], voice, rate=rate)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
            return buf.getvalue()

        loop = asyncio.new_event_loop()
        try:
            audio = loop.run_until_complete(_gen())
        finally:
            loop.close()
        logger.info("TTS generated: %d bytes", len(audio))
        return audio
    except Exception:
        logger.exception("TTS failed")
        return None


# ── Video assembly ────────────────────────────────────────────────────────────

def build_mp4(frames: list[tuple[np.ndarray, int]], audio_bytes: bytes | None, output: str) -> None:
    """Write frames to MP4 with audio."""
    import imageio_ffmpeg
    import tempfile

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    fps = 15  # Shorts use lower fps

    # Determine per-slide seconds
    if audio_bytes:
        audio_path = output.replace(".mp4", "_audio.mp3")
        Path(audio_path).write_bytes(audio_bytes)
        total_audio = _get_audio_duration(ffmpeg, audio_path)
        if total_audio > 0:
            n = len(frames)
            per = max(3, total_audio / n)
            slide_seconds = [max(3, round(per))] * n
            slide_seconds[-1] = max(3, round(total_audio - sum(slide_seconds[:-1])))
        else:
            slide_seconds = [s for _, s in frames]
            Path(audio_path).unlink(missing_ok=True)
            audio_bytes = None
    else:
        slide_seconds = [s for _, s in frames]
        audio_path = ""

    # Write slides as PNGs
    slide_dir = tempfile.mkdtemp(prefix="premarket_slides_")
    slide_paths = []
    try:
        for idx, (frame_arr, _) in enumerate(frames):
            p = f"{slide_dir}/slide_{idx:03d}.png"
            Image.fromarray(frame_arr.astype(np.uint8), "RGB").save(p, format="PNG", optimize=False)
            slide_paths.append(p)

        concat_path = f"{slide_dir}/concat.txt"
        with open(concat_path, "w", encoding="utf-8") as fh:
            for p, secs in zip(slide_paths, slide_seconds):
                fh.write(f"file '{p}'\n")
                fh.write(f"duration {max(1, int(secs))}\n")
            fh.write(f"file '{slide_paths[-1]}'\n")

        cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", concat_path]
        if audio_bytes:
            cmd += ["-i", audio_path]
        cmd += ["-vf", f"fps={fps},format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28"]
        if audio_bytes:
            total_audio = _get_audio_duration(ffmpeg, audio_path)
            cmd += ["-c:a", "aac", "-map", "0:v:0", "-map", "1:a:0"]
            if total_audio > 0:
                cmd += ["-t", str(total_audio)]
        cmd += [output]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")[-500:] if result.stderr else ""
            logger.error("ffmpeg failed: %s", err)
            raise RuntimeError(f"ffmpeg failed: {err[-200:]}")

        logger.info("Video written: %s", output)
    finally:
        if audio_path:
            Path(audio_path).unlink(missing_ok=True)
        for p in slide_paths:
            Path(p).unlink(missing_ok=True)
        Path(f"{slide_dir}/concat.txt").unlink(missing_ok=True)
        try:
            os.rmdir(slide_dir)
        except OSError:
            pass


def _get_audio_duration(ffmpeg: str, audio_path: str) -> float:
    """Return audio duration in seconds."""
    import shutil

    # 1) Try system ffprobe
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, timeout=10,
            )
            val = result.stdout.decode("utf-8", errors="replace").strip()
            if val:
                return float(val)
        except Exception:
            pass

    # 2) Try ffprobe derived from ffmpeg path
    candidate = ffmpeg.replace("ffmpeg", "ffprobe")
    if Path(candidate).exists():
        try:
            result = subprocess.run(
                [candidate, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
                capture_output=True, timeout=10,
            )
            val = result.stdout.decode("utf-8", errors="replace").strip()
            if val:
                return float(val)
        except Exception:
            pass

    # 3) Fallback: use ffmpeg -i to parse duration from stderr
    try:
        result = subprocess.run(
            [ffmpeg, "-i", audio_path, "-f", "null", "-"],
            capture_output=True, timeout=10,
        )
        import re
        stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        m = re.search(r"time=(\d+):(\d+):(\d+)\.(\d+)", stderr)
        if m:
            h, mi, s, cs = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            return h * 3600 + mi * 60 + s + cs / 100
    except Exception:
        pass

    logger.warning("Could not determine audio duration for %s", audio_path)
    return 0.0


# ── YouTube upload ────────────────────────────────────────────────────────────

def upload_to_youtube(video_path: str, title: str, description: str,
                      tags: list[str], privacy: str = "unlisted") -> dict:
    """Upload video to YouTube directly using the youtube_upload module."""
    from apps.api.routers.youtube_upload import (
        _build_youtube_client,
        _upload_video,
        _ensure_playlists,
        _add_to_playlist,
    )

    youtube = _build_youtube_client()
    video_id = _upload_video(
        youtube, video_path, title[:100], description, tags, privacy, None,
    )

    # Add to playlist
    try:
        playlists = _ensure_playlists(youtube)
        pid = playlists.get("每日快報")
        if pid:
            _add_to_playlist(youtube, video_id, pid)
    except Exception:
        logger.warning("Playlist add failed — continuing")

    yt_url = f"https://youtu.be/{video_id}"
    logger.info("Uploaded to YouTube: %s", yt_url)

    # Clean up video file
    Path(video_path).unlink(missing_ok=True)

    return {"video_id": video_id, "youtube_url": yt_url, "title": title, "privacy": privacy}


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate pre-market US overview Shorts")
    parser.add_argument("--no-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--privacy", default="unlisted", choices=["public", "unlisted", "private"])
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    logger.info("=== Pre-market Shorts Generator ===")

    # Skip only on Sunday — Saturday still has Friday's US market data
    today = date.today()
    if today.weekday() == 6:  # Sunday only
        logger.info("Today is Sunday — no new US market data, skipping.")
        sys.exit(0)

    # Step 1: Fetch data
    logger.info("Step 1: Fetching US market data...")
    data = fetch_us_market_data()
    if not data:
        logger.error("No market data available — aborting")
        sys.exit(1)
    logger.info("Fetched %d tickers", len(data))

    # Check if market was actually open (holiday detection)
    sp = data.get("^GSPC", {})
    if sp and sp.get("change") == 0 and sp.get("change_pct") == 0:
        logger.info("S&P change is exactly 0 — likely a holiday, skipping.")
        sys.exit(0)

    # Step 2: Generate slides
    logger.info("Step 2: Generating slides...")
    slide1 = _make_premarket_slide(data)
    slide2 = _make_mini_chart_slide(data)
    frames = [(slide1, 30), (slide2, 30)]  # 30 seconds each
    logger.info("Generated %d slides", len(frames))

    # Step 3: Generate script
    logger.info("Step 3: Generating script...")
    script = generate_script(data)
    logger.info("Script:\n%s", script)

    # Step 4: TTS
    logger.info("Step 4: Generating TTS audio...")
    audio = tts_to_mp3(script)

    # Step 5: Build MP4
    logger.info("Step 5: Building MP4...")
    import tempfile
    today_str = date.today().strftime("%Y%m%d")
    output_path = str(Path(tempfile.gettempdir()) / f"premarket_shorts_{today_str}.mp4")
    build_mp4(frames, audio, output_path)

    if not Path(output_path).exists():
        logger.error("Video file not created — aborting")
        sys.exit(1)

    file_size = Path(output_path).stat().st_size
    logger.info("Video: %s (%.1f MB)", output_path, file_size / 1024 / 1024)

    # Step 6: Upload
    if args.no_upload:
        logger.info("Skipping upload (--no-upload)")
        print(f"\nVideo saved: {output_path}")
        return

    today_display = date.today().strftime("%m/%d")
    sp = data.get("^GSPC", {})
    sox = data.get("^SOX", {})
    sp_sign = "+" if sp.get("change_pct", 0) >= 0 else ""
    sox_sign = "+" if sox.get("change_pct", 0) >= 0 else ""

    title = f"【盤前速報】{today_display} S&P {sp_sign}{sp.get('change_pct', 0):.1f}% 費半 {sox_sign}{sox.get('change_pct', 0):.1f}% 今天台股怎麼看？#Shorts"
    description = (
        f"📊 {today_display} 美股盤前 60 秒速報\n\n"
        f"{script}\n\n"
        f"⚠️ 本頻道內容僅供參考，不構成投資建議\n\n"
        f"#美股 #台股 #盤前速報 #S&P500 #費半 #台積電ADR #VIX #JARVIS選股"
    )
    tags = ["美股", "台股", "盤前速報", "S&P500", "費半", "台積電", "ADR",
            "VIX", "投資", "股票", "JARVIS選股", "Shorts"]

    logger.info("Step 6: Uploading to YouTube...")
    result = upload_to_youtube(output_path, title, description, tags, args.privacy)
    yt_url = result.get('youtube_url', result.get('url', ''))
    logger.info("Upload complete! URL: %s | Title: %s | Privacy: %s",
                yt_url, result.get('title', title), result.get('privacy', args.privacy))


if __name__ == "__main__":
    main()
