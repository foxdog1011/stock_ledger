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
            {"role": "system", "content": (
                "你是台股 YouTube 頻道「JARVIS 選股」的主持人，用數據說故事、語氣像朋友私下跟你透露內幕消息。\n\n"
                "【Hook 規則（最重要）】\n"
                "第一句話 MUST 是戲劇性的 hook，使用以下其中一種模式：\n"
                "1. 驚人數字：「外資狂砍X萬張！」「投信單日掃貨X張！」\n"
                "2. 好奇心缺口：「這檔股票法人偷偷在做一件事...」「有一個數字很不尋常...」\n"
                "3. 反直覺問句：「大家都在賣，但外資卻在買？」「散戶跑光了，但這個訊號出現了...」\n\n"
                "絕對不可以用打招呼、頻道名稱、「大家好」、「歡迎來到」等通用開場。\n"
                "全程保持高能量，語氣像壓低聲音快速分享內幕，有急迫感。\n\n"
                "【Shorts 結尾規則】\n"
                "如果是 Shorts 腳本，結尾必須加一句 CTA 當長片預告，例如：\n"
                "「完整分析看長片，連結在頻道首頁」或「想看更多？訂閱 JARVIS 選股」\n\n"
                "嚴禁給出買賣建議、進場時機、目標價等任何投資建議。僅分析籌碼數據事實與法人動向。"
            )},
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
