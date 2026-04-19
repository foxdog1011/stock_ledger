"""One-time script to obtain YouTube OAuth refresh token.

Usage:
    pip install google-auth-oauthlib
    python scripts/youtube_auth.py

Then copy the printed YOUTUBE_REFRESH_TOKEN into your .env file.
"""
import os
import json

CLIENT_ID     = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()

if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in your env first.")
    raise SystemExit(1)

from google_auth_oauthlib.flow import InstalledAppFlow

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(
    client_config,
    scopes=[
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
    ],
)

# Opens browser for authorization
creds = flow.run_local_server(port=8766)

print("\n" + "=" * 60)
print("✅ Authorization successful!")
print("=" * 60)
print(f"\nAdd these to your .env file:\n")
print(f"YOUTUBE_CLIENT_ID={CLIENT_ID}")
print(f"YOUTUBE_CLIENT_SECRET={CLIENT_SECRET}")
print(f"YOUTUBE_REFRESH_TOKEN={creds.refresh_token}")
print("\n" + "=" * 60)
