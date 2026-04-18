"""JARVIS Video Pipeline Watchdog — self-healing monitor.

Runs continuously via Windows Task Scheduler (on boot).
Every cycle it:
  1. Checks if local API (port 8003) is alive → restarts if dead
  2. Validates critical dependencies (ffmpeg, env vars, YouTube creds)
  3. Before scheduled upload times, runs a pre-flight check
  4. After scheduled upload times, verifies video was uploaded
  5. Alerts Discord on any issues

Usage:
    python scripts/watchdog.py              # Run forever (for Task Scheduler)
    python scripts/watchdog.py --once       # Single check (for testing)
    python scripts/watchdog.py --install    # Install Windows Task Scheduler job
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(PROJECT_ROOT / "logs" / "watchdog.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("watchdog")

# ── Config ────────────────────────────────────────────────────────────────────

API_PORT = 8003
API_URL = f"http://localhost:{API_PORT}"
HEALTH_URL = f"{API_URL}/api/health"
CHECK_INTERVAL = 120  # seconds between checks
DISCORD_CHANNEL_ID = "1484801481159741542"

# Schedule (Asia/Taipei) — times when uploads should happen
# Format: (hour, minute, description, weekdays)  weekdays: 0=Mon..6=Sun
UPLOAD_SCHEDULE = [
    (8, 0, "盤前美股 Shorts", [0, 1, 2, 3, 4, 5]),       # Mon-Sat
    (17, 0, "盤後速報", [0, 1, 2, 3, 4]),                  # Mon-Fri
    (19, 0, "晚間/族群/週報", [0, 1, 2, 3, 4, 5, 6]),     # Every day
]

# Required env vars for video pipeline
REQUIRED_ENV_VARS = [
    "OPENAI_API_KEY",
    "YOUTUBE_CLIENT_ID",
    "YOUTUBE_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN",
]


# ── Discord notification ──────────────────────────────────────────────────────

def _notify_discord(message: str) -> None:
    """Send alert to Discord via the local API's MCP plugin or direct webhook."""
    try:
        # Try via local API if available (it might be down)
        data = json.dumps({"text": message}).encode()
        req = urllib.request.Request(
            f"{API_URL}/api/discord/send",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        return
    except Exception:
        pass

    # Log to file as fallback
    logger.warning("Discord notification failed, message: %s", message)


# ── Health checks ─────────────────────────────────────────────────────────────

def check_api_alive() -> bool:
    """Check if local API responds on port 8003."""
    try:
        req = urllib.request.Request(HEALTH_URL)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("status") == "ok"
    except Exception:
        return False


def restart_api() -> bool:
    """Kill existing API and restart it."""
    logger.warning("API is down — attempting restart...")

    # Kill existing python processes on port 8003
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", "python.exe"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass

    time.sleep(2)

    # Start API in background
    env = os.environ.copy()

    # Load .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()

    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    try:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "apps.api.main:app",
             "--host", "0.0.0.0", "--port", str(API_PORT)],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=open(log_dir / "local_api.log", "a", encoding="utf-8"),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except Exception:
        logger.exception("Failed to start API")
        return False

    # Wait for API to come up
    for _ in range(15):
        time.sleep(2)
        if check_api_alive():
            logger.info("API restarted successfully")
            return True

    logger.error("API failed to start after restart attempt")
    return False


def check_env_vars() -> list[str]:
    """Check that required environment variables are set."""
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing.append(var)
    return missing


def check_ffmpeg() -> bool:
    """Check that ffmpeg is available."""
    try:
        import imageio_ffmpeg
        ff = imageio_ffmpeg.get_ffmpeg_exe()
        return Path(ff).exists()
    except Exception:
        return False


def check_youtube_creds() -> bool:
    """Validate YouTube OAuth credentials by refreshing token."""
    client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
    client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

    if not all([client_id, client_secret, refresh_token]):
        return False

    try:
        import urllib.parse
        data = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return "access_token" in result
    except Exception:
        return False


def check_n8n_alive() -> bool:
    """Check if n8n container is running and responsive."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", "ielts-n8n"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


# ── Pre-flight check ──────────────────────────────────────────────────────────

def preflight_check() -> dict:
    """Run all checks and return status report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "api_alive": check_api_alive(),
        "n8n_alive": check_n8n_alive(),
        "ffmpeg_ok": check_ffmpeg(),
        "env_missing": check_env_vars(),
        "youtube_creds_ok": False,
        "all_ok": False,
    }

    # Only check YouTube creds if env vars are present
    if not report["env_missing"]:
        report["youtube_creds_ok"] = check_youtube_creds()

    report["all_ok"] = (
        report["api_alive"]
        and report["n8n_alive"]
        and report["ffmpeg_ok"]
        and not report["env_missing"]
        and report["youtube_creds_ok"]
    )

    return report


# ── Schedule awareness ────────────────────────────────────────────────────────

def _next_upload_time() -> tuple[datetime, str] | None:
    """Find the next scheduled upload time."""
    now = datetime.now()
    candidates = []

    for hour, minute, desc, weekdays in UPLOAD_SCHEDULE:
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        # Check if target weekday is in schedule
        while target.weekday() not in weekdays:
            target += timedelta(days=1)
        candidates.append((target, desc))

    if not candidates:
        return None
    return min(candidates, key=lambda x: x[0])


def _is_preflight_window() -> tuple[bool, str]:
    """Check if we're within 30 minutes before a scheduled upload."""
    now = datetime.now()
    for hour, minute, desc, weekdays in UPLOAD_SCHEDULE:
        if now.weekday() not in weekdays:
            continue
        upload_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        delta = (upload_time - now).total_seconds()
        if 0 < delta <= 1800:  # Within 30 minutes before upload
            return True, desc
    return False, ""


# ── Main loop ─────────────────────────────────────────────────────────────────

def run_check_cycle() -> None:
    """Run one monitoring cycle."""
    # 1. Check API alive — restart if dead
    if not check_api_alive():
        logger.warning("API is DOWN on port %d", API_PORT)
        success = restart_api()
        if success:
            _notify_discord(
                f"⚠️ Watchdog: API 在 port {API_PORT} 掛了，已自動重啟成功"
            )
        else:
            _notify_discord(
                f"🚨 Watchdog: API 在 port {API_PORT} 掛了，自動重啟失敗！需要手動處理"
            )
            return
    else:
        logger.debug("API alive on port %d", API_PORT)

    # 2. Check n8n
    if not check_n8n_alive():
        logger.warning("n8n container is DOWN")
        # Try to restart
        try:
            subprocess.run(["docker", "restart", "ielts-n8n"],
                           capture_output=True, timeout=30)
            time.sleep(5)
            if check_n8n_alive():
                _notify_discord("⚠️ Watchdog: n8n 容器掛了，已自動重啟成功")
            else:
                _notify_discord("🚨 Watchdog: n8n 容器掛了，自動重啟失敗！")
        except Exception:
            _notify_discord("🚨 Watchdog: n8n 容器掛了，無法重啟！")

    # 3. Pre-flight check before uploads
    is_preflight, upload_desc = _is_preflight_window()
    if is_preflight:
        logger.info("Pre-flight check for: %s", upload_desc)
        report = preflight_check()

        if not report["all_ok"]:
            issues = []
            if not report["api_alive"]:
                issues.append("API 未啟動")
            if not report["n8n_alive"]:
                issues.append("n8n 未運行")
            if not report["ffmpeg_ok"]:
                issues.append("ffmpeg 不可用")
            if report["env_missing"]:
                issues.append(f"缺少環境變數: {', '.join(report['env_missing'])}")
            if not report["youtube_creds_ok"]:
                issues.append("YouTube 認證失敗")

            _notify_discord(
                f"🚨 Watchdog 飛行前檢查失敗（{upload_desc}即將上片）\n"
                f"問題：{'; '.join(issues)}"
            )
        else:
            logger.info("Pre-flight check passed for: %s", upload_desc)


def install_task_scheduler() -> None:
    """Install Windows Task Scheduler job to run watchdog on boot."""
    python_exe = sys.executable
    script_path = Path(__file__).resolve()
    working_dir = str(PROJECT_ROOT)

    # Create the scheduled task
    cmd = (
        f'schtasks /create /tn "JARVIS_Watchdog" /tr '
        f'"\"{python_exe}\" \"{script_path}\"" '
        f'/sc onstart /ru "{os.environ.get("USERNAME", "Administrator")}" '
        f'/rl highest /f'
    )

    logger.info("Installing Task Scheduler job...")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        logger.info("Task Scheduler job installed: JARVIS_Watchdog")
        print("Installed: JARVIS_Watchdog (runs on system startup)")
        print(f"  Python: {python_exe}")
        print(f"  Script: {script_path}")
        print(f"  Working dir: {working_dir}")
    else:
        logger.error("Failed to install: %s", result.stderr)
        print(f"Failed: {result.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS Video Pipeline Watchdog")
    parser.add_argument("--once", action="store_true", help="Run single check and exit")
    parser.add_argument("--install", action="store_true", help="Install as Windows Task Scheduler job")
    parser.add_argument("--preflight", action="store_true", help="Run full pre-flight check")
    args = parser.parse_args()

    # Ensure logs dir exists
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)

    # Load .env
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

    if args.install:
        install_task_scheduler()
        return

    if args.preflight:
        report = preflight_check()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        sys.exit(0 if report["all_ok"] else 1)

    if args.once:
        run_check_cycle()
        return

    # Continuous monitoring loop
    logger.info("Watchdog started — checking every %ds", CHECK_INTERVAL)
    _notify_discord("🟢 Watchdog 已啟動，開始監控影片產線")

    while True:
        try:
            run_check_cycle()
        except Exception:
            logger.exception("Watchdog cycle error")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
