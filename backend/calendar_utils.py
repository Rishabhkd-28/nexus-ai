"""
calendar_utils.py — Google Calendar integration.
"""
import json, logging, os, re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from supabase import create_client

logger = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")

REP_CALENDARS = {
    "Arjun": os.getenv("ARJUN_CALENDAR_ID", "eternal.love.kd@gmail.com"),
    "Priya": os.getenv("PRIYA_CALENDAR_ID",  "eternal.love.kd@gmail.com"),
}

REP_EMAILS = {
    "Arjun": os.getenv("ARJUN_EMAIL", "rishabhkd28@gmail.com"),
    "Priya": os.getenv("PRIYA_EMAIL",  "rishabhkd28@gmail.com"),
}

REP_HOURS = {
    "Arjun": (9, 18),
    "Priya": (10, 19),
}


def _get_calendar_service():
    token_data = json.loads(os.environ["GOOGLE_TOKEN_JSON"])
    creds = Credentials(
        token         = token_data.get("token"),
        refresh_token = token_data.get("refresh_token"),
        token_uri     = "https://oauth2.googleapis.com/token",
        client_id     = os.environ["GOOGLE_CLIENT_ID"],
        client_secret = os.environ["GOOGLE_CLIENT_SECRET"],
        scopes        = ["https://www.googleapis.com/auth/calendar"],
    )
    return build("calendar", "v3", credentials=creds)


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def get_slots(rep: str, num_slots: int = 3) -> list:
    try:
        service = _get_calendar_service()
        calendar_id = REP_CALENDARS.get(rep, "primary")
        start_hour, end_hour = REP_HOURS.get(rep, (9, 18))

        now   = datetime.now(IST)
        slots = []
        day   = now.date()

        for _ in range(14):
            if len(slots) >= num_slots:
                break
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue

            day_start = datetime(day.year, day.month, day.day, start_hour, 0, tzinfo=IST)
            day_end   = datetime(day.year, day.month, day.day, end_hour,   0, tzinfo=IST)
            busy = _get_busy_times(service, calendar_id, day_start, day_end)

            cursor = day_start
            while cursor + timedelta(minutes=30) <= day_end and len(slots) < num_slots:
                window_end = cursor + timedelta(minutes=30)
                if not _overlaps(cursor, window_end, busy):
                    slots.append({
                        "start": cursor.isoformat(),
                        "end":   window_end.isoformat(),
                        "label": cursor.strftime("%A, %d %b · %I:%M %p IST"),
                    })
                cursor += timedelta(minutes=30)

        return slots

    except Exception as e:
        logger.error(f"get_slots failed: {e}")
        return _dummy_slots()


def _get_busy_times(service, calendar_id, start, end):
    try:
        body = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "items":   [{"id": calendar_id}],
        }
        resp = service.freebusy().query(body=body).execute()
        return resp.get("calendars", {}).get(calendar_id, {}).get("busy", [])
    except Exception as e:
        logger.error(f"freebusy failed: {e}")
        return []


def _overlaps(start, end, busy):
    for b in busy:
        try:
            b_start = _parse_dt(b["start"])
            b_end   = _parse_dt(b["end"])
            if start < b_end and end > b_start:
                return True
        except Exception:
            continue
    return False


def _dummy_slots():
    now  = datetime.now(IST)
    base = now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return [
        {
            "start": (base + timedelta(hours=i*2)).isoformat(),
            "end":   (base + timedelta(hours=i*2, minutes=30)).isoformat(),
            "label": (base + timedelta(hours=i*2)).strftime("%A, %d %b · %I:%M %p IST"),
        }
        for i in range(3)
    ]


def format_slot_offer(rep, slots, preamble=True):
    if not slots:
        return f"I couldn't find open slots for {rep}. Our team will reach out to schedule."
    lines = [f"{i+1}. {s['label']}" for i, s in enumerate(slots)]
    body  = "\n".join(lines)
    if preamble:
        return f"Great news — matched with {rep}!\n\n{body}\n\nReply with 1, 2, or 3."
    return f"{body}\n\nReply with 1, 2, or 3."


def create_booking(lead: dict, slot: dict) -> object:
    """
    Create Google Calendar event with BOTH the lead and the rep as attendees.
    Both will receive a Google Calendar invite in their email.
    """
    calendar_event_id = None
    rep = lead["assigned_rep"]
    rep_email = REP_EMAILS.get(rep, "rishabhkd28@gmail.com")
    lead_email = lead["sender_id"]

    try:
        service  = _get_calendar_service()
        calendar = REP_CALENDARS.get(rep, "primary")

        event_body = {
            "summary":     f"Discovery Call — {lead.get('sender_name') or lead_email}",
            "description": (
                f"Sales discovery call\n"
                f"Lead: {lead_email}\n"
                f"Rep: {rep}\n"
                f"Channel: {lead.get('channel', 'email')}"
            ),
            "start": {"dateTime": slot["start"].replace("+05:30", "") + "+05:30", "timeZone": "Asia/Kolkata"},
            "end":   {"dateTime": slot["end"].replace("+05:30", "") + "+05:30", "timeZone": "Asia/Kolkata"},
            # Both lead AND rep get a calendar invite
            "attendees": [
                {"email": lead_email, "displayName": lead.get("sender_name") or lead_email},
                {"email": rep_email,  "displayName": rep},
            ],
            "reminders": {
                "useDefault": False,
                "overrides":  [
                    {"method": "email", "minutes": 60},
                    {"method": "popup", "minutes": 10},
                ],
            },
        }

        event = service.events().insert(
            calendarId=calendar,
            body=event_body,
            sendUpdates="all",  # sends invite emails to all attendees
        ).execute()
        calendar_event_id = event.get("id")
        logger.info(f"Calendar event created: {calendar_event_id} | attendees: {lead_email}, {rep_email}")

    except Exception as e:
        logger.error(f"Calendar event creation failed: {e}")

    # Save to DB
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    try:
        res = (
            supabase.table("bookings")
            .upsert(
                {
                    "lead_id":           lead["id"],
                    "rep":               rep,
                    "slot_start":        slot["start"],
                    "slot_end":          slot["end"],
                    "calendar_event_id": calendar_event_id,
                },
                on_conflict="lead_id,slot_start",
            )
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Booking DB insert failed: {e}")
        return None


def parse_slot_choice(text, lead_id):
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    msgs = (
        supabase.table("messages")
        .select("content")
        .eq("lead_id", lead_id)
        .eq("role", "assistant")
        .order("created_at", desc=True)
        .limit(5)
        .execute()
        .data or []
    )

    offer_msg = None
    for m in msgs:
        if "1." in m["content"] or "1️⃣" in m["content"]:
            offer_msg = m["content"]
            break

    if not offer_msg:
        return None

    text_l = text.lower().strip()
    choice = None
    if re.search(r'\b1\b|first|slot 1', text_l): choice = 0
    elif re.search(r'\b2\b|second|slot 2', text_l): choice = 1
    elif re.search(r'\b3\b|third|slot 3', text_l): choice = 2

    if choice is None:
        return None

    lead_res = (
        supabase.table("leads")
        .select("assigned_rep")
        .eq("id", lead_id)
        .single()
        .execute()
    )
    rep = lead_res.data.get("assigned_rep") if lead_res.data else None
    if not rep:
        return None

    slots = get_slots(rep)
    if choice < len(slots):
        return slots[choice]["start"]
    return None
