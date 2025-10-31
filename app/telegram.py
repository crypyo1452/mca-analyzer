# app/bot/telegram.py
import os
import re
import requests
from fastapi import APIRouter, HTTPException, Request

from app.bot_formatting import format_report_for_telegram
from app.services.bsc import analyze_bsc  # call analyzer directly, faster & simpler

router = APIRouter()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage" if TELEGRAM_BOT_TOKEN else None

# Simple CA matcher
CA_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")

HELP_TEXT = (
    "Hi! Send me a BSC contract address (CA), like:\n"
    "`0x0E09FABB73BD3ADE0A17ECC321FD13A19E81CE82`\n\n"
    "I’ll analyze it and reply with a score, risk band, and key factors."
)

def _send(chat_id: int, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TG_API:
        # Fail loudly so you notice misconfig fast
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var.")
    # Telegram expects plain text; we’re not using Markdown here to avoid escaping complexity
    requests.post(TG_API, json={"chat_id": chat_id, "text": text}, timeout=15)

def _extract_chat_and_text(update: dict) -> tuple[int, str]:
    """
    Supports standard message updates and simple edited_message.
    """
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        raise ValueError("No message in update")
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if chat_id is None:
        raise ValueError("No chat_id")
    return chat_id, text

@router.post("/tg")
async def telegram_webhook(request: Request):
    """
    Telegram will POST updates here.
    Make sure your bot's webhook is set to: https://<your-domain>/tg
    """
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    try:
        chat_id, text = _extract_chat_and_text(update)
    except Exception as e:
        # Nothing we can do without chat_id; just 200 to avoid retry storms
        return {"ok": True, "ignored": str(e)}

    # /start or empty → help
    if not text or text.lower().startswith("/start"):
        _send(chat_id, HELP_TEXT)
        return {"ok": True}

    # Validate contract address
    candidate = text.split()[0]  # take first token in the message
    if not CA_RE.match(candidate):
        _send(chat_id, "Please send a valid BSC contract address (starts with 0x + 40 hex chars).")
        return {"ok": True}

    # Analyze (direct call) and format
    try:
        result = analyze_bsc(candidate)           # dataclass result
        data = result.model_dump()                # dict for formatter
        reply = format_report_for_telegram(data)  # pretty string
    except Exception as e:
        # Don’t leak stacktraces to users
        _send(chat_id, "❌ Sorry, couldn’t analyze. Try again in a minute.")
        # Return detail for logs
        return {"ok": False, "error": str(e)}

    # Send the reply back
    try:
        _send(chat_id, reply)
    except Exception as e:
        # If sending fails, let Render logs show why
        raise HTTPException(status_code=500, detail=f"Telegram send failed: {e}")

    return {"ok": True}
