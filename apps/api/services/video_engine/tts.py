"""Text-to-speech audio generation (Edge-TTS, ElevenLabs) and script cleaning."""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request

logger = logging.getLogger(__name__)

# ── Edge-TTS configuration ───────────────────────────────────────────────────

EDGE_VOICE_ZH = os.getenv("EDGE_TTS_VOICE", "zh-TW-HsiaoChenNeural")
EDGE_TTS_RATE = os.getenv("EDGE_TTS_RATE", "+15%")


# ── Script cleaning ──────────────────────────────────────────────────────────

def clean_script_for_tts(script: str) -> str:
    """Strip non-spoken content from AI-generated scripts before TTS.

    Removes entirely:
    - Markdown header lines (## etc.)
    - Numbered section lines (1. etc.)
    - Horizontal rules --- / ===
    - Emoji-only lines
    - Blank lines

    Strips inline:
    - Stage directions [text] etc.
    - Timestamp cues [0:15]
    - Speaker labels
    - Markdown bold/italic **text**
    """
    lines = script.splitlines()
    cleaned = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        # Skip entire markdown header lines
        if re.match(r'^#{1,6}\s+', s):
            continue
        # Skip numbered section labels
        if re.match(r'^(第[一二三四五六七八九十百]+[段節部點]|[一二三四五六七八九十]\s*[、.．]|[1-9]\d*\s*[\.、])\s*\S{1,20}[：:]?\s*$', s):
            continue
        # Skip standalone section-label lines
        if len(s) <= 30 and re.search(r'[（(【\[]', s) and not re.search(r'[。！？，、]', s):
            continue
        # Remove horizontal rules
        if re.match(r'^[-=*]{3,}$', s):
            continue
        # Strip bracketed/parenthetical stage directions
        s = re.sub(r'[【\[（(][^】\]）)]{1,60}[】\]）)]', '', s)
        # Strip timestamp cues
        s = re.sub(r'[\[(]\d+:\d+[\])]', '', s)
        # Strip speaker labels
        s = re.sub(r'^(主持人|旁白|Host|Narrator|VO|V\.O\.)\s*[：:]\s*', '', s)
        # Strip markdown formatting markers
        s = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', s)
        s = re.sub(r'_{1,2}([^_]+)_{1,2}', r'\1', s)
        s = s.strip()
        if not s:
            continue
        # Skip emoji-only lines
        text_only = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff]', '', s).strip()
        if not text_only:
            continue
        cleaned.append(s)

    return '\n'.join(cleaned)


# ── Edge-TTS ─────────────────────────────────────────────────────────────────

async def _edge_tts_bytes(text: str, voice: str, rate: str = "+0%") -> bytes:
    import edge_tts
    import io
    buf = io.BytesIO()
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def tts_edge(script: str, rate: str | None = None) -> bytes | None:
    """Generate TTS via Edge-TTS (free Microsoft voices, zh-TW supported)."""
    if not script:
        return None
    import asyncio
    effective_rate = rate if rate is not None else EDGE_TTS_RATE
    try:
        audio = asyncio.run(_edge_tts_bytes(script[:3000], EDGE_VOICE_ZH, rate=effective_rate))
        logger.info("Edge-TTS voiceover generated (%d bytes) at rate %s", len(audio), effective_rate)
        return audio
    except Exception:
        logger.exception("Edge-TTS failed")
        return None


# ── ElevenLabs TTS ───────────────────────────────────────────────────────────

def tts_elevenlabs(script: str) -> bytes | None:
    """Call ElevenLabs API -> return MP3 bytes (premium, most natural)."""
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key or not script:
        return None

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")
    payload  = json.dumps({
        "text": script[:2500],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode()

    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except Exception:
        logger.exception("ElevenLabs TTS failed")
        return None


# ── Auto-select TTS provider ────────────────────────────────────────────────

def tts_to_mp3(script: str) -> bytes | None:
    """TTS with automatic provider selection.

    Cleans non-spoken content before sending to TTS.
    Priority: ElevenLabs (if ELEVENLABS_API_KEY set) -> Edge-TTS (free default).
    Returns None if both fail, resulting in a silent video.
    """
    spoken = clean_script_for_tts(script)
    if not spoken:
        return None
    logger.info("TTS input after cleaning: %d chars (was %d)", len(spoken), len(script))
    if os.getenv("ELEVENLABS_API_KEY", "").strip():
        result = tts_elevenlabs(spoken)
        if result:
            return result
        logger.warning("ElevenLabs failed, falling back to Edge-TTS")
    return tts_edge(spoken)
