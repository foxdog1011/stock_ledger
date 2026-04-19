"""Update existing YouTube video metadata for JARVIS 選股 channel.

Phase 1 — LIST: Print video ID + exact title for every upload (no changes).
Phase 2 — UPDATE: Fix titles that need reformatting; skip videos whose title
          already starts with '【'.
"""
import os
import sys
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def _build_youtube_client():
    """Build authenticated YouTube API client from refresh token in env."""
    client_id     = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()

    if not all([client_id, client_secret, refresh_token]):
        print("ERROR: YouTube credentials not configured in .env")
        sys.exit(1)

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=_SCOPES,
    )
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def get_all_uploaded_video_ids(youtube) -> list[str]:
    """Return all video IDs from the channel's uploads playlist."""
    channels = youtube.channels().list(part='contentDetails', mine=True).execute()
    uploads_playlist = channels['items'][0]['contentDetails']['relatedPlaylists']['uploads']

    video_ids: list[str] = []
    request = youtube.playlistItems().list(
        part='snippet',
        playlistId=uploads_playlist,
        maxResults=50,
    )
    while request is not None:
        response = request.execute()
        for item in response.get('items', []):
            video_ids.append(item['snippet']['resourceId']['videoId'])
        request = youtube.playlistItems().list_next(request, response)

    return video_ids


def get_video_snippet(youtube, vid: str) -> dict | None:
    """Fetch the snippet for a single video; return None if not found."""
    response = youtube.videos().list(part='snippet', id=vid).execute()
    items = response.get('items', [])
    if not items:
        return None
    return items[0]['snippet']


# ---------------------------------------------------------------------------
# Title-fix rules
# Each entry is (keywords_that_must_all_appear_in_old_title, new_title).
# Keywords are checked as substrings of the existing title (case-sensitive).
# Full-width ｜ is used throughout per project spec.
# ---------------------------------------------------------------------------
_TITLE_FIX_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ('聯電', '2303'),
        '【2303 聯電】外資狂買 6.6 萬張！三大法人都在搶？｜ 籌碼分析',
    ),
    (
        ('中信金', '2891'),
        '【2891 中信金】外資買超 4,779 張！三大法人都在搶？｜ 籌碼分析',
    ),
    (
        ('鴻海', '2317'),
        '【2317 鴻海】外資狂賣 2.9 萬張！法人大逃殺什麼訊號？｜ 籌碼分析',
    ),
    (
        ('台積電', '2330'),
        '【2330 台積電】三大法人籌碼分析｜JARVIS 選股',
    ),
]

NEW_CATEGORY = '22'   # People & Blogs
BAD_TAG = 'AI投資實驗室'
GOOD_TAG = 'JARVIS選股'
EXTRA_TAGS = ['台股2026', '選股推薦', '籌碼面分析', '法人動向', '外資動向']


def resolve_new_title(old_title: str) -> str | None:
    """Return the corrected title, or None if no fix applies.

    Returns None when:
    - The title already starts with '【' (already formatted), OR
    - No keyword set matches the title.
    """
    if old_title.startswith('【'):
        return None  # already correct format — skip

    for keywords, new_title in _TITLE_FIX_RULES:
        if all(kw in old_title for kw in keywords):
            return new_title

    return None  # no rule matched


def build_new_tags(old_tags: list[str]) -> list[str]:
    """Remove bad tag, ensure good tag and extra tags are present (immutable)."""
    without_bad = [t for t in old_tags if t != BAD_TAG]
    with_good   = without_bad if GOOD_TAG in without_bad else [*without_bad, GOOD_TAG]
    with_extra  = [*with_good, *(t for t in EXTRA_TAGS if t not in with_good)]
    return with_extra


# ---------------------------------------------------------------------------
# Phase 1 — list only
# ---------------------------------------------------------------------------

def phase_list(youtube) -> list[tuple[str, str]]:
    """Fetch all uploads, print ID + exact title, return list of (id, title)."""
    print("\n" + "=" * 70)
    print("PHASE 1 — LIST (no changes)")
    print("=" * 70)

    video_ids = get_all_uploaded_video_ids(youtube)
    print(f"Found {len(video_ids)} video(s) in uploads playlist.\n")

    videos: list[tuple[str, str]] = []
    for vid in video_ids:
        snippet = get_video_snippet(youtube, vid)
        if snippet is None:
            print(f"  [{vid}]  WARNING: not found via videos.list — skipping")
            continue
        title = snippet['title']
        print(f"  [{vid}]  {title}")
        videos.append((vid, title))

    return videos


# ---------------------------------------------------------------------------
# Phase 2 — update
# ---------------------------------------------------------------------------

def phase_update(youtube, videos: list[tuple[str, str]]) -> None:
    """Apply title fixes (and tag/category updates) where rules match."""
    print("\n" + "=" * 70)
    print("PHASE 2 — UPDATE")
    print("=" * 70)

    changed = 0
    skipped = 0

    for vid, _ in videos:
        snippet = get_video_snippet(youtube, vid)
        if snippet is None:
            print(f"\n  [{vid}]  WARNING: not found — skipping")
            skipped += 1
            continue

        old_title = snippet['title']
        new_title = resolve_new_title(old_title)

        if new_title is None:
            # Either already formatted or no rule matched
            reason = "already has 【】 format" if old_title.startswith('【') else "no matching rule"
            print(f"\n  [{vid}]  SKIP ({reason})")
            print(f"           title: {old_title}")
            skipped += 1
            continue

        old_tags = snippet.get('tags', [])
        old_cat  = snippet['categoryId']
        new_tags = build_new_tags(old_tags)

        print(f"\n  [{vid}]  UPDATING")
        print(f"    BEFORE title:    {old_title}")
        print(f"    AFTER  title:    {new_title}")
        print(f"    category: {old_cat} → {NEW_CATEGORY}")
        print(f"    tags (first 5 before): {old_tags[:5]}")
        print(f"    tags (first 5 after):  {new_tags[:5]}")

        # Immutable snippet update — build a new dict, never mutate old_snippet
        updated_snippet = {
            **snippet,
            'title':      new_title,
            'tags':       new_tags,
            'categoryId': NEW_CATEGORY,
        }

        youtube.videos().update(
            part='snippet',
            body={'id': vid, 'snippet': updated_snippet},
        ).execute()

        print("    -> Updated successfully!")
        changed += 1

    print(f"\nSummary: {changed} video(s) updated, {skipped} skipped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("Building YouTube client...")
    youtube = _build_youtube_client()

    # Phase 1: list all videos (read-only)
    videos = phase_list(youtube)

    if not videos:
        print("\nNo videos found. Exiting.")
        return

    # Phase 2: apply title fixes
    phase_update(youtube, videos)

    print("\nDone!")


if __name__ == '__main__':
    main()
