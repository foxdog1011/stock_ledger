"""YouTube Data API v3 upload endpoint.

POST /api/video/youtube-upload
  body: multipart/form-data
    file      : MP4 video file
    title     : video title
    description : video description (optional)
    tags      : comma-separated tags (optional)
    thumbnail : PNG thumbnail file (optional)
    privacy   : "public" | "unlisted" | "private" (default: "private")

Requires env vars (set in .env):
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET
    YOUTUBE_REFRESH_TOKEN

One-time setup: run  python scripts/youtube_auth.py  to get the refresh token.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter()

_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# Playlist IDs — populated on first use via _ensure_playlists()
_PLAYLIST_CACHE: dict[str, str] = {}

_PLAYLIST_DEFINITIONS = {
    "個股分析": "JARVIS 選股個股深度籌碼分析，每日更新三大法人買賣超數據。",
    "族群分析": "台股產業族群籌碼分析，外資投信動向一次看。",
    "每日快報": "每天 60 秒掌握法人動態，JARVIS 選股 Shorts。",
    "大盤週報": "每週五回顧台股大盤與本週選股表現。",
}


def _build_youtube_client():
    """Build authenticated YouTube API client from refresh token in env."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_id     = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

    if not all([client_id, client_secret, refresh_token]):
        raise HTTPException(
            503,
            "YouTube credentials not configured. "
            "Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN in .env"
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=_SCOPES,
    )
    try:
        creds.refresh(Request())
    except Exception as exc:
        raise HTTPException(
            401,
            f"YouTube token refresh failed — re-run youtube_auth.py: {exc}"
        ) from exc
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _upload_video(
    youtube,
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    publish_at: str | None = None,
) -> str:
    """Upload video via resumable upload. Returns YouTube video ID.

    Args:
        publish_at: RFC 3339 datetime (e.g. "2026-04-07T08:00:00+08:00").
                    If provided and privacy is "public", video uploads as
                    "private" and YouTube auto-publishes at the scheduled time.
    """
    from googleapiclient.http import MediaFileUpload

    status: dict = {"selfDeclaredMadeForKids": False}
    if publish_at and privacy == "public":
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    else:
        status["privacyStatus"] = privacy

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "25",   # 25 = News & Politics (closest to finance)
            "defaultLanguage": "zh-TW",
        },
        "status": status,
    }

    media = MediaFileUpload(video_path, chunksize=1024 * 1024, resumable=True,
                            mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        try:
            _, response = request.next_chunk(num_retries=3)
        except Exception as exc:
            error_str = str(exc)
            if "quotaExceeded" in error_str or "403" in error_str:
                raise HTTPException(429, f"YouTube API quota exceeded: {exc}") from exc
            if "401" in error_str or "invalid_grant" in error_str:
                raise HTTPException(401, f"YouTube credentials expired: {exc}") from exc
            raise

    return response["id"]


def _set_thumbnail(youtube, video_id: str, thumb_path: str) -> None:
    from googleapiclient.http import MediaFileUpload
    media = MediaFileUpload(thumb_path, mimetype="image/png")
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()


def _ensure_playlists(youtube) -> dict[str, str]:
    """Create playlists if they don't exist. Returns {name: playlist_id}.

    Gracefully returns empty dict if scope is insufficient.
    """
    if _PLAYLIST_CACHE:
        return _PLAYLIST_CACHE

    try:
        # Fetch existing playlists
        existing = {}
        req = youtube.playlists().list(part="snippet", mine=True, maxResults=50)
        resp = req.execute()
        for item in resp.get("items", []):
            existing[item["snippet"]["title"]] = item["id"]

        # Create missing playlists
        for name, desc in _PLAYLIST_DEFINITIONS.items():
            if name in existing:
                _PLAYLIST_CACHE[name] = existing[name]
            else:
                body = {
                    "snippet": {"title": name, "description": desc},
                    "status": {"privacyStatus": "public"},
                }
                result = youtube.playlists().insert(part="snippet,status", body=body).execute()
                _PLAYLIST_CACHE[name] = result["id"]
                logger.info("Created playlist: %s (%s)", name, result["id"])
    except Exception:
        logger.warning("Playlist management failed (may need youtube scope) — skipping")

    return _PLAYLIST_CACHE


def _add_to_playlist(youtube, video_id: str, playlist_id: str) -> None:
    """Add a video to a playlist."""
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        }
    }
    youtube.playlistItems().insert(part="snippet", body=body).execute()


@router.get("/health/youtube", summary="Check YouTube credential health")
def youtube_health() -> JSONResponse:
    """Verify YouTube OAuth credentials are configured and valid."""
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

    missing = [
        name
        for name, val in [
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
        ]
        if not val
    ]
    if missing:
        return JSONResponse(
            {"status": "error", "detail": f"Missing env vars: {', '.join(missing)}"},
            status_code=200,
        )

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=_SCOPES,
        )
        creds.refresh(Request())

        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = youtube.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        channel_title = items[0]["snippet"]["title"] if items else "unknown"

        return JSONResponse({"status": "ok", "channel": channel_title})

    except Exception as exc:
        logger.warning("YouTube health check failed: %s", exc)
        return JSONResponse(
            {"status": "error", "detail": str(exc)},
            status_code=200,
        )


@router.post("/video/youtube-upload", summary="Upload video to YouTube")
async def youtube_upload(
    file: UploadFile = File(..., description="MP4 video file"),
    title: str = Form(..., description="YouTube video title"),
    description: str = Form("", description="Video description"),
    tags: str = Form("台股,三大法人,籌碼分析,AI投資實驗室", description="Comma-separated tags"),
    privacy: str = Form("private", description="public | unlisted | private"),
    thumbnail: UploadFile | None = File(None, description="Thumbnail PNG (optional)"),
) -> JSONResponse:
    """
    Upload an MP4 to YouTube and optionally set a custom thumbnail.

    Returns { video_id, url, title, privacy }.
    """
    privacy = privacy.lower()
    if privacy not in ("public", "unlisted", "private"):
        raise HTTPException(400, "privacy must be public, unlisted, or private")

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # Save uploaded files to temp paths
    tmp_video = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False, dir=tempfile.gettempdir())
    tmp_video.write(await file.read())
    tmp_video.close()

    tmp_thumb_path: str | None = None
    if thumbnail:
        tmp_thumb = tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir=tempfile.gettempdir())
        tmp_thumb.write(await thumbnail.read())
        tmp_thumb.close()
        tmp_thumb_path = tmp_thumb.name

    try:
        youtube = _build_youtube_client()
        video_id = _upload_video(youtube, tmp_video.name, title, description, tag_list, privacy)
        logger.info("Uploaded video to YouTube: %s (%s)", title, video_id)

        if tmp_thumb_path:
            try:
                _set_thumbnail(youtube, video_id, tmp_thumb_path)
                logger.info("Thumbnail set for video %s", video_id)
            except Exception:
                logger.exception("Thumbnail upload failed for %s — video uploaded OK", video_id)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("YouTube upload failed")
        raise HTTPException(500, f"YouTube upload failed: {exc}") from exc
    finally:
        Path(tmp_video.name).unlink(missing_ok=True)
        if tmp_thumb_path:
            Path(tmp_thumb_path).unlink(missing_ok=True)

    url = f"https://www.youtube.com/watch?v={video_id}"
    return JSONResponse({
        "video_id": video_id,
        "url": url,
        "title": title,
        "privacy": privacy,
    })


@router.get("/health/youtube", summary="Check YouTube credentials")
def health_youtube() -> JSONResponse:
    """Non-throwing health check for YouTube OAuth credentials.

    Returns {"status": "ok", "channel": "..."} or {"status": "error", "detail": "..."}.
    """
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

    missing = [
        name for name, val in [
            ("YOUTUBE_CLIENT_ID", client_id),
            ("YOUTUBE_CLIENT_SECRET", client_secret),
            ("YOUTUBE_REFRESH_TOKEN", refresh_token),
        ] if not val
    ]
    if missing:
        return JSONResponse({"status": "error", "detail": f"Missing env vars: {', '.join(missing)}"})

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=_SCOPES,
        )
        creds.refresh(Request())
        yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = yt.channels().list(part="snippet", mine=True).execute()
        items = resp.get("items", [])
        channel_name = items[0]["snippet"]["title"] if items else "unknown"
        return JSONResponse({"status": "ok", "channel": channel_name})
    except Exception as exc:
        logger.warning("YouTube health check failed: %s", exc)
        return JSONResponse({"status": "error", "detail": str(exc)})
