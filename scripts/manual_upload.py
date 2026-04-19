"""Manual pipeline: pick stock → generate video → upload to YouTube."""
import json
import urllib.request

BASE = "http://localhost:8000"


def api_post(path, body, timeout=300):
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# Step 1: Pick stock
pick = api_post("/api/video-gen/pick-stock", {"slot": "morning"}, timeout=90)
sym = pick["symbol"]
print(f"Picked: {sym} - {pick['title']}")

# Step 2: Generate video
gen = api_post("/api/video-gen/generate", {
    "symbol": sym,
    "slot": "morning",
    "title": pick["title"],
    "pick_reason": pick["pick_reason"],
}, timeout=300)
print(f"Generated: {gen['video_path']}")
print(f"Title: {gen['title']}")

# Step 3: Upload to YouTube
upload = api_post("/api/video-gen/upload-youtube", {
    "video_path": gen["video_path"],
    "title": gen["title"],
    "description": gen["description"],
    "tags": gen["tags"],
    "script": gen["script"],
    "slot": "morning",
    "symbol": sym,
    "privacy": "public",
}, timeout=120)
print(f"Upload: {json.dumps(upload, ensure_ascii=False)[:500]}")
