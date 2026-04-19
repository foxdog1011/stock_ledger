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

    # Build frontmatter
    ticker_str = ", ".join(tickers) if tickers else "none"
    tag_list = " ".join(f"#{t}" for t in tags) if tags else ""

    # Quality emoji
    quality_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(
        quality_tier, "⚪"
    )

    md = f"""---
title: "{title}"
url: "{url}"
source: {source_type}
tickers: [{ticker_str}]
quality: {quality_tier} ({quality_score:.1f})
date: {now.strftime("%Y-%m-%d %H:%M")}
tags: [{", ".join(tags)}]
---

# {title}

{quality_emoji} **品質: {quality_tier.upper()}** ({quality_score:.1f}/1.0) | 來源: {source_type}
{f"作者: {author}" if author else ""}
🔗 [原文連結]({url})

## 摘要

{summary}

## 🟢 Bull Case

{bull_case or "（尚未分析）"}

## 🔴 Bear Case / 盲點

{bear_case or "（尚未分析）"}

## ⚖️ 審核筆記

{audit_notes or "（尚未審核）"}

## 相關標的

{ticker_str}

{tag_list}

---

## 原文節錄

{content[:2000]}

"""

    filepath.write_text(md, encoding="utf-8")
    rel_path = f"knowledge/{month_dir}/{filepath.name}"
    logger.info("Wrote knowledge to Obsidian: %s", rel_path)
    return rel_path
