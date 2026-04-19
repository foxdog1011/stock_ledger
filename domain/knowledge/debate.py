"""Multi-agent debate system for knowledge quality validation.

Inspired by TradingAgents (github.com/TauricResearch/TradingAgents).
Uses 4 specialized AI agents in sequence:

1. Extractor Agent  — Extract key claims, data points, tickers, and thesis
2. Bull Agent       — Argue why this analysis is valuable and correct
3. Bear Agent       — Find blind spots, risks, missing context, logical flaws
4. Auditor Agent    — Cross-check claims, score quality, produce final verdict

Each agent sees the output of previous agents, creating a structured debate.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DebateResult:
    """Full output from the multi-agent debate."""
    # Extractor output
    key_claims: list[str]
    data_points: list[str]
    tickers: list[str]
    thesis: str
    # Bull agent
    bull_arguments: list[str]
    bull_confidence: float
    # Bear agent
    bear_arguments: list[str]
    blind_spots: list[str]
    bear_confidence: float
    # Auditor verdict
    quality_tier: str
    quality_score: float
    verdict: str
    contradictions: list[str]
    recommendations: list[str]


def _call_openai_json(
    system: str,
    user: str,
    max_tokens: int = 800,
    model: str = "gpt-4o-mini",
) -> dict:
    """Call OpenAI with JSON mode. Returns parsed dict."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.4,
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
    return json.loads(data["choices"][0]["message"]["content"])


# ── Agent 1: Extractor ──────────────────────────────────────────────────────

_EXTRACTOR_SYSTEM = """你是投資知識提取專家。從文章中提取結構化資訊。

回傳 JSON：
{
    "key_claims": ["文章的核心論點1", "論點2", ...],
    "data_points": ["具體數據1（如：營收成長28%）", "數據2", ...],
    "tickers": ["2330", "2454"],
    "thesis": "文章的核心投資論述（1-2句話）",
    "sector": "相關產業",
    "timeframe": "分析的時間範圍（短期/中期/長期）"
}

僅提取事實，不加入個人判斷。"""


def _run_extractor(title: str, content: str) -> dict:
    """Agent 1: Extract structured claims and data from content."""
    return _call_openai_json(
        system=_EXTRACTOR_SYSTEM,
        user=f"標題：{title}\n\n內容：\n{content[:3000]}",
    )


# ── Agent 2: Bull ───────────────────────────────────────────────────────────

_BULL_SYSTEM = """你是多頭研究員。你的工作是找出這篇分析的價值和正確之處。

你收到的資料包含：
1. 原始文章摘要
2. 提取 Agent 的結構化分析

回傳 JSON：
{
    "arguments": [
        "支持論點1（為什麼這個分析有價值）",
        "支持論點2",
        "支持論點3"
    ],
    "data_support": "這些論點有哪些數據支撐",
    "confidence": 0.0-1.0,
    "strength": "這篇分析最強的地方是什麼（1句話）"
}

你必須盡力找到正面論點，即使文章品質不高也要找出可取之處。
嚴禁給出買賣建議。"""


def _run_bull(title: str, content: str, extraction: dict) -> dict:
    """Agent 2: Argue the bull case for this analysis."""
    user_msg = (
        f"原始文章：{title}\n{content[:1500]}\n\n"
        f"提取結果：\n{json.dumps(extraction, ensure_ascii=False, indent=2)}"
    )
    return _call_openai_json(system=_BULL_SYSTEM, user=user_msg)


# ── Agent 3: Bear ───────────────────────────────────────────────────────────

_BEAR_SYSTEM = """你是空頭研究員兼魔鬼代言人。你的工作是找出分析的盲點、風險和邏輯漏洞。

你收到的資料包含：
1. 原始文章摘要
2. 提取 Agent 的結構化分析
3. 多頭研究員的論點

回傳 JSON：
{
    "arguments": [
        "反駁論點1（這個分析哪裡有問題）",
        "反駁論點2",
        "反駁論點3"
    ],
    "blind_spots": [
        "文章忽略的風險1",
        "文章忽略的風險2"
    ],
    "missing_data": "需要但文章沒提供的數據",
    "confidence": 0.0-1.0,
    "biggest_risk": "最大的風險是什麼（1句話）"
}

你必須嚴格審視。不要客氣，找出所有問題。
嚴禁給出買賣建議。"""


def _run_bear(
    title: str, content: str, extraction: dict, bull: dict,
) -> dict:
    """Agent 3: Argue the bear case and find blind spots."""
    user_msg = (
        f"原始文章：{title}\n{content[:1500]}\n\n"
        f"提取結果：\n{json.dumps(extraction, ensure_ascii=False, indent=2)}\n\n"
        f"多頭論點：\n{json.dumps(bull, ensure_ascii=False, indent=2)}"
    )
    return _call_openai_json(system=_BEAR_SYSTEM, user=user_msg)


# ── Agent 4: Auditor ────────────────────────────────────────────────────────

_AUDITOR_SYSTEM = """你是投資知識審核員。你看過了原始文章、提取結果、多頭論點和空頭論點。
現在你要做最終裁決。

回傳 JSON：
{
    "quality_tier": "high/medium/low",
    "quality_score": 0.0-1.0,
    "verdict": "最終裁決（2-3句話總結這篇文章的知識價值）",
    "contradictions": ["與市場現實矛盾的地方1", ...],
    "recommendations": [
        "如果要使用這篇分析，需要注意什麼1",
        "需要額外驗證什麼2"
    ],
    "bull_winner": true/false,
    "debate_summary": "多空辯論的結論（1句話）"
}

評分標準：
- high (0.8-1.0): 數據充分、邏輯嚴謹、盲點已被充分討論
- medium (0.5-0.7): 有價值但需要額外驗證
- low (0.0-0.4): 風險大於價值，不建議作為決策依據

嚴禁給出買賣建議。你是知識品質審核，不是投資顧問。"""


def _run_auditor(
    title: str,
    extraction: dict,
    bull: dict,
    bear: dict,
) -> dict:
    """Agent 4: Final verdict combining all perspectives."""
    user_msg = (
        f"文章：{title}\n\n"
        f"提取：\n{json.dumps(extraction, ensure_ascii=False, indent=2)}\n\n"
        f"多頭：\n{json.dumps(bull, ensure_ascii=False, indent=2)}\n\n"
        f"空頭：\n{json.dumps(bear, ensure_ascii=False, indent=2)}"
    )
    return _call_openai_json(system=_AUDITOR_SYSTEM, user=user_msg)


# ── Public API ──────────────────────────────────────────────────────────────


def run_debate(title: str, content: str) -> DebateResult:
    """Run the full 4-agent debate pipeline on content.

    Returns a DebateResult with structured output from all agents.
    This is the "deep review" mode — more thorough than the basic
    analyze_content() function but uses 4x the API calls.
    """
    logger.info("Starting multi-agent debate for: %s", title[:50])

    # Agent 1: Extract
    logger.info("  Agent 1 (Extractor) running...")
    extraction = _run_extractor(title, content)
    logger.info("  Extracted %d claims, %d data points",
                len(extraction.get("key_claims", [])),
                len(extraction.get("data_points", [])))

    # Agent 2: Bull
    logger.info("  Agent 2 (Bull) running...")
    bull = _run_bull(title, content, extraction)
    logger.info("  Bull confidence: %.2f", bull.get("confidence", 0))

    # Agent 3: Bear
    logger.info("  Agent 3 (Bear) running...")
    bear = _run_bear(title, content, extraction, bull)
    logger.info("  Bear confidence: %.2f", bear.get("confidence", 0))

    # Agent 4: Auditor
    logger.info("  Agent 4 (Auditor) running...")
    auditor = _run_auditor(title, extraction, bull, bear)
    logger.info("  Verdict: %s (%.2f)",
                auditor.get("quality_tier"), auditor.get("quality_score", 0))

    quality_tier = auditor.get("quality_tier", "medium")
    if quality_tier not in ("high", "medium", "low"):
        quality_tier = "medium"

    return DebateResult(
        key_claims=extraction.get("key_claims", []),
        data_points=extraction.get("data_points", []),
        tickers=extraction.get("tickers", []),
        thesis=extraction.get("thesis", ""),
        bull_arguments=bull.get("arguments", []),
        bull_confidence=float(bull.get("confidence", 0.5)),
        bear_arguments=bear.get("arguments", []),
        blind_spots=bear.get("blind_spots", []),
        bear_confidence=float(bear.get("confidence", 0.5)),
        quality_tier=quality_tier,
        quality_score=float(auditor.get("quality_score", 0.5)),
        verdict=auditor.get("verdict", ""),
        contradictions=auditor.get("contradictions", []),
        recommendations=auditor.get("recommendations", []),
    )
