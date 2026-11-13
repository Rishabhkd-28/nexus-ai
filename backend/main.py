from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import os, logging

load_dotenv()

from agent import process_message
from channels import poll_gmail

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.add_job(poll_gmail, "interval", seconds=60, id="gmail_poll")
    scheduler.start()
    logger.info("APScheduler started — Gmail polling every 60s")
    yield
    scheduler.shutdown()

app = FastAPI(title="Nexus AI Sales Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}

# ── Telegram ──────────────────────────────────────────────────────────────────

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    try:
        payload = await request.json()
        message = payload.get("message", {})
        chat    = message.get("chat", {})
        text    = message.get("text", "").strip()
        chat_id = str(chat.get("id", ""))
        name    = (chat.get("first_name", "") + " " + chat.get("last_name", "")).strip()

        if not chat_id or not text:
            return {"ok": True}

        if text.startswith("/") and text != "/start":
            return {"ok": True}

        if text == "/start":
            text = "Hi, I'd like to know more about your services."

        logger.info(f"Telegram from {chat_id} ({name}): {text[:60]}")
        await process_message("telegram", chat_id, text, sender_name=name)
        return {"ok": True}

    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"ok": True}

# ── Email — manual poll trigger ───────────────────────────────────────────────

@app.post("/webhook/email/poll")
async def email_poll_now():
    await poll_gmail()
    return {"status": "polled"}
