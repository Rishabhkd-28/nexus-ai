"""
qualify.py — pure Python qualification and routing.
LLM never touches these decisions.
"""
import logging
from supabase import create_client
import os

logger = logging.getLogger(__name__)

SERVICES = ["BI", "Analytics", "AI", "Automation", "CRM"]

REP_ROUTING = {
    "BI":         "Arjun",
    "Analytics":  "Arjun",
    "AI":         "Priya",
    "Automation": "Priya",
    "CRM":        "Priya",
}


def qualify_lead(fields: dict) -> dict:
    budget    = normalise_budget(fields.get("budget"))
    need      = fields.get("need")
    dm        = fields.get("decision_maker")
    timeline  = fields.get("timeline_months")

    reasons = []

    budget_ok   = budget is not None and budget >= 50_000
    dm_ok       = dm is True
    need_ok     = need in SERVICES
    timeline_ok = isinstance(timeline, (int, float)) and timeline <= 3

    if not budget_ok:
        reasons.append(f"budget {budget} < ₹50,000")
    if not dm_ok:
        reasons.append("not a decision maker")
    if not need_ok:
        reasons.append(f"need '{need}' not in service list")
    if not timeline_ok:
        reasons.append(f"timeline {timeline} months > 3")

    qualified = budget_ok and dm_ok and need_ok and timeline_ok

    if qualified:
        logger.info("Lead QUALIFIED")
    else:
        logger.info(f"Lead NOT qualified: {reasons}")

    return {
        "qualified": qualified,
        "evidence": {
            "budget":           budget,
            "decision_maker":   dm,
            "need":             need,
            "timeline_months":  timeline,
            "disqualifiers":    reasons,
        },
    }


def normalise_budget(text) -> object:
    """Convert messy budget strings to integer INR."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)

    s = str(text).lower().strip()

    # Remove currency symbols
    s = s.replace("₹", "").replace("inr", "").replace(",", "").strip()

    try:
        if "lakh" in s or "lac" in s:
            num = float(s.replace("lakh", "").replace("lac", "").strip())
            return int(num * 100_000)
        if "k" in s:
            num = float(s.replace("k", "").strip())
            return int(num * 1_000)
        if "$" in s or "usd" in s:
            num = float(s.replace("$", "").replace("usd", "").strip())
            return int(num * 83)        # rough USD→INR
        return int(float(s))
    except (ValueError, TypeError):
        logger.warning(f"Could not parse budget: {text!r}")
        return None


def route_lead(need: str) -> str:
    """Return rep name. Falls back to whoever has fewer open leads."""
    if need in REP_ROUTING:
        return REP_ROUTING[need]
    return _rep_with_fewer_leads()


def _rep_with_fewer_leads() -> str:
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    arjun_count = (
        supabase.table("leads")
        .select("id", count="exact")
        .eq("assigned_rep", "Arjun")
        .eq("stage", "QUALIFIED")
        .execute()
        .count or 0
    )
    priya_count = (
        supabase.table("leads")
        .select("id", count="exact")
        .eq("assigned_rep", "Priya")
        .eq("stage", "QUALIFIED")
        .execute()
        .count or 0
    )
    return "Arjun" if arjun_count <= priya_count else "Priya"
