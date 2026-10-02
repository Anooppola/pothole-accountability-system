"""Small display helpers shared by the web pages."""
from . import config

SEVERITY_BADGE = {"Minor": "green", "Moderate": "orange", "Critical": "red"}
PRIORITY_BADGE = {"P1 Urgent": "red", "P2 Soon": "orange", "P3 Routine": "blue"}
REVIEW_BADGE = {"Pending": "gray", "Approved": "green", "Rejected": "red"}
TELEGRAM_LABEL = {
    "sent": ":green-badge[Telegram: sent]",
    "failed": ":red-badge[Telegram: failed]",
    "not_configured": ":gray-badge[Telegram: not set up]",
    "pending": ":gray-badge[Telegram: pending]",
    "skipped": ":gray-badge[Telegram: not sent]",
}


def badge(text: str, colors: dict) -> str:
    return f":{colors.get(text, 'gray')}-badge[{text}]"


def fmt_time(seconds) -> str:
    m, s = divmod(max(0.0, seconds or 0.0), 60)
    return f"{int(m):02d}:{s:04.1f}"


def abs_path(rel: str) -> str:
    return str(config.ROOT / rel) if rel else ""
