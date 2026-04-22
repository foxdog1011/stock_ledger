"""YouTube upload orchestration logic extracted from video_gen router."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import HTTPException

from apps.api.services.video_engine.constants import SHORTS_SLOTS

logger = logging.getLogger(__name__)


def _cleanup_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


def compute_publish_at(publish_time: str | None) -> tuple[str | None, str | None]:
    """Parse publish_time (HH:MM) into ISO publishAt string.

    Returns (publish_at, privacy_override).
    privacy_override is "private" if publish_at is set, else None.
    """
    if not publish_time:
        return None, None
    try:
        hour, minute = (int(x) for x in publish_time.split(":"))
        today = date.today()
        taipei_tz = timezone(timedelta(hours=8))
        publish_dt = datetime(today.year, today.month, today.day,
                              hour, minute, 0, tzinfo=taipei_tz)
        return publish_dt.isoformat(), "private"
    except (ValueError, TypeError):
        logger.warning("Could not parse publish_time: %s", publish_time)
        return None, None


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    publish_at: str | None,
    slot: str,
    thumbnail_path: str | None = None,
) -> str:
    """Upload video to YouTube, set thumbnail, add to playlist. Returns video_id."""
    from apps.api.routers.youtube_upload import (
        _build_youtube_client,
        _upload_video,
        _set_thumbnail,
        _ensure_playlists,
        _add_to_playlist,
    )

    youtube = _build_youtube_client()
    video_id = _upload_video(
        youtube, video_path, title[:100], description,
        tags, privacy, publish_at,
    )

    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            _set_thumbnail(youtube, video_id, thumbnail_path)
        except Exception:
            logger.exception("Thumbnail upload failed -- continuing")

    slot_playlist_map = {
        "morning": "每日快報",
        "afternoon": "每日快報",
        "long_tuesday": "個股分析",
        "long_friday": "大盤週報",
    }
    playlist_name = slot_playlist_map.get(slot)
    if playlist_name:
        try:
            playlists = _ensure_playlists(youtube)
            pid = playlists.get(playlist_name)
            if pid:
                _add_to_playlist(youtube, video_id, pid)
        except Exception:
            logger.exception("Playlist add failed -- continuing")

    return video_id
