"""FFmpeg video assembly pipeline — builds MP4 from frames + optional audio.

Uses ffmpeg concat demuxer with static images (one file per slide) instead of
duplicating frames in memory.  Falls back to the legacy frame-duplication
approach when the concat pipeline fails.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_slide_seconds(
    frames: list[tuple[np.ndarray, int]],
    audio_bytes: bytes | None,
    output: str,
) -> tuple[list[int], str | None]:
    """Compute per-slide durations and optionally write audio to disk.

    Returns (slide_seconds, audio_path_or_None).
    """
    if audio_bytes:
        audio_path = output.replace(".mp4", "_audio.mp3")
        Path(audio_path).write_bytes(audio_bytes)
        total_audio = get_audio_duration(audio_path)
        if total_audio > 0:
            n = len(frames)
            per = max(3, total_audio / n)
            slide_seconds = [max(3, round(per))] * n
            slide_seconds[-1] = max(3, round(total_audio - sum(slide_seconds[:-1])))
            return slide_seconds, audio_path
        # Audio file exists but duration is zero — discard it
        Path(audio_path).unlink(missing_ok=True)

    slide_seconds = [s for _, s in frames]
    return slide_seconds, None


def _save_slide_images(
    frames: list[tuple[np.ndarray, int]],
    tmp_dir: str,
) -> list[str]:
    """Write each unique slide frame as a PNG and return the list of paths."""
    import matplotlib.image as mpimg

    paths: list[str] = []
    for idx, (frame_arr, _) in enumerate(frames):
        img_path = str(Path(tmp_dir) / f"slide_{idx:04d}.png")
        # frame_arr is RGB uint8 from matplotlib — imsave handles it directly
        mpimg.imsave(img_path, frame_arr)
        paths.append(img_path)
    return paths


def _build_concat_file(
    image_paths: list[str],
    slide_seconds: list[int],
    concat_path: str,
) -> None:
    """Write an ffmpeg concat-demuxer list file.

    Format:
        file '/path/to/slide.png'
        duration 10
    """
    lines: list[str] = []
    for img, secs in zip(image_paths, slide_seconds):
        # Use forward slashes — ffmpeg on Windows accepts them
        safe = img.replace("\\", "/")
        lines.append(f"file '{safe}'")
        lines.append(f"duration {secs}")
    # Repeat last entry so the final frame is held (ffmpeg concat quirk)
    if image_paths:
        safe = image_paths[-1].replace("\\", "/")
        lines.append(f"file '{safe}'")
    Path(concat_path).write_text("\n".join(lines), encoding="utf-8")


def _build_silent_concat(
    ffmpeg: str,
    concat_path: str,
    silent_path: str,
    frame_size: tuple[int, int],
) -> subprocess.CompletedProcess:
    """Create a silent MP4 from the concat file using ffmpeg."""
    width, height = frame_size
    # Ensure dimensions are even (required by libx264)
    width = width if width % 2 == 0 else width + 1
    height = height if height % 2 == 0 else height + 1

    cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_path,
        "-vf", f"scale={width}:{height},format=yuv420p",
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "20",
        "-r", str(FPS),
        "-movflags", "+faststart",
        silent_path,
    ]
    return subprocess.run(cmd, capture_output=True, timeout=300)


def _build_silent_legacy(
    frames: list[tuple[np.ndarray, int]],
    slide_seconds: list[int],
    silent_path: str,
) -> None:
    """Legacy frame-duplication approach (fallback)."""
    import imageio.v2 as imageio

    writer = imageio.get_writer(
        silent_path, fps=FPS, codec="libx264",
        output_params=["-pix_fmt", "yuv420p", "-crf", "20"],
        macro_block_size=None,
    )
    for (frame_arr, _), secs in zip(frames, slide_seconds):
        for _ in range(max(1, secs * FPS)):
            writer.append_data(frame_arr)
    writer.close()


def _merge_audio(
    ffmpeg: str,
    silent_path: str,
    audio_path: str,
    output: str,
) -> None:
    """Merge silent video with audio track, falling back to silent-only."""
    try:
        result = subprocess.run(
            [ffmpeg, "-y",
             "-i", silent_path,
             "-i", audio_path,
             "-c:v", "copy",
             "-c:a", "aac",
             "-map", "0:v:0",
             "-map", "1:a:0",
             output],
            capture_output=True, timeout=120,
        )
        if result.returncode != 0:
            err_msg = (
                result.stderr.decode("utf-8", errors="replace")[-500:]
                if result.stderr else ""
            )
            logger.warning(
                "ffmpeg merge failed (%d): %s", result.returncode, err_msg,
            )
            shutil.copy(silent_path, output)
    except Exception:
        logger.exception("Audio merge error -- using silent video")
        shutil.copy(silent_path, output)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_mp4(
    frames: list[tuple[np.ndarray, int]],
    audio_bytes: bytes | None,
    output: str,
) -> None:
    """Write frames to MP4, syncing slide durations to audio length when available.

    Primary path: ffmpeg concat demuxer (one image file per slide).
    Fallback:     legacy frame duplication via imageio.

    If audio is provided:
      - Distribute slides evenly across audio duration
      - Audio is the master timeline (no -shortest truncation)
    If no audio:
      - Use fixed SLIDE_SECONDS durations
    """
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    slide_seconds, audio_path = _resolve_slide_seconds(frames, audio_bytes, output)

    silent = output.replace(".mp4", "_silent.mp4")
    tmp_dir = tempfile.mkdtemp(dir=tempfile.gettempdir(), prefix="video_slides_")

    try:
        # ── Try concat-demuxer approach ──────────────────────────────────
        concat_ok = False
        try:
            image_paths = _save_slide_images(frames, tmp_dir)
            concat_path = str(Path(tmp_dir) / "concat.txt")
            _build_concat_file(image_paths, slide_seconds, concat_path)

            # Determine frame dimensions from the first slide
            h, w = frames[0][0].shape[:2]
            result = _build_silent_concat(ffmpeg, concat_path, silent, (w, h))

            if result.returncode == 0 and Path(silent).exists():
                concat_ok = True
                logger.info(
                    "Concat-demuxer build succeeded (%d slides)", len(frames),
                )
            else:
                err = (
                    result.stderr.decode("utf-8", errors="replace")[-500:]
                    if result.stderr else ""
                )
                logger.warning(
                    "Concat-demuxer failed (exit %d), falling back: %s",
                    result.returncode, err,
                )
        except Exception:
            logger.exception("Concat-demuxer pipeline error -- falling back")

        # ── Fallback: legacy frame duplication ───────────────────────────
        if not concat_ok:
            logger.info("Using legacy frame-duplication for %d slides", len(frames))
            _build_silent_legacy(frames, slide_seconds, silent)

        # ── Merge audio or move silent to output ─────────────────────────
        if audio_path:
            _merge_audio(ffmpeg, silent, audio_path, output)
        else:
            shutil.move(silent, output)
            return  # skip finally cleanup of silent (already moved)

    finally:
        # Clean up temp artefacts
        Path(silent).unlink(missing_ok=True)
        if audio_path:
            Path(audio_path).unlink(missing_ok=True)
        shutil.rmtree(tmp_dir, ignore_errors=True)
