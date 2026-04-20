"""Write knowledge entries to Obsidian vault as Markdown files."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default vault path — override via OBSIDIAN_VAULT_PATH env var
_DEFAULT_VAULT = r"C:\Users\Administrator\obsidian-vault"


def _get_vault_path() -> Path:
    return Path(os.environ.get("OBSIDIAN_VAULT_PATH", _DEFAULT_VAULT))


def _sanitize_filename(name: str) -> str:
    """Remove characters invalid for filenames."""
    cleaned = re.sub(r'[<>:"/\\|?*]', '', name)
    cleaned = cleaned.strip(". ")
    return cleaned[:80] or "untitled"


def _ticker_wikilink(ticker: str) -> str:
    """Create a wikilink for a ticker, e.g. [[2330-台積電]]."""
    # Known ticker → name mapping (expand over time)
    _NAMES: dict[str, str] = {
        "2330": "台積電", "2454": "聯發科", "2317": "鴻海",
        "2382": "廣達", "2308": "台達電", "3711": "日月光",
        "2303": "聯電", "2412": "中華電", "2881": "富邦金",
        "2882": "國泰金", "2886": "兆豐金", "2891": "中信金",
        "3037": "欣興", "2357": "華碩", "6505": "台塑化",
        "3034": "聯詠", "5274": "信驊", "3661": "世芯-KY",
        "2603": "長榮", "2609": "陽明", "2615": "萬海",
    }
    name = _NAMES.get(ticker, "")
    if name:
        return f"[[{ticker}-{name}]]"
    return f"[[{ticker}]]"


def write_to_vault(
    title: str,
    url: str,
    source_type: str,
    summary: str,
    content: str,
    tickers: list[str],
    tags: list[str],
    bull_case: str,
    bear_case: str,
    audit_notes: str,
    quality_tier: str,
    quality_score: float,
    author: str = "",
) -> str:
    """Write a knowledge entry as a Markdown file in the Obsidian vault.

    Optimized for Obsidian Second Brain workflow:
    - YAML frontmatter compatible with Dataview plugin
    - Wikilinks for Graph View connections
    - Tags as proper Obsidian tags

    Files are saved to: vault/knowledge/YYYY-MM/title.md
    Returns the relative path within the vault.
    """
    vault = _get_vault_path()
    now = datetime.now()
    month_dir = now.strftime("%Y-%m")
    folder = vault / "knowledge" / month_dir
    folder.mkdir(parents=True, exist_ok=True)

    safe_title = _sanitize_filename(title)
    date_prefix = now.strftime("%Y%m%d")
    filename = f"{date_prefix}_{safe_title}.md"
    filepath = folder / filename

    # Avoid overwriting
    if filepath.exists():
        filepath = folder / f"{date_prefix}_{safe_title}_{now.strftime('%H%M%S')}.md"

    # Build YAML frontmatter (Dataview compatible)
    ticker_yaml = "\n".join(f"  - \"{t}\"" for t in tickers) if tickers else "  []"
    tag_yaml = "\n".join(f"  - {t}" for t in tags) if tags else "  []"

    # Wikilinks for graph view
    ticker_links = " ".join(_ticker_wikilink(t) for t in tickers)
    tag_links = " ".join(f"#{t}" for t in tags)

    md = f"""---
title: "{title}"
url: "{url}"
source: {source_type}
author: "{author}"
tickers:
{ticker_yaml}
tags:
{tag_yaml}
quality: {quality_tier}
quality_score: {quality_score:.1f}
reviewed: false
date: {now.strftime("%Y-%m-%d")}
created: {now.strftime("%Y-%m-%dT%H:%M")}
---

# {title}

來源: {source_type} | {f"作者: @{author} | " if author else ""}[原文連結]({url})
擷取時間: {now.strftime("%Y-%m-%d %H:%M")}

## 相關標的

{ticker_links or "（無）"}

## 摘要

{summary}

## 多空分析

> 待整理 — 在 Claude Code 中執行深度分析

## 原文內容

{content[:3000]}

---

{tag_links}
"""

    filepath.write_text(md, encoding="utf-8")
    rel_path = f"knowledge/{month_dir}/{filepath.name}"
    logger.info("Wrote knowledge to Obsidian: %s", rel_path)
    return rel_path
