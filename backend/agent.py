"""
agent.py — central message processing loop (OpenRouter / Llama)
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

SYSTEM_PROMPT = """You are a sales assistant for Nexus Analytics Consulting.

SERVICES:
- BI and Dashboard Development         from ₹80,000
- Data Analytics and Insight Reports   from ₹50,000
- AI Workflow Automation               from ₹60,000
- AI Agent and Chatbot Development     from ₹75,000
- CRM Integration and Sales Analytics  from ₹55,000

YOU MUST COLLECT EXACTLY THESE 4 FIELDS:
1. budget — any number or amount mentioned (1 lakh, 50k, 80000 etc.)
2. decision_maker — true if they say CTO, CEO, founder, owner, decision maker, yes I decide etc.
3. need — which service they want (BI, Analytics, AI, Automation, CRM)
4. timeline_months — how many months (2 months, next quarter=3, urgent=1 etc.)

CRITICAL RULES:
- If the user provides all 4 fields in one message — extract them ALL and return missing_fields as EMPTY [].
- Do NOT ask follow-up questions if you already have the information.
- Do NOT ask "what specific insights" or "what reports" — that is NOT one of the 4 fields.
- Do NOT ask for clarification on budget if any amount is mentioned.
- If need is mentioned (analytics, BI, AI etc.) — that is enough, map it to the service.
- Be warm and brief. ONE question maximum if something is missing.
- Never invent services or pricing.

FIELD MAPPING:
- "analytics" or "reports" or "insights" → need: "Analytics"
- "dashboard" or "BI" → need: "BI"  
- "AI" or "chatbot" or "automation" → need: "AI"
- "CRM" or "sales tracking" → need: "CRM"
- "CTO" or "CEO" or "founder" or "decision maker" or "I decide" → decision_maker: true
- Any amount (1 lakh, 50k, 80000) → extract as budget
- "2 months" or "next quarter" or "soon" or "urgent" → extract as timeline_months

ALWAYS reply ONLY with this exact JSON — no markdown, no preamble, no extra text:

{
  "reply": "your brief warm message",
  "extracted": {
    "budget": null,
    "decision_maker": null,
    "need": null,
    "timeline_months": null
  },
  "missing_fields": ["list only fields you genuinely don't know"]
}"""

def get_or_create_lead(channel, sender_id, sender_name=""):
    res = supabase.table("leads").select("*").eq("channel", channel).eq("sender_id", sender_id).limit(1).execute()
    if res.data:
        return res.data[0]
    new_lead = {
        "channel": channel, "sender_id": sender_id, "sender_name": sender_name,
        "stage": "NEW", "qualified": None, "assigned_rep": None,
        "evidence_json": {}, "human_takeover": False,
    }
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

def call_llm(history, new_text):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in history:
        messages.append({"role": "user" if msg["role"] == "user" else "assistant", "content": msg["content"]})
    messages.append({"role": "user", "content": new_text})

    response = client.chat.completions.create(model=MODEL, messages=messages, temperature=0.1, max_tokens=500)
    raw = response.choices[0].message.content.strip()

    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start >= 0 and end > start:
            raw = raw[start:end]
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"LLM non-JSON: {raw[:100]}")
        return {
            "reply": "Thank you! Could you share your budget and timeline for this project?",
            "extracted": {},
            "missing_fields": ["budget", "decision_maker", "need", "timeline_months"],
        }

async def handle_rep_reply(sender_id, text):
    rep_name = None
    for name, email in REP_EMAILS.items():
        if email == sender_id:
            rep_name = name
            break
    if not rep_name:
        return

    res = (
        supabase.table("leads").select("*")
        .eq("assigned_rep", rep_name)
        .eq("stage", "SCHEDULING")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return

    lead = res.data[0]
    lead_id = lead["id"]
    text_l = text.lower().strip()

    choice = None
    if re.search(r'\b1\b|first|slot 1', text_l): choice = 0
    elif re.search(r'\b2\b|second|slot 2', text_l): choice = 1
    elif re.search(r'\b3\b|third|slot 3', text_l): choice = 2

    if choice is None:
        await send_email_to_rep(sender_id,
            f"Please reply with 1, 2, or 3 to confirm the slot for {lead.get('sender_name') or lead['sender_id']}.")
        return

    slots = get_slots(rep_name)
    if choice >= len(slots):
        return

    slot = slots[choice]
    booking = create_booking(lead, slot)

    if booking:
        update_lead(lead_id, {"stage": "BOOKED"})
        log_action(lead_id, "booking confirmed by rep")

        lead_email = lead["sender_id"]
        lead_msg = (
            f"Great news! Your discovery call is confirmed! 🎉\n\n"
            f"📅 {slot['label']}\n"
            f"👤 You'll be speaking with {rep_name} from our team.\n\n"
            f"A calendar invite has been sent to your email. "
            f"Looking forward to speaking with you!"
        )
        await send_reply("email", lead_email, lead_msg)
        save_message(lead_id, "assistant", lead_msg)
        await send_email_to_rep(sender_id,
            f"✅ Confirmed! Booking with {lead.get('sender_name') or lead_email} at {slot['label']}. Calendar invite sent.")
        log_action(lead_id, f"lead notified — booked at {slot['label']}")

async def process_message(channel, sender_id, text, sender_name=""):
    # Rep replying to slot confirmation
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

    if lead["stage"] == "NEW":
        update_lead(lead_id, {"stage": "GATHERING"})
        lead["stage"] = "GATHERING"

    llm            = call_llm(history, text)
    reply          = llm.get("reply", "Could you tell me more about your project?")
    extracted      = llm.get("extracted", {})
    missing_fields = llm.get("missing_fields", [])

    if extracted and lead["stage"] == "GATHERING":
        update_lead(lead_id, {"stage": "QUALIFYING"})
        lead["stage"] = "QUALIFYING"

    if not missing_fields:
        result = qualify_lead(extracted)
        patch  = {"qualified": result["qualified"], "evidence_json": result["evidence"]}

        if result["qualified"]:
            rep = route_lead(extracted.get("need", ""))
            patch["assigned_rep"] = rep
            patch["stage"]        = "SCHEDULING"
            log_action(lead_id, f"qualified → routed to {rep}")

            reply = (
                f"Thank you! You're a great fit for our services. 🎉\n\n"
                f"I've matched you with *{rep}* from our team. "
                f"We're checking their calendar right now and will send you a confirmed meeting time shortly.\n\n"
                f"You'll receive an email confirmation soon!"
            )

            slots = get_slots(rep)
            rep_email = REP_EMAILS[rep]
            lead_name = lead.get("sender_name") or sender_id
            slot_lines = "\n".join([f"{i+1}. {s['label']}" for i, s in enumerate(slots)])

            rep_msg = (
                f"Hi {rep},\n\n"
                f"New qualified lead waiting for you!\n\n"
                f"👤 {lead_name}\n"
                f"📧 {sender_id}\n"
                f"🎯 Need: {extracted.get('need')}\n"
                f"💰 Budget: ₹{result['evidence'].get('budget', 'N/A'):,}\n"
                f"⏱ Timeline: {extracted.get('timeline_months')} months\n\n"
                f"Reply with 1, 2, or 3 to confirm their meeting slot:\n\n"
                f"{slot_lines}\n\n"
                f"The lead will be automatically notified once you confirm."
            )
            await send_email_to_rep(rep_email, rep_msg)
            log_action(lead_id, f"rep {rep} notified for slot confirmation")

        else:
            patch["stage"] = "NOT_QUALIFIED"
            log_action(lead_id, "not qualified")
            reply = (
                "Thank you for reaching out! Unfortunately, based on the details shared, "
                "we may not be the best fit right now. Feel free to reach out again if your "
                "requirements change. Have a great day!"
            )

        update_lead(lead_id, patch)
        lead.update(patch)

    save_message(lead_id, "assistant", reply)
    await send_reply(channel, sender_id, reply)
