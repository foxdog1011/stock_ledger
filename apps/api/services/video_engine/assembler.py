"""FFmpeg video assembly pipeline — builds MP4 from frames + optional audio."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

import numpy as np

from apps.api.services.video_engine.constants import FPS

logger = logging.getLogger(__name__)


def get_audio_duration(audio_path: str) -> float:
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


def build_mp4(
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
        total_audio = get_audio_duration(audio_path)
        if total_audio > 0:
            n = len(frames)
            per = max(3, total_audio / n)
            slide_seconds = [max(3, round(per))] * n
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
        shutil.move(silent, output)
        return

    # Merge audio
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
            shutil.copy(silent, output)
    except Exception:
        logger.exception("Audio merge error -- using silent video")
        shutil.copy(silent, output)
    finally:
        Path(silent).unlink(missing_ok=True)
        Path(audio_path).unlink(missing_ok=True)
