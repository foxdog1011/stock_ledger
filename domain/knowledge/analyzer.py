"""Content analysis: regex-based extraction (no AI API calls).

The ingestion pipeline uses free local extraction only:
- Ticker extraction via regex
- Tag detection via keyword matching
- Title cleaning
- Text truncation for summary

AI-powered deep analysis (Bull/Bear, quality scoring) is done on-demand
via Claude Code conversations reading the Obsidian vault — zero API cost.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Known Taiwan stock keywords → tags mapping
_TAG_KEYWORDS: dict[str, list[str]] = {
    "半導體": ["半導體", "晶圓", "台積", "TSMC", "聯發科", "IC設計", "封測", "矽"],
    "AI": ["AI", "人工智慧", "機器學習", "LLM", "GPT", "Claude", "深度學習"],
    "電動車": ["電動車", "EV", "特斯拉", "Tesla", "充電"],
    "金融": ["金融", "銀行", "壽險", "證券", "保險"],
    "航運": ["航運", "貨櫃", "散裝", "長榮", "萬海", "陽明"],
    "綠能": ["綠能", "太陽能", "風電", "儲能"],
    "生技": ["生技", "新藥", "醫材", "FDA"],
    "營建": ["營建", "房地產", "建設", "都更"],
    "觀光": ["觀光", "旅遊", "飯店", "餐飲"],
    "SaaS": ["SaaS", "軟體", "雲端", "訂閱制"],
    "CPU": ["CPU", "處理器", "x86", "ARM"],
    "MEMS": ["MEMS", "微機電", "振盪器", "石英"],
    "外資": ["外資", "法人", "投信", "自營商", "三大法人"],
    "總經": ["總經", "利率", "CPI", "Fed", "聯準會", "GDP", "通膨"],
    "美股": ["美股", "S&P", "那斯達克", "NASDAQ", "道瓊"],
}

# US stock tickers commonly mentioned in Taiwan investment context
# Use lookaround to handle Chinese-ASCII boundaries where \b may not match
_US_TICKER_PATTERNS = re.compile(
    r'(?<![A-Za-z])(AAPL|MSFT|GOOGL|GOOG|AMZN|NVDA|META|TSLA|AMD|INTC|ARM|TSM|AVGO'
    r'|QCOM|MU|ASML|LRCX|KLAC|AMAT|MRVL|SMCI|DELL|HPE)(?![A-Za-z])'
)


@dataclass(frozen=True)
class AnalysisResult:
    """Output from content analysis."""
    title: str
    summary: str
    tickers: list[str]
    tags: list[str]
    bull_case: str
    bear_case: str
    audit_notes: str
    quality_tier: str
    quality_score: float


def _extract_tickers_regex(text: str) -> list[str]:
    """Extract Taiwan stock tickers (4-digit numbers) from text."""
    # Match patterns like 2330, (2330), 2330.TW
    matches = re.findall(r'\b(\d{4})\b', text)
    # Filter to valid TWSE range (1000-9999), exclude common years
    current_year = 2026
    valid = [
        m for m in matches
        if 1000 <= int(m) <= 9999 and not (2020 <= int(m) <= current_year + 1)
    ]
    return list(dict.fromkeys(valid))  # dedupe preserving order


def _extract_us_tickers(text: str) -> list[str]:
    """Extract commonly mentioned US stock tickers."""
    matches = _US_TICKER_PATTERNS.findall(text)
    return list(dict.fromkeys(matches))


def _extract_tags(text: str) -> list[str]:
    """Extract topic tags by keyword matching."""
    tags: list[str] = []
    upper = text.upper()
    for tag, keywords in _TAG_KEYWORDS.items():
        if any(kw.upper() in upper for kw in keywords):
            tags.append(tag)
    return tags


def _make_summary(text: str, max_len: int = 200) -> str:
    """Create a simple summary from the first meaningful paragraph."""
    lines = [ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15]
    summary = " ".join(lines[:3])
    if len(summary) > max_len:
        summary = summary[:max_len] + "…"
    return summary


def analyze_content(
    title: str,
    text: str,
    source_type: str,
    user_notes: str = "",
) -> AnalysisResult:
    """Analyze content using free local extraction (no API calls).

    Extracts tickers, tags, and creates a basic summary.
    Deep analysis (Bull/Bear) is deferred to Claude Code sessions.
    """
    tw_tickers = _extract_tickers_regex(text)
    us_tickers = _extract_us_tickers(text)
    all_tickers = tw_tickers + us_tickers
    tags = _extract_tags(text)
    summary = _make_summary(text)

    clean_title = title.strip()[:80] if title.strip() else "未命名文章"

    return AnalysisResult(
        title=clean_title,
        summary=summary,
        tickers=all_tickers,
        tags=tags,
        bull_case="",
        bear_case="",
        audit_notes="",
        quality_tier="unreviewed",
        quality_score=0.0,
    )
