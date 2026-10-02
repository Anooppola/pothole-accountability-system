"""Send pothole alerts to a Telegram chat through the Bot API."""
import html
import time
from pathlib import Path

import requests

from . import config

API = "https://api.telegram.org/bot{token}/{method}"
SEVERITY_ICON = {"Minor": "\U0001F7E2", "Moderate": "\U0001F7E0", "Critical": "\U0001F534"}  # green/orange/red


def _fmt_time(seconds: float) -> str:
    m, s = divmod(max(0.0, seconds or 0.0), 60)
    return f"{int(m):02d}:{s:04.1f}"


def pothole_caption(p: dict, video_name: str) -> str:
    """HTML caption for one pothole (Telegram limit: 1024 characters)."""
    icon = SEVERITY_ICON.get(p["severity"], "")
    lines = [
        f"<b>Pothole detected: {html.escape(p['id'])}</b>",
        f"Severity: {icon} <b>{html.escape(p['severity'])}</b>",
        f"Priority: <b>{html.escape(p['priority'])}</b>",
        f"In driving path: {'Yes' if p.get('in_path') else 'No'}",
        f"Video: {html.escape(video_name)} at {_fmt_time(p.get('best_time_s'))}",
        f"Seen in {p.get('frames_seen', 0)} frames, confidence {p.get('confidence', 0):.0%}",
        f"Severity score: {p.get('score', 0):.2f} (estimated from image)",
    ]
    return "\n".join(lines)[:1024]


def summary_text(video_name: str, potholes: list) -> str:
    counts = {s: sum(1 for p in potholes if p["severity"] == s) for s in ("Critical", "Moderate", "Minor")}
    urgent = sum(1 for p in potholes if p["priority"].startswith("P1"))
    return "\n".join([
        "<b>Road inspection report</b>",
        f"Video: {html.escape(video_name)}",
        f"Unique potholes: <b>{len(potholes)}</b>",
        f"{SEVERITY_ICON['Critical']} Critical: {counts['Critical']}   "
        f"{SEVERITY_ICON['Moderate']} Moderate: {counts['Moderate']}   "
        f"{SEVERITY_ICON['Minor']} Minor: {counts['Minor']}",
        f"P1 Urgent repairs: <b>{urgent}</b>",
    ])


def _post(method: str, data: dict, files: dict = None, retries: int = 2):
    """POST to the Bot API. Returns (ok, error_message)."""
    if not config.telegram_configured():
        return False, "Telegram not configured (add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to .env)"
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, data=data, files=files, timeout=30)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            if r.ok and body.get("ok"):
                return True, None
            if r.status_code == 429 and attempt < retries:  # rate limited
                time.sleep(int(body.get("parameters", {}).get("retry_after", 3)) + 1)
                if files:
                    for f in files.values():
                        f.seek(0)
                continue
            return False, body.get("description") or f"HTTP {r.status_code}"
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(2)
                continue
            return False, f"Network error: {e.__class__.__name__}"
    return False, "Unknown error"


def send_message(text: str):
    return _post("sendMessage", {
        "chat_id": config.TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })


def send_pothole(p: dict, video_name: str):
    image = config.ROOT / p["image_path"]
    caption = pothole_caption(p, video_name)
    if not Path(image).exists():
        return send_message(caption)
    with open(image, "rb") as fh:
        return _post(
            "sendPhoto",
            {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
            files={"photo": fh},
        )


def test_connection():
    """Check the bot token and chat ID. Returns (ok, message)."""
    if not config.telegram_configured():
        return False, "Not configured: add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to the .env file."
    ok, err = send_message("Pothole system: Telegram connection test successful.")
    return (True, "Test message sent. Check your Telegram.") if ok else (False, err)
