"""Daily portfolio briefing → Discord.

Fetches portfolio snapshot + positions + risk metrics via the local API,
asks J.A.R.V.I.S. (Claude) to write a concise morning briefing, then
posts the result to a Discord channel via webhook or bot token.

Usage:
    python scripts/daily_discord_briefing.py

Environment variables (set in .env or shell):
    API_BASE_URL       Internal API base, default http://localhost:8000
    ANTHROPIC_API_KEY  Claude API key
    DISCORD_BOT_TOKEN  Bot token (same as .env in channels/discord/)
    DISCORD_CHANNEL_ID Discord channel ID to post to
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_BASE   = os.getenv("API_BASE_URL", "http://localhost:8000")
BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN", "")
CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID", "1484801456824516678")  # 股票分類 default


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> dict:
    url = f"{API_BASE}{path}"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post_discord(text: str) -> None:
    if not BOT_TOKEN:
        print("[briefing] DISCORD_BOT_TOKEN not set — printing to stdout only")
        print(text)
        return

    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages"
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    # Discord max 2000 chars per message — split if needed
    chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
    for chunk in chunks:
        resp = httpx.post(url, headers=headers, json={"content": chunk}, timeout=10)
        resp.raise_for_status()


def _gather_data() -> dict:
    data: dict = {}
    try:
        data["snapshot"]  = _api("/portfolio/snapshot")
    except Exception as e:
        data["snapshot"]  = {"error": str(e)}
    try:
        data["positions"] = _api("/positions")
    except Exception as e:
        data["positions"] = {"error": str(e)}
    try:
        data["risk"]      = _api("/risk/metrics")
    except Exception as e:
        data["risk"]      = {"error": str(e)}
    try:
        data["perf"]      = _api("/perf/summary")
    except Exception as e:
        data["perf"]      = {"error": str(e)}
    return data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[briefing] ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    today = date.today().isoformat()
    print(f"[briefing] Gathering portfolio data for {today}...")
    data = _gather_data()

    prompt = f"""Today is {today}. Here is the current portfolio data:

{json.dumps(data, indent=2, default=str)}

Write a concise morning briefing (max 400 words) for the portfolio owner. Include:
1. Portfolio value and today's P&L summary (unrealized + realized)
2. Top gainer and top loser position
3. Key risk flags (if any concentration > 20%, max drawdown concerns, etc.)
4. One actionable observation or suggestion based on the data

Be direct and use numbers. Format for Discord (no markdown headers, use emoji sparingly).
Start with "📊 Morning Briefing — {today}"."""

    client = OpenAI(api_key=api_key)
    print("[briefing] Asking J.A.R.V.I.S. to generate briefing...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    briefing = response.choices[0].message.content

    print("[briefing] Posting to Discord...")
    _post_discord(briefing)
    print("[briefing] Done.")


if __name__ == "__main__":
    main()
