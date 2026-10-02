"""Find your Telegram chat ID and save it into .env automatically.

Before running:
  1. Put your bot token in .env  (TELEGRAM_BOT_TOKEN=...)
  2. Open your bot in Telegram, press Start and send it any message (e.g. "hi")

Run:
    python scripts/get_chat_id.py
"""
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"


def read_env() -> str:
    if not ENV.exists():
        sys.exit("No .env file found. Copy .env.example to .env first.")
    return ENV.read_text()


def main():
    text = read_env()
    m = re.search(r"^TELEGRAM_BOT_TOKEN=(.*)$", text, re.M)
    token = (m.group(1).strip() if m else "")
    if not token or token == "your-bot-token-from-BotFather":
        sys.exit("Put your bot token in .env first (the line TELEGRAM_BOT_TOKEN=...), save, and run again.")

    try:
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20)
        data = r.json()
    except requests.RequestException as e:
        sys.exit(f"Could not reach Telegram ({e.__class__.__name__}). Check your internet connection.")
    if not data.get("ok"):
        sys.exit(f"Telegram rejected the token: {data.get('description')}. "
                 "Copy the token from @BotFather again, exactly as shown.")

    chats = {}
    for upd in data.get("result", []):
        msg = upd.get("message") or upd.get("channel_post") or upd.get("my_chat_member") or {}
        chat = msg.get("chat")
        if chat:
            name = chat.get("first_name") or chat.get("title") or chat.get("username") or ""
            chats[chat["id"]] = name
    if not chats:
        sys.exit("No messages found yet. Open your bot in Telegram, press Start, send it 'hi', "
                 "then run this again.")

    chat_id, name = list(chats.items())[-1]
    if re.search(r"^TELEGRAM_CHAT_ID=.*$", text, re.M):
        text = re.sub(r"^TELEGRAM_CHAT_ID=.*$", f"TELEGRAM_CHAT_ID={chat_id}", text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\nTELEGRAM_CHAT_ID={chat_id}\n"
    ENV.write_text(text)
    print(f"Found chat ID {chat_id} ({name}) and saved it to .env.")

    ok = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                       data={"chat_id": chat_id, "text": "Pothole system connected successfully."},
                       timeout=20).json().get("ok")
    print("Test message sent. Check Telegram!" if ok else "Saved, but the test message failed.")


if __name__ == "__main__":
    main()
