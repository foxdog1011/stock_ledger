#!/usr/bin/env python3
"""Ingest a URL into the knowledge base via the API.

Usage:
    python scripts/ingest_url.py "https://threads.net/@user/post/abc"
    python scripts/ingest_url.py "https://x.com/..." --debate
    python scripts/ingest_url.py "https://..." --api http://EC2:8003/api/knowledge
"""
import json
import sys
import urllib.request

DEFAULT_API = "http://localhost:8003/api/knowledge"


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python ingest_url.py <url> [--debate] [--api <base_url>]")
        sys.exit(0 if "--help" in sys.argv else 1)

    url = sys.argv[1]
    debate = "--debate" in sys.argv
    api_base = DEFAULT_API
    for i, arg in enumerate(sys.argv):
        if arg == "--api" and i + 1 < len(sys.argv):
            api_base = sys.argv[i + 1].rstrip("/")

    # Step 1: Ingest
    payload = json.dumps({"url": url, "source_type": "auto", "notes": ""}).encode()
    req = urllib.request.Request(
        f"{api_base}/ingest", data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}")
        sys.exit(1)

    entry_id = data.get("id")
    print(f"Status : {data.get('status')}")
    print(f"Title  : {data.get('title')}")
    print(f"Quality: {data.get('quality_tier')} ({data.get('quality_score')})")
    print(f"Tickers: {', '.join(data.get('tickers', [])) or 'none'}")
    print(f"Summary: {data.get('summary', '')[:200]}")
    if data.get("bull_case"):
        print(f"Bull   : {data['bull_case'][:150]}")
    if data.get("bear_case"):
        print(f"Bear   : {data['bear_case'][:150]}")
    print(f"Saved  : {data.get('obsidian_path')}")

    # Step 2: Deep debate (optional)
    if debate and entry_id:
        print("\n--- 4-Agent Debate ---")
        req2 = urllib.request.Request(
            f"{api_base}/{entry_id}/debate", data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req2, timeout=120) as resp2:
            dr = json.loads(resp2.read()).get("debate", {})

        print(f"Thesis : {dr.get('extraction', {}).get('thesis')}")
        bull = dr.get("bull", {})
        print(f"\nBull ({bull.get('confidence', 0):.0%}):")
        for a in bull.get("arguments", []):
            print(f"  + {a}")
        bear = dr.get("bear", {})
        print(f"\nBear ({bear.get('confidence', 0):.0%}):")
        for a in bear.get("arguments", []):
            print(f"  - {a}")
        for b in bear.get("blind_spots", []):
            print(f"  ! {b}")
        aud = dr.get("auditor", {})
        print(f"\nVerdict: {aud.get('quality_tier')} ({aud.get('quality_score')})")
        print(f"  {aud.get('verdict')}")


if __name__ == "__main__":
    main()
