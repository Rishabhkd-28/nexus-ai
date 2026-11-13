"""
agent.py — dynamic sales assistant with off-topic handling
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

SERVICE_MAP = {
    "Automation": ["workflow automation","automat","workflow","rpa","process automation","robotic","automate"],
    "BI":         ["bi","business intelligence","dashboard","power bi","tableau","reporting tool"],
    "Analytics":  ["analytics","analysis","reports","reporting","insights","data report","data analysis","sales data","metrics","kpi"],
    "AI":         ["ai","artificial intelligence","chatbot","chat bot","llm","agent","machine learning","nlp","gpt"],
    "CRM":        ["crm","customer relationship","sales tracking","sales pipeline","lead management"],
}

DM_KEYWORDS = ["cto","ceo","coo","cfo","founder","co-founder","owner","director","head of","decision maker","i decide","managing director","md","president"]

BUDGET_PATTERNS = [
    (r'(\d+(?:\.\d+)?)\s*lakh', lambda m: int(float(m.group(1))*100_000)),
    (r'(\d+(?:\.\d+)?)\s*lac',  lambda m: int(float(m.group(1))*100_000)),
    (r'(\d+(?:\.\d+)?)\s*l\b',  lambda m: int(float(m.group(1))*100_000)),
    (r'rs\.?\s*(\d[\d,]*)',      lambda m: int(m.group(1).replace(",",""))),
    (r'(\d+)\s*k\b',             lambda m: int(m.group(1))*1_000),
    (r'budget\s+(?:is\s+|of\s+|changed\s+to\s+)?(\d[\d,]*)', lambda m: int(m.group(1).replace(",",""))),
    (r'around\s+(\d[\d,]*)',     lambda m: int(m.group(1).replace(",",""))),
]

TIMELINE_PATTERNS = [
    (r'(\d+)\s*month',           lambda m: int(m.group(1))),
    (r'(\d+)\s*week',            lambda m: max(1, round(int(m.group(1))/4.3))),
    (r'next\s+quarter',          lambda m: 3),
    (r'asap|urgent|immediately', lambda m: 1),
    (r'few\s+weeks',             lambda m: 1),
    (r'couple\s+of\s+months',    lambda m: 2),
]

UPDATE_SIGNALS = ["changed","update","actually","correction","i mean","not that","instead","revised","new budget","different","wait","sorry","scratch that"]


def is_update_message(text):
    return any(sig in text.lower() for sig in UPDATE_SIGNALS)


def extract_fields(text, existing, is_update=False):
    t = text.lower()
    result = dict(existing or {})

    budget_found = None
    for pattern, fn in BUDGET_PATTERNS:
        m = re.search(pattern, t)
        if m:
            try:
                val = fn(m)
                if val >= 1000:
                    budget_found = val
                    break
            except:
                continue
    if budget_found:
        result["budget"] = budget_found

    if result.get("decision_maker") is None or is_update:
        for kw in DM_KEYWORDS:
            if kw in t:
                result["decision_maker"] = True
                break
        if "not the decision" in t or "need approval" in t:
            result["decision_maker"] = False

    need_found = None
    for service, keywords in SERVICE_MAP.items():
        if any(kw in t for kw in keywords):
            need_found = service
            break
    if need_found and (not result.get("need") or is_update):
        result["need"] = need_found

    timeline_found = None
    for pattern, fn in TIMELINE_PATTERNS:
        m = re.search(pattern, t)
        if m:
            try:
                timeline_found = fn(m)
                break
            except:
                continue
    if timeline_found and (not result.get("timeline_months") or is_update):
        result["timeline_months"] = timeline_found

    email_match = re.search(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]+', text)
    if email_match:
        result["contact_email"] = email_match.group(0)

    return result


def get_missing(fields, channel="email"):
    missing = []
    if channel == "telegram":
        if not fields.get("contact_email"): missing.append("contact_email")
    if not fields.get("need"):              missing.append("need")
    if not fields.get("budget"):            missing.append("budget")
    if fields.get("decision_maker") is None: missing.append("decision_maker")
    if not fields.get("timeline_months"):   missing.append("timeline_months")
    return missing


SYSTEM_PROMPT = """You are Alex, a friendly sales assistant at Nexus Analytics Consulting.

Personality: warm, helpful, conversational — like a knowledgeable friend.

SERVICES:
- BI and Dashboard Development     from Rs.80,000
- Data Analytics and Insight Reports from Rs.50,000
- AI Workflow Automation           from Rs.60,000
- AI Agent and Chatbot Development from Rs.75,000
- CRM Integration and Sales Analytics from Rs.55,000

YOUR JOB: Have a natural conversation and gently collect ONE missing piece of info at a time.

RULES:
- Always acknowledge what the person said first
- Ask for ONLY ONE missing field naturally
- Keep replies to 2-3 sentences max
- Never use bullet points
- If user says something unrelated (personal questions, random chat, greetings), acknowledge it warmly and briefly steer back to business
- Never ignore any message
- Sound human and warm

HOW TO ASK:
- contact_email: "What email should I send your confirmation to?"
- need: "What kind of solution are you looking for — dashboards, analytics, AI automation, or something else?"
- budget: "Just so I point you to the right package, roughly what budget are you working with?"
- decision_maker: "And are you the one who'd be signing off on this?"
- timeline_months: "When are you hoping to get started?"

Reply in plain text. 2-3 sentences max."""


def call_llm(history, new_text, missing_fields, extracted, is_update=False):
    if not missing_fields:
        return "Let me check that for you right away..."

    next_missing = missing_fields[0]
    known = []
    if extracted.get("need"):           known.append(f"need: {extracted['need']}")
    if extracted.get("budget"):         known.append(f"budget: Rs.{extracted['budget']:,}")
    if extracted.get("decision_maker") is True: known.append("decision maker: yes")
    if extracted.get("timeline_months"): known.append(f"timeline: {extracted['timeline_months']} months")
    if extracted.get("contact_email"):  known.append(f"email: {extracted['contact_email']}")

    system = SYSTEM_PROMPT
    if known:
        system += f"\n\nYOU ALREADY KNOW: {', '.join(known)}. Do NOT ask about these again."
    if is_update:
        system += "\n\nUser just updated their requirements. Acknowledge the change naturally."
    system += f"\n\nNEXT: Ask naturally for their {next_missing}."

    messages = [{"role": "system", "content": system}]
    for msg in history[-6:]:
        messages.append({"role": "user" if msg["role"] == "user" else "assistant", "content": msg["content"]})
    messages.append({"role": "user", "content": new_text})

    try:
        response = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.4, max_tokens=150)
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"LLM error: {e}")
        fallback = {
            "contact_email":  "What email should I send your confirmation to?",
            "need":           "What kind of solution are you looking for?",
            "budget":         "Roughly what budget are you working with?",
            "decision_maker": "Are you the decision maker for this project?",
            "timeline_months":"When are you hoping to get this done?",
        }
        return fallback.get(next_missing, "Could you tell me a bit more about your project?")


def build_not_qualified_reply(evidence):
    disqualifiers = evidence.get("disqualifiers", [])
    reply_parts = ["Thanks for reaching out!"]
    for d in disqualifiers:
        if "budget" in d and "50,000" in d:
            budget = evidence.get("budget", 0)
            reply_parts.append(f"Your current budget of Rs.{budget:,} is a bit below our minimum of Rs.50,000. If you could stretch to Rs.50,000, we'd love to help.")
        elif "timeline" in d:
            reply_parts.append("Our projects typically need a 1-3 month runway. If your timeline has flexibility, we'd love to chat.")
        elif "decision" in d:
            reply_parts.append("We'd need to connect with the decision maker before moving forward. Could you loop them in?")
        elif "need" in d:
            reply_parts.append("We specialize in BI, Analytics, AI, Automation, and CRM. Could you clarify which area you need help with?")
    reply_parts.append("Feel free to reach out again if anything changes!")
    return " ".join(reply_parts)


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

    lead = res.data[0]
    lead_id = lead["id"]
    text_l = text.lower().strip()

    choice = None
    if re.search(r'\b1\b|first|slot 1', text_l):  choice = 0
    elif re.search(r'\b2\b|second|slot 2', text_l): choice = 1
    elif re.search(r'\b3\b|third|slot 3', text_l):  choice = 2

    if choice is None:
        await send_email_to_rep(sender_id, f"Please reply with 1, 2, or 3 to confirm the slot for {lead.get('sender_name') or lead['sender_id']}.")
        return

    slots = get_slots(rep_name)
    if choice >= len(slots):
        return

    slot = slots[choice]
    booking = create_booking(lead, slot)

    if booking:
        update_lead(lead_id, {"stage": "BOOKED"})
        log_action(lead_id, "booking confirmed by rep")
        evidence = lead.get("evidence_json") or {}
        contact_email = evidence.get("contact_email")
        channel = lead["channel"]
        lead_contact = contact_email if contact_email else lead["sender_id"]
        notify_channel = "email" if contact_email else channel

        lead_msg = (
            f"Great news! Your discovery call is confirmed!\n\n"
            f"Date: {slot['label']}\n"
            f"You'll be speaking with {rep_name} from our team.\n\n"
            f"A calendar invite has been sent to your email. Looking forward to speaking with you!"
        )
        await send_reply(notify_channel, lead_contact, lead_msg)
        save_message(lead_id, "assistant", lead_msg)
        if channel == "telegram" and contact_email:
            await send_reply("telegram", lead["sender_id"], lead_msg)
        await send_email_to_rep(sender_id, f"Confirmed! Booking with {lead.get('sender_name') or lead_contact} at {slot['label']}.")
        log_action(lead_id, f"lead notified — booked at {slot['label']}")


async def process_message(channel, sender_id, text, sender_name=""):
    if channel == "email" and sender_id in REP_EMAILS.values():
        await handle_rep_reply(sender_id, text)
        return

    lead = get_or_create_lead(channel, sender_id, sender_name)
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

    update_signal = is_update_message(text)

    if lead["stage"] in ("NOT_QUALIFIED", "BOOKED", "SCHEDULING") and update_signal:
        update_lead(lead_id, {"stage": "QUALIFYING", "qualified": None})
        lead["stage"] = "QUALIFYING"
        log_action(lead_id, "requirements updated — re-qualifying")

    all_user_text = " ".join([m["content"] for m in history if m["role"] == "user"] + [text])
    existing = lead.get("evidence_json") or {}
    if sender_name and not existing.get("name"):
        existing["name"] = sender_name

    extracted = extract_fields(all_user_text, existing, is_update=update_signal)
    latest = extract_fields(text, {}, is_update=True)
    for key in ["budget", "need", "timeline_months", "contact_email"]:
        if latest.get(key):
            extracted[key] = latest[key]

    missing = get_missing(extracted, channel)
    logger.info(f"Extracted: {extracted} | Missing: {missing}")

    if extracted and lead["stage"] == "GATHERING":
        update_lead(lead_id, {"stage": "QUALIFYING"})
        lead["stage"] = "QUALIFYING"

    if not missing:
        result = qualify_lead(extracted)
        patch = {"qualified": result["qualified"], "evidence_json": {**result["evidence"],
                 "contact_email": extracted.get("contact_email"),
                 "name": extracted.get("name") or lead.get("sender_name")}}

        if result["qualified"]:
            rep = route_lead(extracted.get("need", ""))
            patch["assigned_rep"] = rep
            patch["stage"] = "SCHEDULING"
            log_action(lead_id, f"qualified → routed to {rep}")

            reply = (
                f"You're a great fit for our services!\n\n"
                f"I've matched you with {rep} from our team. "
                f"We're checking their calendar and will send you a confirmed meeting time shortly!\n\n"
                f"Expect a confirmation soon."
            )

            slots = get_slots(rep)
            rep_email = REP_EMAILS[rep]
            lead_name = extracted.get("name") or lead.get("sender_name") or sender_id
            contact = extracted.get("contact_email") or sender_id
            slot_lines = "\n".join([f"{i+1}. {s['label']}" for i, s in enumerate(slots)])

            rep_msg = (
                f"Hi {rep},\n\nNew qualified lead!\n\n"
                f"Name: {lead_name}\nContact: {contact}\nChannel: {channel}\n"
                f"Need: {extracted.get('need')}\nBudget: Rs.{result['evidence'].get('budget',0):,}\n"
                f"Timeline: {extracted.get('timeline_months')} months\n\n"
                f"Reply with 1, 2, or 3 to confirm their slot:\n\n{slot_lines}\n\nThe lead will be notified automatically."
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
        reply = call_llm(history, text, missing, extracted, is_update=update_signal)
        update_lead(lead_id, {"evidence_json": extracted})

    save_message(lead_id, "assistant", reply)
    await send_reply(channel, sender_id, reply)
