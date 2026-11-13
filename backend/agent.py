"""
agent.py — dynamic sales assistant
- Handles requirement updates mid-conversation
- Qualifies BEFORE saying "great fit"
- Gives helpful rejection with actionable advice
- Natural conversation throughout
"""
import json, logging, os, re
from openai import OpenAI
from supabase import create_client, Client
from qualify import qualify_lead, route_lead
from calendar_utils import get_slots, create_booking
from channels import send_reply, send_email_to_rep

logger = logging.getLogger(__name__)

supabase: Client = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)

client = OpenAI(
    api_key=os.environ["OPENROUTER_API_KEY"],
    base_url="https://openrouter.ai/api/v1"
)
MODEL = "meta-llama/llama-3.1-8b-instruct"

REP_EMAILS = {
    "Arjun": os.getenv("ARJUN_EMAIL", "rishabhkd28@gmail.com"),
    "Priya": os.getenv("PRIYA_EMAIL",  "rishabhkd28@gmail.com"),
}

# ── Rule-based extraction ─────────────────────────────────────────────────────

SERVICE_MAP = {
    "Automation": ["workflow automation", "automat", "workflow", "rpa",
                   "process automation", "robotic", "automate"],
    "BI":         ["bi", "business intelligence", "dashboard", "power bi",
                   "tableau", "reporting tool"],
    "Analytics":  ["analytics", "analytical", "analysis", "reports", "reporting",
                   "insights", "data report", "data analysis", "sales data",
                   "metrics", "kpi"],
    "AI":         ["ai", "artificial intelligence", "chatbot", "chat bot",
                   "llm", "agent", "machine learning", "nlp", "gpt"],
    "CRM":        ["crm", "customer relationship", "sales tracking",
                   "sales pipeline", "lead management"],
}

DM_KEYWORDS = ["cto", "ceo", "coo", "cfo", "founder", "co-founder", "owner",
               "director", "head of", "decision maker", "decision-maker",
               "i decide", "managing director", "md", "president",
               "i am the one", "i handle", "i manage"]

BUDGET_PATTERNS = [
    (r'(\d+(?:\.\d+)?)\s*lakh', lambda m: int(float(m.group(1)) * 100_000)),
    (r'(\d+(?:\.\d+)?)\s*lac',  lambda m: int(float(m.group(1)) * 100_000)),
    (r'(\d+(?:\.\d+)?)\s*l\b',  lambda m: int(float(m.group(1)) * 100_000)),
    (r'rs\.?\s*(\d[\d,]*)',      lambda m: int(m.group(1).replace(",", ""))),
    (r'inr\s*(\d[\d,]*)',        lambda m: int(m.group(1).replace(",", ""))),
    (r'(\d[\d,]*)\s*inr',        lambda m: int(m.group(1).replace(",", ""))),
    (r'(\d+)\s*k\b',             lambda m: int(m.group(1)) * 1_000),
    (r'\$(\d+)',                  lambda m: int(m.group(1)) * 83),
    (r'budget\s+(?:is\s+|of\s+|changed\s+to\s+|now\s+)?(\d[\d,]*)',
                                  lambda m: int(m.group(1).replace(",", ""))),
    (r'changed\s+(?:my\s+)?budget\s+to\s+(\d[\d,]*)',
                                  lambda m: int(m.group(1).replace(",", ""))),
    (r'now\s+(\d[\d,]*)',         lambda m: int(m.group(1).replace(",", ""))),
    (r'around\s+(\d[\d,]*)',      lambda m: int(m.group(1).replace(",", ""))),
]

TIMELINE_PATTERNS = [
    (r'(\d+)\s*month',           lambda m: int(m.group(1))),
    (r'(\d+)\s*week',            lambda m: max(1, round(int(m.group(1)) / 4.3))),
    (r'(\d+)\s*day',             lambda m: max(1, round(int(m.group(1)) / 30))),
    (r'next\s+quarter',          lambda m: 3),
    (r'this\s+quarter',          lambda m: 2),
    (r'asap|urgent|immediately', lambda m: 1),
    (r'few\s+weeks',             lambda m: 1),
    (r'couple\s+of\s+months',    lambda m: 2),
]

UPDATE_SIGNALS = [
    "changed", "update", "actually", "correction", "i mean",
    "not that", "instead", "revised", "new budget", "different",
    "wait", "sorry", "my bad", "scratch that", "new requirement",
]


def is_update_message(text: str) -> bool:
    """Detect if user is updating a previous answer."""
    t = text.lower()
    return any(sig in t for sig in UPDATE_SIGNALS)


def extract_fields(text: str, existing: dict, is_update: bool = False) -> dict:
    """
    Extract fields from text.
    If is_update=True, overwrite existing values with new ones from this message.
    """
    t = text.lower()
    result = dict(existing or {})

    # Budget — always re-extract from latest message if update signal
    budget_found = None
    for pattern, fn in BUDGET_PATTERNS:
        m = re.search(pattern, t)
        if m:
            try:
                val = fn(m)
                if val >= 1000:
                    budget_found = val
                    break
            except Exception:
                continue

    if budget_found:
        result["budget"] = budget_found  # always overwrite budget if found

    # Decision maker
    if result.get("decision_maker") is None or is_update:
        for kw in DM_KEYWORDS:
            if kw in t:
                result["decision_maker"] = True
                break
        if "not the decision" in t or "need approval" in t:
            result["decision_maker"] = False

    # Need/service
    need_found = None
    for service, keywords in SERVICE_MAP.items():
        if any(kw in t for kw in keywords):
            need_found = service
            break
    if need_found and (not result.get("need") or is_update):
        result["need"] = need_found

    # Timeline
    timeline_found = None
    for pattern, fn in TIMELINE_PATTERNS:
        m = re.search(pattern, t)
        if m:
            try:
                timeline_found = fn(m)
                break
            except Exception:
                continue
    if timeline_found and (not result.get("timeline_months") or is_update):
        result["timeline_months"] = timeline_found

    # Email
    email_match = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]+', text)
    if email_match:
        result["contact_email"] = email_match.group(0)

    return result


def get_missing(fields: dict, channel: str = "email") -> list:
    missing = []
    if channel == "telegram":
        if not fields.get("contact_email"): missing.append("contact_email")
        if not fields.get("name"):          missing.append("name")
    if not fields.get("need"):              missing.append("need")
    if not fields.get("budget"):            missing.append("budget")
    if fields.get("decision_maker") is None: missing.append("decision_maker")
    if not fields.get("timeline_months"):   missing.append("timeline_months")
    return missing


# ── LLM for natural replies ───────────────────────────────────────────────────

SYSTEM_PROMPT = """You are Alex, a friendly sales assistant at Nexus Analytics Consulting.

Personality: warm, helpful, honest — like a knowledgeable friend, not a pushy salesperson.

SERVICES:
- BI and Dashboard Development     from ₹80,000
- Data Analytics and Insight Reports from ₹50,000
- AI Workflow Automation           from ₹60,000
- AI Agent and Chatbot Development from ₹75,000
- CRM Integration and Sales Analytics from ₹55,000

RULES:
- Always acknowledge what the person said — especially if they updated something
- Ask for ONLY ONE missing field at a time, naturally
- Keep replies to 2-3 sentences max
- Never use bullet points
- Never say "great fit" — Python decides that, not you
- Sound human and conversational

HOW TO ASK NATURALLY:
- name: "By the way, what should I call you?"
- contact_email: "What email should I send your confirmation to?"
- need: "What kind of solution are you looking for — dashboards, analytics, AI automation?"
- budget: "Roughly what budget are you working with for this?"
- decision_maker: "And are you the one who'd be signing off on this?"
- timeline_months: "When are you hoping to get this done?"

If user updated something, acknowledge it first: "Got it, updated your budget to X. Let me check..."

Reply in plain conversational text. 2-3 sentences max."""


def call_llm(history, new_text, missing_fields, extracted, is_update=False):
    if not missing_fields and not is_update:
        return "Let me check that for you right away..."

    next_missing = missing_fields[0] if missing_fields else None

    known = []
    if extracted.get("name"):            known.append(f"name: {extracted['name']}")
    if extracted.get("contact_email"):   known.append(f"email: {extracted['contact_email']}")
    if extracted.get("need"):            known.append(f"need: {extracted['need']}")
    if extracted.get("budget"):          known.append(f"budget: Rs.{extracted['budget']:,}")
    if extracted.get("decision_maker") is True: known.append("decision maker: yes")
    if extracted.get("timeline_months"): known.append(f"timeline: {extracted['timeline_months']} months")

    system = SYSTEM_PROMPT
    if known:
        system += f"\n\nYOU ALREADY KNOW: {', '.join(known)}. Do NOT ask about these again."
    if is_update:
        system += "\n\nUser just updated their requirements. Acknowledge the change naturally."
    if next_missing:
        system += f"\n\nNEXT: Ask naturally for their {next_missing}."
    else:
        system += "\n\nAll info collected. Say you're checking availability right now."

    messages = [{"role": "system", "content": system}]
    for msg in history[-6:]:
        messages.append({"role": "user" if msg["role"] == "user" else "assistant",
                         "content": msg["content"]})
    messages.append({"role": "user", "content": new_text})

    try:
        response = client.chat.completions.create(
            model=MODEL, messages=messages, temperature=0.4, max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM error: {e}")
        fallback = {
            "name":           "What should I call you?",
            "contact_email":  "What email should I send your confirmation to?",
            "need":           "What kind of solution are you looking for?",
            "budget":         "Roughly what budget are you working with?",
            "decision_maker": "Are you the decision maker for this project?",
            "timeline_months":"When are you hoping to get this done?",
        }
        return fallback.get(next_missing, "Could you tell me a bit more?")


def build_not_qualified_reply(evidence: dict) -> str:
    """Build a helpful rejection message with actionable advice."""
    disqualifiers = evidence.get("disqualifiers", [])
    reply_parts   = ["Thanks for reaching out! I've reviewed your details."]

    for d in disqualifiers:
        if "budget" in d and "50,000" in d:
            budget = evidence.get("budget", 0)
            reply_parts.append(
                f"Your current budget of ₹{budget:,} is a bit below our minimum of ₹50,000. "
                f"If you could stretch to ₹50,000, we'd be happy to explore options together."
            )
        elif "timeline" in d:
            reply_parts.append(
                "Our projects typically need at least a 1-3 month runway to deliver quality results. "
                "If your timeline has flexibility, we'd love to chat."
            )
        elif "decision" in d:
            reply_parts.append(
                "We'd need to connect with the decision maker before moving forward. "
                "Would you be able to loop them in?"
            )
        elif "need" in d:
            reply_parts.append(
                "We specialize in BI, Analytics, AI, Automation, and CRM. "
                "Could you clarify which area you need help with?"
            )

    reply_parts.append("Feel free to reply if anything changes — we'd love to help when the time is right!")
    return " ".join(reply_parts)


# ── DB helpers ────────────────────────────────────────────────────────────────

def get_or_create_lead(channel, sender_id, sender_name=""):
    res = supabase.table("leads").select("*").eq("channel", channel).eq("sender_id", sender_id).limit(1).execute()
    if res.data:
        return res.data[0]
    new_lead = {"channel": channel, "sender_id": sender_id, "sender_name": sender_name,
                "stage": "NEW", "qualified": None, "assigned_rep": None,
                "evidence_json": {}, "human_takeover": False}
    created = supabase.table("leads").insert(new_lead).execute()
    lead = created.data[0]
    log_action(lead["id"], "lead created")
    return lead

def get_messages(lead_id):
    res = supabase.table("messages").select("role,content").eq("lead_id", lead_id).order("created_at").execute()
    return res.data or []

def save_message(lead_id, role, content):
    supabase.table("messages").insert({"lead_id": lead_id, "role": role, "content": content}).execute()

def update_lead(lead_id, patch):
    supabase.table("leads").update(patch).eq("id", lead_id).execute()

def log_action(lead_id, event):
    supabase.table("action_log").insert({"lead_id": lead_id, "event": event}).execute()


# ── Rep slot confirmation ─────────────────────────────────────────────────────

async def handle_rep_reply(sender_id, text):
    rep_name = None
    for name, email in REP_EMAILS.items():
        if email == sender_id:
            rep_name = name
            break
    if not rep_name:
        return

    res = supabase.table("leads").select("*").eq("assigned_rep", rep_name).eq("stage", "SCHEDULING").order("updated_at", desc=True).limit(1).execute()
    if not res.data:
        return

    lead    = res.data[0]
    lead_id = lead["id"]
    text_l  = text.lower().strip()

    choice = None
    if re.search(r'\b1\b|first|slot 1', text_l):  choice = 0
    elif re.search(r'\b2\b|second|slot 2', text_l): choice = 1
    elif re.search(r'\b3\b|third|slot 3', text_l):  choice = 2

    if choice is None:
        await send_email_to_rep(sender_id,
            f"Please reply with 1, 2, or 3 to confirm the slot for {lead.get('sender_name') or lead['sender_id']}.")
        return

    slots = get_slots(rep_name)
    if choice >= len(slots):
        return

    slot    = slots[choice]
    booking = create_booking(lead, slot)

    if booking:
        update_lead(lead_id, {"stage": "BOOKED"})
        log_action(lead_id, "booking confirmed by rep")

        evidence      = lead.get("evidence_json") or {}
        contact_email = evidence.get("contact_email")
        channel       = lead["channel"]
        lead_contact  = contact_email if contact_email else lead["sender_id"]
        notify_channel = "email" if contact_email else channel

        lead_msg = (
            f"Great news! Your discovery call is confirmed! 🎉\n\n"
            f"📅 {slot['label']}\n"
            f"👤 You'll be speaking with {rep_name} from our team.\n\n"
            f"A calendar invite has been sent to your email. Looking forward to speaking with you!"
        )
        await send_reply(notify_channel, lead_contact, lead_msg)
        save_message(lead_id, "assistant", lead_msg)

        if channel == "telegram" and contact_email:
            await send_reply("telegram", lead["sender_id"], lead_msg)

        await send_email_to_rep(sender_id,
            f"✅ Confirmed! Booking with {lead.get('sender_name') or lead_contact} at {slot['label']}.")
        log_action(lead_id, f"lead notified — booked at {slot['label']}")


# ── Main loop ─────────────────────────────────────────────────────────────────

async def process_message(channel, sender_id, text, sender_name=""):
    # Rep replying to slot confirmation
    if channel == "email" and sender_id in REP_EMAILS.values():
        await handle_rep_reply(sender_id, text)
        return

    lead    = get_or_create_lead(channel, sender_id, sender_name)
    lead_id = lead["id"]

    if lead.get("human_takeover"):
        await send_reply(channel, sender_id, "Our team has taken over and will be with you shortly!")
        return

    history = get_messages(lead_id)
    save_message(lead_id, "user", text)

    if sender_name and not lead.get("sender_name"):
        update_lead(lead_id, {"sender_name": sender_name})

    if lead["stage"] == "NEW":
        update_lead(lead_id, {"stage": "GATHERING"})
        lead["stage"] = "GATHERING"

    # Detect if user is updating requirements
    update_signal = is_update_message(text)

    # If previously booked/not-qualified but user is updating → reopen
    if lead["stage"] in ("NOT_QUALIFIED", "BOOKED", "SCHEDULING") and update_signal:
        update_lead(lead_id, {"stage": "QUALIFYING", "qualified": None})
        lead["stage"] = "QUALIFYING"
        log_action(lead_id, "requirements updated — re-qualifying")

    # Rule-based extraction
    all_user_text = " ".join([m["content"] for m in history if m["role"] == "user"] + [text])
    existing  = lead.get("evidence_json") or {}

    if sender_name and not existing.get("name"):
        existing["name"] = sender_name

    # Always re-extract from latest message for updates
    extracted = extract_fields(all_user_text, existing, is_update=update_signal)

    # Also extract from just the latest message to catch updates
    latest_extracted = extract_fields(text, {}, is_update=True)
    for key in ["budget", "need", "timeline_months", "contact_email"]:
        if latest_extracted.get(key):
            extracted[key] = latest_extracted[key]

    missing = get_missing(extracted, channel)

    logger.info(f"Extracted: {extracted} | Missing: {missing} | Update: {update_signal}")

    if extracted and lead["stage"] == "GATHERING":
        update_lead(lead_id, {"stage": "QUALIFYING"})
        lead["stage"] = "QUALIFYING"

    if not missing:
        # All fields collected — now qualify
        result = qualify_lead(extracted)
        patch  = {"qualified": result["qualified"], "evidence_json": {**result["evidence"],
                   "contact_email": extracted.get("contact_email"),
                   "name": extracted.get("name") or lead.get("sender_name")}}

        if result["qualified"]:
            rep = route_lead(extracted.get("need", ""))
            patch["assigned_rep"] = rep
            patch["stage"]        = "SCHEDULING"
            log_action(lead_id, f"qualified → routed to {rep}")

            reply = (
                f"Great news — you're a perfect fit! 🎉\n\n"
                f"I've matched you with {rep} from our team. "
                f"We're checking their calendar right now and will send you a confirmed time shortly.\n\n"
                f"Keep an eye on your inbox!"
            )

            slots     = get_slots(rep)
            rep_email = REP_EMAILS[rep]
            lead_name = extracted.get("name") or lead.get("sender_name") or sender_id
            contact   = extracted.get("contact_email") or sender_id
            slot_lines = "\n".join([f"{i+1}. {s['label']}" for i, s in enumerate(slots)])

            rep_msg = (
                f"Hi {rep},\n\nNew qualified lead!\n\n"
                f"Name: {lead_name}\n"
                f"Contact: {contact}\n"
                f"Channel: {channel}\n"
                f"Need: {extracted.get('need')}\n"
                f"Budget: Rs.{result['evidence'].get('budget', 0):,}\n"
                f"Timeline: {extracted.get('timeline_months')} months\n\n"
                f"Reply with 1, 2, or 3 to confirm their slot:\n\n{slot_lines}\n\n"
                f"The lead will be notified automatically."
            )
            await send_email_to_rep(rep_email, rep_msg)
            log_action(lead_id, f"rep {rep} notified")

        else:
            patch["stage"] = "NOT_QUALIFIED"
            log_action(lead_id, "not qualified")
            reply = build_not_qualified_reply(result["evidence"])

        update_lead(lead_id, patch)
        lead.update(patch)

    else:
        # Still missing fields — LLM generates natural follow-up
        reply = call_llm(history, text, missing, extracted, is_update=update_signal)
        update_lead(lead_id, {"evidence_json": extracted})

    save_message(lead_id, "assistant", reply)
    await send_reply(channel, sender_id, reply)
