"""AI-powered content analysis: summarize, extract tickers, Bull/Bear debate."""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisResult:
    """Output from AI content analysis."""
    title: str
    summary: str
    tickers: list[str]
    tags: list[str]
    bull_case: str
    bear_case: str
    audit_notes: str
    quality_tier: str
    quality_score: float


def _call_openai(messages: list[dict], max_tokens: int = 1000) -> str:
    """Call OpenAI API via raw HTTP (no SDK dependency)."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    payload = json.dumps({
        "model": "gpt-4o-mini",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _extract_tickers_regex(text: str) -> list[str]:
    """Extract Taiwan stock tickers (4-digit numbers) from text."""
    # Match patterns like 2330, (2330), 2330.TW
    matches = re.findall(r'\b(\d{4})\b', text)
    # Filter to valid TWSE range (1000-9999)
    valid = [m for m in matches if 1000 <= int(m) <= 9999]
    return list(dict.fromkeys(valid))  # dedupe preserving order


def analyze_content(
    title: str,
    text: str,
    source_type: str,
    user_notes: str = "",
) -> AnalysisResult:
    """Run AI analysis pipeline on fetched content.

    Steps:
    1. Summarize + extract tickers/tags
    2. Bull case analysis
    3. Bear case + blind spot detection
    4. Quality scoring
    """
    # Truncate for API limits
    truncated = text[:3000]

    system_prompt = """你是專業台股投資知識分析師。分析以下文章內容，回傳 JSON 格式：

{
    "title": "簡潔的中文標題（20字以內）",
    "summary": "3-5句話的重點摘要",
    "tickers": ["2330", "2454"],  // 文中提到的台股代碼
    "tags": ["半導體", "外資"],   // 相關主題標籤
    "bull_case": "這篇分析的價值和支持論點（2-3句）",
    "bear_case": "盲點、風險、可能遺漏的問題（2-3句）",
    "audit_notes": "與常識或市場現況的矛盾點（1-2句，沒有就寫「無明顯矛盾」）",
    "quality_tier": "high/medium/low",
    "quality_score": 0.0-1.0
}

品質評分標準：
- high (0.8-1.0): 有數據支撐、邏輯清晰、分析深入
- medium (0.5-0.7): 有觀點但缺乏數據、或分析較淺
- low (0.0-0.4): 純猜測、情緒化、或資訊明顯錯誤

嚴禁給出買賣建議。僅分析知識品質。"""

    user_prompt = f"來源：{source_type}\n標題：{title}\n\n內容：\n{truncated}"
    if user_notes:
        user_prompt += f"\n\n使用者備註：{user_notes}"

    try:
        raw = _call_openai([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ])
        result = json.loads(raw)
    except Exception as exc:
        logger.warning("AI analysis failed: %s — using fallback", exc)
        # Fallback: regex-based extraction
        tickers = _extract_tickers_regex(text)
        return AnalysisResult(
            title=title[:50] or "未命名文章",
            summary=truncated[:200],
            tickers=tickers,
            tags=[],
            bull_case="",
            bear_case="",
            audit_notes="AI 分析失敗，僅做基本擷取",
            quality_tier="unreviewed",
            quality_score=0.0,
        )

    # Merge regex-extracted tickers with AI-extracted ones
    ai_tickers = result.get("tickers", [])
    regex_tickers = _extract_tickers_regex(text)
    all_tickers = list(dict.fromkeys(ai_tickers + regex_tickers))

    quality_score = float(result.get("quality_score", 0.5))
    quality_tier = result.get("quality_tier", "medium")
    # Validate tier
    if quality_tier not in ("high", "medium", "low"):
        quality_tier = "medium"

    return AnalysisResult(
        title=result.get("title", title[:50]) or "未命名文章",
        summary=result.get("summary", ""),
        tickers=all_tickers,
        tags=result.get("tags", []),
        bull_case=result.get("bull_case", ""),
        bear_case=result.get("bear_case", ""),
        audit_notes=result.get("audit_notes", ""),
        quality_tier=quality_tier,
        quality_score=quality_score,
    )
