"""OpenAI script generation for video narration."""
from __future__ import annotations

import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)


def openai_script(prompt: str, max_tokens: int = 500) -> str:
    """Generate a narration script via OpenAI gpt-4o-mini."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return prompt  # fallback: use prompt as script

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "你是專業台股分析 YouTuber，語氣活潑但專業。嚴禁給出買賣建議、進場時機、目標價等任何投資建議。僅分析籌碼數據事實。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("OpenAI script generation failed")
        return prompt
