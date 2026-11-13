"""
channels.py — unified send_reply() + Gmail polling
Active channels: telegram | email
Coming soon: instagram, whatsapp
"""
import base64, logging, os, re
from email.mime.text import MIMEText

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import json

logger = logging.getLogger(__name__)


# ── Gmail ──────────────────────────────────────────────────────────────────────

def _gmail_service():
    token_data = json.loads(os.environ["GOOGLE_TOKEN_JSON"])
    creds = Credentials(
        token         = token_data.get("token"),
        refresh_token = token_data.get("refresh_token"),
        token_uri     = "https://oauth2.googleapis.com/token",
        client_id     = os.environ["GOOGLE_CLIENT_ID"],
        client_secret = os.environ["GOOGLE_CLIENT_SECRET"],
        scopes        = [
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar",
        ],
    )
    return build("gmail", "v1", credentials=creds)


def _extract_email_text(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    if mime_type == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = _extract_email_text(part)
        if result:
            return result
    return ""


def _extract_sender_email(from_addr: str) -> str:
    match = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]+', from_addr)
    return match.group(0).lower() if match else from_addr.lower()


async def poll_gmail():
    """Poll Gmail — ONLY processes emails from @gmail.com addresses."""
    from agent import process_message

    BLOCKED = [
        "support@interakt.ai", "hello@interakt.ai",
        "noreply@interakt.ai", "noreply@github.com",
        "postmaster@microsoft.com",
    ]

    try:
        service  = _gmail_service()
        results  = (
            service.users()
            .messages()
            .list(userId="me", q="is:unread label:inbox", maxResults=10)
            .execute()
        )
        messages = results.get("messages", [])

        for msg_ref in messages:
            msg_id = msg_ref["id"]
            msg    = service.users().messages().get(
                userId="me", id=msg_id, format="full"
            ).execute()

            headers   = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
            from_addr = headers.get("From", "")
            subject   = headers.get("Subject", "(no subject)")
            body      = _extract_email_text(msg["payload"]).strip()

            service.users().messages().modify(
                userId="me", id=msg_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()

            if not body:
                continue

            sender_id = _extract_sender_email(from_addr)

            if sender_id in BLOCKED:
                logger.info(f"Blocked: {sender_id}")
                continue

            if not sender_id.endswith("@gmail.com"):
                logger.info(f"Skipped (not gmail): {sender_id}")
                continue

            logger.info(f"Processing: {sender_id} | {subject[:50]}")
            display_name = f"{from_addr} | {subject}"
            await process_message("email", sender_id, body, sender_name=display_name)

    except Exception as e:
        logger.error(f"Gmail poll error: {e}")


async def _send_email(to: str, text: str):
    service = _gmail_service()
    subject = "Re: Nexus Analytics Consulting Inquiry"
    try:
        results = (
            service.users()
            .messages()
            .list(userId="me", q=f"from:{to}", maxResults=1)
            .execute()
        )
        msgs = results.get("messages", [])
        if msgs:
            msg = service.users().messages().get(
                userId="me", id=msgs[0]["id"], format="metadata"
            ).execute()
            headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
            orig = headers.get("Subject", "")
            if orig:
                subject = orig if orig.startswith("Re:") else f"Re: {orig}"
    except Exception:
        pass

    message = MIMEText(text)
    message["to"]      = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    logger.info(f"Email sent → {to}")


async def send_email_to_rep(to: str, text: str):
    """Send email to a sales rep for slot confirmation."""
    service = _gmail_service()
    message = MIMEText(text)
    message["to"]      = to
    message["subject"] = "Nexus AI — New Lead / Slot Confirmation Required"
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    logger.info(f"Rep email sent → {to}")


# ── Telegram ───────────────────────────────────────────────────────────────────

async def _send_telegram(chat_id: str, text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    url   = f"https://api.telegram.org/bot{token}/sendMessage"
    # Remove markdown that Telegram might not support
    clean_text = text.replace("*", "").replace("_", "")
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json={
            "chat_id": chat_id,
            "text":    text,
            "parse_mode": "Markdown",
        }, timeout=10)
        if resp.status_code != 200:
            # Retry without markdown
            await client.post(url, json={
                "chat_id": chat_id,
                "text":    clean_text,
            }, timeout=10)
            logger.warning(f"Telegram markdown failed, sent plain text → {chat_id}")
        else:
            logger.info(f"Telegram sent → {chat_id}")


# ── Unified send ───────────────────────────────────────────────────────────────

async def send_reply(channel: str, sender_id: str, text: str):
    try:
        if channel == "telegram":
            await _send_telegram(sender_id, text)
        elif channel == "email":
            await _send_email(sender_id, text)
        else:
            logger.warning(f"Channel not active: {channel} (coming soon)")
    except Exception as e:
        logger.error(f"send_reply failed [{channel} → {sender_id}]: {e}")
