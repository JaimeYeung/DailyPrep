import json
import os
import anthropic
from datetime import date, datetime
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

DIVIDER = "━━━━━━━━━━━━━━━━━━━"

TIER_LABELS = {
    "P0": "P0 — MUST ACT TODAY",
    "P1": "P1 — HIGH-CONVERSION / DEAL RISK",
    "P2": "P2 — PIPELINE CREATION",
}

# Claude only writes item descriptions — one per priority item
ITEM_SYSTEM = """
You are a GTM assistant for a sales rep at Hebbia (enterprise AI for institutional finance).

You will receive a list of priority items. For each item write exactly two lines:
Line 1: One sentence of context — why this matters TODAY (reference ARR, days to close, contacts, use cases if relevant).
Line 2: -> One specific action the rep should take right now.

Rules:
- Direct, no-fluff. No markdown, no asterisks.
- Use contact names and roles from the contacts field when available.
- Reference industry or use cases when it adds useful context.
- Each item is separated by its rank number in the input — preserve that order exactly.
- Return only the two lines per item, separated by a blank line between items.
""".strip()

BRIEF_SYSTEM = """
You are a GTM assistant helping a sales rep at Hebbia prepare for a customer call.
Hebbia sells enterprise AI document analysis to institutional finance firms.

Generate a pre-meeting brief with exactly these seven sections in this order:

1. MEETING CONTEXT
   Account, deal stage, attendees with their roles, ARR, days to close, account tier, industry.

2. COMPANY SNAPSHOT
   2-3 bullets from recent_news field. Then one line on current_solution: what the rep is displacing
   and the key displacement angle (what pain does Hebbia solve that the current solution doesn't).

3. LAST CALL SUMMARY
   Summarize gong_summary in your own words — do not copy verbatim.
   If gong_summary is null or empty: "No prior call history — this appears to be a first meeting."

4. OPEN ITEMS YOU OWE THEM
   One line per item from customer_waiting_for, flagged with ⚠️.
   If empty: "No outstanding deliverables on record."

5. SUGGESTED TALK TRACK
   5 steps tailored to this account's industry, deal stage, and current_solution.
   Step 1 should reference delivery of any open items.
   Step 5 should define the exit criteria (specific next step with owner and date).

6. OBJECTION HANDLING
   3 likely objections for this account type and deal stage, each with a one-line response.
   Common objections for institutional finance: data security, integration complexity, ROI justification.
   Format: "Objection: [X] → Response: [Y]"

7. WATCH OUT FOR
   3 bullets max: deal risks, missing stakeholders, timeline pressure.

Every sentence must help the rep walk in more prepared.
Use plain text with ━━━ section dividers. No markdown, no asterisks.
""".strip()


def _brief_time(meeting_time_str: str) -> str:
    t = datetime.strptime(meeting_time_str, "%H:%M")
    brief = t.replace(hour=t.hour - 1) if t.hour > 0 else t
    return brief.strftime("%I:%M %p").lstrip("0")


def _meeting_time_fmt(t: str) -> str:
    return datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")


def _get_item_descriptions(items: list) -> list[str]:
    """Ask Claude to write context + action lines for each item. Returns list of strings."""
    if not items:
        return []

    user_prompt = "\n\n".join(
        f"Item {item['rank']} — [{item['tier']}] {item['account']}\n"
        f"Signals: {', '.join(item['reason_codes'])}\n"
        f"Suggested action: {item['suggested_action']}\n"
        f"Context: {json.dumps(item.get('context', {}))}"
        for item in items
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1200,
        system=ITEM_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}]
    )

    raw = response.content[0].text.strip()
    # Split on blank lines between items — each item is 2 lines
    blocks = [b.strip() for b in raw.split("\n\n") if b.strip()]
    # Strip any leading rank numbers Claude may have added (e.g. "1\nText..." → "Text...")
    cleaned = []
    for block in blocks:
        lines = block.splitlines()
        if lines and lines[0].strip().rstrip(".").isdigit():
            lines = lines[1:]
        cleaned.append("\n".join(lines).strip())
    blocks = cleaned
    # Pad or trim to match item count
    while len(blocks) < len(items):
        blocks.append("→ Follow up on this item today.")
    return blocks[:len(items)]


def generate_daily_email(classified: dict) -> str:
    today = date.today()
    rep_name = classified["rep"].get("name", "Rep")

    p0 = [x for x in classified["priorities"] if x["tier"] == "P0"]
    p1 = [x for x in classified["priorities"] if x["tier"] == "P1"][:4]
    p2 = [x for x in classified["priorities"] if x["tier"] == "P2"][:2]
    p1_total = sum(1 for x in classified["priorities"] if x["tier"] == "P1")
    p2_total = sum(1 for x in classified["priorities"] if x["tier"] == "P2")
    shown = p0 + p1 + p2

    try:
        descriptions = _get_item_descriptions(shown)
    except Exception as e:
        return _fallback_daily(classified, str(e))

    lines = [
        f"Hi {rep_name},",
        "",
        f"Here's your priority list for {today.strftime('%A, %B %d')}.",
        "",
    ]

    # TODAY'S SCHEDULE
    lines.append("TODAY'S SCHEDULE")
    for m in classified.get("meetings_today", []):
        lines.append(f"• {_meeting_time_fmt(m['time'])} — {m['title']}  (brief scheduled for {_brief_time(m['time'])})")
    lines.append("")

    # Priority tiers — use sequential display number, not internal rank
    display_num = 1
    for tier_key, tier_items in [("P0", p0), ("P1", p1), ("P2", p2)]:
        if not tier_items:
            continue
        lines += [DIVIDER, TIER_LABELS[tier_key], DIVIDER, ""]
        for item in tier_items:
            idx = shown.index(item)
            rc_str = " / ".join(item["reason_codes"])
            desc = descriptions[idx]
            lines.append(f"{display_num}. [{item['account']}] {item['suggested_action']}  <- {rc_str}")
            lines.append(f"   {desc}")
            lines.append("")
            display_num += 1

    # Truncation notes
    if p1_total > 4:
        lines.append(f"(+{p1_total - 4} more P1 item{'s' if p1_total - 4 > 1 else ''} not shown.)")
    if p2_total > 2:
        lines.append(f"(+{p2_total - 2} more P2 item{'s' if p2_total - 2 > 1 else ''} not shown.)")
    if p1_total > 3 or p2_total > 2:
        lines.append("")

    # Hygiene
    hygiene = classified.get("hygiene", [])
    if hygiene:
        hygiene_summary = "; ".join(h["action"] for h in hygiene)
        lines.append(f"{len(hygiene)} hygiene task{'s' if len(hygiene) > 1 else ''} omitted. ({hygiene_summary}.)")
        lines.append("")

    if not shown:
        lines.append("No priority items flagged for today. Your pipeline looks healthy.")
        lines.append("")

    lines += ["Good luck today.", "— Hebbia Sales Assistant"]
    return "\n".join(lines)


def generate_brief(meeting: dict, deal: dict) -> str:
    user_prompt = f"""Meeting in ~60 minutes:
{json.dumps(meeting, indent=2)}

Account deal data:
{json.dumps(deal, indent=2)}

Generate the pre-meeting brief."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1800,
            system=BRIEF_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.content[0].text
    except Exception as e:
        return _fallback_brief(meeting, deal, str(e))


def _fallback_daily(classified: dict, error: str) -> str:
    lines = [
        "Note: AI formatting unavailable. Showing structured summary.",
        f"Error: {error}", "",
    ]
    for item in classified["priorities"]:
        lines.append(f"[{item['tier']}] {item['account']}: {item['suggested_action']}")
        lines.append(f"  Signals: {', '.join(item['reason_codes'])}")
        lines.append("")
    if classified["hygiene"]:
        lines.append(f"{len(classified['hygiene'])} hygiene tasks omitted.")
    return "\n".join(lines)


def _fallback_brief(meeting: dict, deal: dict, error: str) -> str:
    lines = [
        "Note: AI formatting unavailable. Showing structured summary.",
        f"Error: {error}", "",
        f"Meeting: {meeting.get('title')} at {meeting.get('time')}",
        f"Account: {meeting.get('account')}",
        f"Deal stage: {deal.get('stage')} | ARR: ${deal.get('arr', 0):,}",
    ]
    if deal.get("customer_waiting_for"):
        lines.append("Open items: " + ", ".join(deal["customer_waiting_for"]))
    return "\n".join(lines)
