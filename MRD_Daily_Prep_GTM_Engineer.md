# MRD: Sales Rep Daily Prep Automation
**Hebbia GTM Engineer Take-Home**

---

## 1. Background & Goal

This is a take-home demo for Hebbia's GTM Engineer role.

**Core design principle: Push, not Pull.**

Reps don't open dashboards. The system embeds itself into workflows they already use — their inbox. Every output is automatically delivered; nothing requires the rep to initiate.

**Two automated push emails:**
1. **Daily Priority Email** — sent every morning at 8:00 AM on weekdays only
2. **Pre-Meeting Brief Email** — sent 60 minutes before any external customer call

---

## 2. System Architecture

### Files to Build

```
project/
├── main.py                  # Entry point; also supports manual trigger flags
├── scheduler.py             # APScheduler: weekday-only, timezone-aware
├── priority_engine.py       # Python rules engine: classifies, deduplicates, and ranks tasks
├── calendar_reader.py       # Google Calendar API: detect external calls
├── claude_generator.py      # Claude API: converts structured recommendations into email copy
├── email_sender.py          # Gmail API: send emails
├── mock_data.py             # Generates mock CRM data with dynamic relative dates
├── sent_briefs.json         # Tracks which meetings already received briefs (avoid duplicates)
├── run.log                  # Basic observability log
├── requirements.txt         # Python dependencies
└── README.md                # Setup instructions
```

### Critical Design Rule: Python Classifies, Claude Writes

**Python's `priority_engine.py` is the single source of truth for tier assignment and ranking.**
Claude does NOT decide what is P0 or P1. Claude only converts the structured output into concise, useful email copy.

This ensures:
- Ranking is deterministic and explainable
- The same data always produces the same priority order
- During presentation, every item can be traced back to a specific rule

Flow:
```
mock_data.py (dynamic CRM data)
  → priority_engine.py (classify + deduplicate + rank deterministically)
      → structured output with tier, reason_codes, rank
  → claude_generator.py (convert structured output to email text)
  → email_sender.py (send via Gmail API)
```

Example output from `priority_engine.py` before Claude sees it:
```json
{
  "tier": "P0",
  "reason_codes": ["CUSTOMER_WAITING", "COMMITMENT_DUE_TODAY", "MEETING_PREP_REQUIRED"],
  "rank": 1,
  "account": "KKR",
  "suggested_action": "Send security whitepaper and revised pricing before 2 PM call"
}
```

Claude's job: take this structured object and write one natural-language paragraph per item.

### Two Scheduled Jobs

**Job 1 — Daily Priority Email**
- Trigger: Every weekday (Mon–Fri) at 8:00 AM, timezone set explicitly to `America/Los_Angeles` in APScheduler config (production reads from rep profile)
- Weekday check: `if datetime.now().weekday() >= 5: skip` — no email on Saturday or Sunday
- Input: `mock_data.py` output (deals, leads, prospect replies, today's meetings)
- Process: `priority_engine.py` classifies → Claude writes email body
- Output: Email sent to rep's Gmail

**Job 2 — Pre-Meeting Brief Email**
- Trigger: Every 15 minutes, check Google Calendar
- Primary window: meeting starts **between 45 and 75 minutes from now** AND brief not yet sent → send brief
- Late brief rule: if a meeting was created with less than 75 minutes notice and brief hasn't been sent, send immediately and log as `LATE_BRIEF`
- Track sent briefs in `sent_briefs.json` to avoid duplicate sends
- Input: Calendar event details + matched account from mock data
- Output: Email sent to rep's Gmail

### Manual Trigger Commands (for live demo)

```bash
python main.py --daily-now                              # Immediately send Daily Priority Email
python main.py --brief --meeting-id meeting_001         # Immediately send Pre-Meeting Brief
python main.py --brief --meeting-id meeting_001 --force # Force re-send even if already sent
```

`--force` flag overrides `sent_briefs.json` check, so the same meeting can be demonstrated multiple times without resetting state manually.

---

## 3. Mock CRM Data

File: `mock_data.py` — all dates generated dynamically relative to `today`. All `customer_waiting_for` fields are lists. Stage names use the canonical enum defined below.

### Account-Level Fields (added to each deal)

| Field | Type | Purpose |
|-------|------|---------|
| `account_tier` | `"Tier 1" / "Tier 2" / "Tier 3"` | Strategic importance of the account — used in within-tier ranking |
| `industry` | string | e.g. `"Private Equity"`, `"Hedge Fund"` — passed to Claude for tailored brief and talk track |
| `current_use_cases` | list of strings | What the account is evaluating Hebbia for — surfaces expansion angles in brief |
| `current_solution` | string | What Hebbia is displacing (e.g. "Bloomberg + manual Excel models") — used to generate displacement angle in brief |
| `recent_news` | list of strings | 2-3 recent signals about the account (funding, hiring, expansion) — used in Company Snapshot section of brief. In production, populated by Tavily real-time search at brief generation time. |
| `contacts` | list of objects | Replaces `contacts_count`. Each contact has `name`, `title`, `role`, `last_engaged_days_ago`. Used for stakeholder map in brief and single-threaded detection. |

**Contact roles used:** `Champion`, `Economic Buyer`, `Procurement`, `Evaluator`, `IT / Security`, `Legal`

**Missing roles:** Not stored as a separate field. In the demo, `critical_stakeholder_missing` + `missing_stakeholder` are explicit flags. In production, missing roles would be derived by comparing `contacts[].role` against required roles for the current deal stage.

### Canonical Stage Enum (used throughout priority_engine.py)

```python
STAGE_ORDER = {
    "Discovery": 1,
    "Demo": 2,
    "Technical Evaluation": 3,
    "Pricing & Negotiation": 4
}

# Use numeric comparison, never string matching
# is_late_stage = STAGE_ORDER.get(stage, 0) >= STAGE_ORDER["Technical Evaluation"]
```

All stage values in mock data must exactly match keys in `STAGE_ORDER`. No aliases, no abbreviations.

### Task Deduplication in priority_engine.py

A single account may trigger multiple signals (e.g. KKR satisfies `customer_waiting`, `commitment_due_today`, and `meeting_prep_required` simultaneously). The engine must merge these into one task per account per action type using a dedup key:

```python
dedup_key = f"{account}_{action_type}"  # e.g. "KKR_send_deliverables"
```

#### `action_type` Canonical Values

`action_type` is derived from the primary action the rep must take, not from the signal itself. This ensures signals that require the same physical action are merged, not split.

```python
ACTION_TYPE_MAP = {
    "customer_waiting":           "send_deliverables",
    "commitment_due_today":       "send_deliverables",   # same action → merges with above
    "meeting_prep_required":      "send_deliverables",   # if same account/deliverable
    "prospect_reply":             "respond_to_reply",
    "inbound_lead":               "respond_to_inbound",
    "missing_stakeholder":        "loop_in_stakeholder",
    "weak_next_step":             "update_next_step",
    "missing_next_step":          "update_next_step",
    "stalled_deal":               "re_engage",
}
# If two signals map to the same action_type for the same account → merge.
# If they map to different action_types → two separate items (both appear in email).
```

Merge rule: keep the highest tier, accumulate all `reason_codes`:

```python
{
  "account": "KKR",
  "tier": "P0",
  "reason_codes": ["CUSTOMER_WAITING", "COMMITMENT_DUE_TODAY", "MEETING_PREP_REQUIRED"],
  "rank": 1,
  "suggested_action": "Send security whitepaper and revised pricing before 2 PM call"
}
```

Never output two separate P0 items for the same account and same underlying action.

#### Cross-Tier Reason Code Accumulation

When an account triggers signals at multiple tiers, the item is assigned the **highest tier**, and reason_codes from **all tiers** are accumulated. Lower-tier reason codes are not dropped.

Example: Blackstone is P0 (`customer_waiting`) AND P1 (`contacts_count == 1` at Technical Evaluation → SINGLE-THREADED RISK). The final item is P0, but both reason codes appear:

```python
{
  "account": "Blackstone",
  "tier": "P0",
  "reason_codes": ["CUSTOMER_WAITING", "SINGLE_THREADED_RISK"],
  "rank": 2,
  "suggested_action": "Send security documentation today. Note: single-threaded — consider multi-threading."
}
```

#### `customer_waiting_for` Null Guard

If `customer_waiting: True` but `customer_waiting_for: []` (empty list), the engine must not generate a broken suggested_action. Fallback:

```python
if deal["customer_waiting"] and not deal["customer_waiting_for"]:
    deal["customer_waiting_for"] = ["(pending — check CRM for details)"]
```

#### Multiple Deals per Account

In production, an account may have multiple deals (e.g., two KKR deals at different stages). For the demo, mock data has one deal per account. In production, the engine runs per-deal, not per-account — each deal generates its own signals. If two deals for the same account trigger the same action_type, the higher-ARR deal's context wins for suggested_action, but both deals' reason_codes accumulate.

### Mock Data

```python
from datetime import date, timedelta

today = date.today()

data = {
  "rep": {
    "name": "Sarah Chen",
    "email": "YOUR_GMAIL_HERE",
    "domain": "hebbia.ai",
    "timezone": "America/Los_Angeles"
  },
  "deals": [
    {
      "id": "deal_001",
      "account": "Blackstone",
      "stage": "Technical Evaluation",
      "arr": 180000,
      "close_date": str(today + timedelta(days=38)),
      "last_activity_days_ago": 12,
      "next_step": None,
      "next_step_quality": "missing",
      "contacts_count": 1,
      "customer_waiting": True,
      "customer_waiting_for": ["Security documentation"],
      "commitment_due_today": False,
      "critical_stakeholder_missing": False,
      "notes": "Champion is VP of Research. Single-threaded at Evaluation stage — multi-threading risk. No economic buyer identified."
    },
    {
      "id": "deal_002",
      "account": "KKR",
      "stage": "Pricing & Negotiation",
      "arr": 240000,
      "close_date": str(today + timedelta(days=10)),
      "last_activity_days_ago": 3,
      "next_step": {
        "action": "Send revised pricing proposal",
        "owner": "rep",
        "due": str(today)
      },
      "next_step_quality": "strong",
      "contacts_count": 3,
      "customer_waiting": True,
      "customer_waiting_for": ["Security whitepaper", "Revised pricing proposal"],
      "commitment_due_today": True,
      "critical_stakeholder_missing": False,
      "notes": "Strong engagement. Legal review started. Procurement loop in. Customer actively waiting on two deliverables committed last call."
    },
    {
      "id": "deal_003",
      "account": "Citadel",
      "stage": "Discovery",
      "arr": 95000,
      "close_date": str(today + timedelta(days=75)),
      "last_activity_days_ago": 18,
      "next_step": "follow up sometime",
      "next_step_quality": "weak",
      "contacts_count": 1,
      "customer_waiting": False,
      "customer_waiting_for": [],
      "commitment_due_today": False,
      "critical_stakeholder_missing": False,
      "notes": "Met once. Champion went quiet. Single contact but still early Discovery — monitor, not urgent."
    },
    {
      "id": "deal_004",
      "account": "Apollo Global",
      "stage": "Demo",
      "arr": 120000,
      "close_date": str(today + timedelta(days=52)),
      "last_activity_days_ago": 5,
      "next_step": {
        "action": "Confirm pilot scope",
        "owner": "rep",
        "due": str(today + timedelta(days=2))
      },
      "next_step_quality": "strong",
      "contacts_count": 2,
      "customer_waiting": False,
      "customer_waiting_for": [],
      "commitment_due_today": False,
      "critical_stakeholder_missing": True,
      "missing_stakeholder": "IT / Security",
      "pilot_blocked": True,
      "notes": "Second demo requested. Positive signals. IT/Security stakeholder not looped in — will block pilot sign-off."
    }
  ],
  "meetings_today": [
    {
      "id": "meeting_001",
      "account": "KKR",
      "title": "KKR Pricing Review",
      "time": "14:00",
      "duration_minutes": 60,
      "attendees": [
        "sarah.chen@hebbia.ai",
        "john.smith@kkr.com",
        "mary.wong@kkr.com"
      ],
      "type": "Pricing & Negotiation",
      "has_pending_deliverables": True,
      "gong_summary": "Last call: Discussed pilot scope. Customer raised data security concerns. Requested security whitepaper and revised pricing. Rep committed to delivering both by end of week.",
      "deal_id": "deal_002"
    }
  ],
  "inbound_leads": [
    {
      "id": "lead_001",
      "account": "Bridgewater Associates",
      "contact": "James Park, Director of Research",
      "source": "Inbound form fill",
      "inbound_type": "demo_request",
      "received_hours_ago": 3,
      "icp_fit": "high",
      "notes": "Filled out enterprise contact form. Mentioned AI-powered document analysis. Requested a demo."
    },
    {
      "id": "lead_002",
      "account": "Point72",
      "contact": "Unknown",
      "source": "Webinar attendee",
      "inbound_type": "content_download",
      "received_hours_ago": 18,
      "icp_fit": "medium",
      "notes": "Attended AI in finance webinar. Downloaded whitepaper."
    }
  ],
  "prospect_replies": [
    {
      "id": "reply_001",
      "account": "Two Sigma",
      "contact": "Lisa Chen, Head of Technology",
      "replied_minutes_ago": 45,
      "original_outreach": "Cold email about AI document analysis for quant research",
      "reply_summary": "Interested, asked for more info on data security and pricing. Available next week for a call.",
      "icp_fit": "high"
    }
  ],
  "hygiene_tasks": [
    {
      "id": "hygiene_001",
      "account": "Apollo Global",
      "action": "Update Salesforce opportunity stage from Demo to Technical Evaluation",
      "tier": "P3"
    },
    {
      "id": "hygiene_002",
      "account": "KKR",
      "action": "Log call notes after 2 PM meeting",
      "tier": "P3"
    }
  ]
}
```

---

## 4. Priority Framework

### Core Principle
> Every recommended priority must either **protect revenue**, **advance revenue**, or **create qualified pipeline**.

### Tier Definitions (fixed — `priority_engine.py` enforces these rules exactly)

| Tier | Label | What Goes Here |
|------|-------|----------------|
| P0 | Must Act Today | Customer waiting on us, commitment due today, meeting today WITH `has_pending_deliverables: true` |
| P1 | High-Conversion / Deal Risk | Prospect actively replied, close date within 14 days, missing/weak next step at Technical Evaluation or later, critical stakeholder missing with `pilot_blocked: true`, high-intent inbound (`demo_request`), **overdue close date** |
| P2 | Pipeline Creation | General inbound (`content_download`, webinar), weak/missing next step in Discovery stage, early-stage stalled deals |
| P3 | Hygiene | CRM updates, call notes, forecast admin — omitted from email body, count shown only |

**Meeting rule:** A meeting today does NOT automatically create a P0 task. It appears in TODAY'S SCHEDULE. It only generates a P0 action item if `has_pending_deliverables: true`.

**Overdue close date rule:** If `close_date < today`, the deal is automatically P1 with reason_code `OVERDUE_CLOSE_DATE`, regardless of other signals (unless it's already P0 for another reason). This surfaces slipped deals that may have fallen out of active attention.

```python
if close_date < today:
    tier = max(existing_tier, "P1")  # escalate to P1, never downgrade a P0
    reason_codes.append("OVERDUE_CLOSE_DATE")
```

### Email Display Limits

```
P0  — show all (no cap)
P1  — show top 4 maximum
P2  — show top 2 maximum
P3  — omit from body; show count: "2 hygiene tasks omitted. (Update Apollo stage; log KKR call notes.)"
```

**Truncation line:** If P1 or P2 items are cut by the cap, append a count line immediately after that tier's section:
```
(+2 more P1 items not shown. Full list available on request.)
```

**Zero-item case:** If all tiers produce zero items (no signals from any data source), still send the email with the following body instead of skipping silently:
```
Hi [Name],

No priority items flagged for today. Your pipeline looks healthy or there's no new activity to action.

— Hebbia Sales Assistant
```
Silent skips make it impossible to distinguish "system ran and found nothing" from "system didn't run." Always send.

### Within-Tier Ranking (enforced by `priority_engine.py`)

```
Hard Deadline → Customer Waiting → Response Freshness → Deal Stage → Account Tier → Deal ARR → Staleness
```

**Account Tier vs ARR distinction:** ARR measures the value of this specific deal. Account Tier measures the strategic importance of the client. A Tier 1 account (e.g. Blackstone) with a $180K deal ranks above a Tier 2 account with a $200K deal within the same priority tier — because expansion potential, brand value, and strategic fit outweigh the current deal size.

```python
ACCOUNT_TIER_RANK = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2}
# Lower number = higher priority, same direction as TIER_RANK
```

### Enterprise Sales Signals (particularly relevant to Hebbia's motion)

| Signal | Field | Tier Rule |
|--------|-------|-----------|
| Customer blocked on us | `customer_waiting: true` | P0 |
| Commitment due today | `commitment_due_today: true` | P0 |
| Meeting with open deliverables | `has_pending_deliverables: true` | P0 action item (merged with deal signals if same account) |
| Single-threaded at late stage | `len(contacts) == 1` AND `STAGE_ORDER[stage] >= 3` | P1, flag as SINGLE-THREADED RISK |
| Missing next step — late stage | `next_step_quality: "missing"` AND `STAGE_ORDER[stage] >= 3` | P1 |
| Weak next step — late stage | `next_step_quality: "weak"` AND `STAGE_ORDER[stage] >= 3` | P1, flag as NOT ACTIONABLE |
| Missing/weak next step — Discovery | `next_step_quality in ["missing","weak"]` AND `STAGE_ORDER[stage] == 1` | P2 |
| Pilot blocked by missing stakeholder | `critical_stakeholder_missing: true` AND `pilot_blocked: true` | P1 |
| High-intent inbound | `inbound_type: "demo_request"` | P1 |
| General inbound | `inbound_type: "content_download"` | P2 |
| Prospect reply | `replied_minutes_ago` present | P1, ranked by freshness |

### next_step_quality Definition

```
"strong"   = has specific action + owner + due date  →  executable
"weak"     = vague description only, e.g. "follow up sometime"  →  not actionable
"missing"  = no next step at all  →  deal is drifting
```

Demo talking point: "Apollo and Citadel both have a next step field. Only Apollo's is executable. And Citadel is in Discovery — weak next step there is P2, not urgent. Apollo at Demo stage with a blocked pilot is P1. The rules, not Claude's judgment, make that call."

---

## 5. Email Output Formats

### Email 1: Daily Priority Email

**Subject:** `Your Sales Priorities for [Weekday, Date]`

```
Hi Sarah,

Here's your priority list for today.

TODAY'S SCHEDULE
• 2:00 PM — KKR Pricing Review  (brief scheduled for 1:00 PM)

━━━━━━━━━━━━━━━━━━━
P0 — MUST ACT TODAY
━━━━━━━━━━━━━━━━━━━

1. [KKR] Send security whitepaper + revised pricing  ← CUSTOMER WAITING / COMMITMENT DUE TODAY / MEETING PREP REQUIRED
   Customer is actively waiting on both deliverables you committed last call.
   $240K deal closes in 10 days. 2 PM call is today.
   → Deliver both now before the meeting.

2. [Blackstone] Send security documentation  ← CUSTOMER WAITING
   Customer is blocked on us. 12 days since last activity. Single contact at
   Evaluation stage — high risk if this stalls further.
   → Send security whitepaper today.

━━━━━━━━━━━━━━━━━━━
P1 — HIGH-CONVERSION / DEAL RISK
━━━━━━━━━━━━━━━━━━━

3. [Two Sigma] Respond to Lisa Chen's reply  ← 45 MIN AGO
   Head of Technology replied to your cold outreach. Interested, asked about
   security and pricing. High ICP fit.
   → Reply now while momentum is fresh.

4. [Bridgewater] New demo request — James Park, Director of Research
   Filled out enterprise contact form 3 hours ago. High ICP fit.
   Mentioned AI document analysis specifically.
   → Schedule intro call today.

5. [Apollo Global] Loop in IT/Security stakeholder  ← PILOT BLOCKED
   Strong next step confirmed. But IT/Security not involved —
   pilot sign-off will be blocked without them.
   → Identify and add IT contact this week.

━━━━━━━━━━━━━━━━━━━
P2 — PIPELINE CREATION
━━━━━━━━━━━━━━━━━━━

6. [Citadel] Re-engage — 18 days dark, next step vague
   Still early Discovery, not critical yet. Champion went quiet.
   → Try a new angle or contact before this goes cold.

7. [Point72] Webinar lead — low urgency
   Downloaded whitepaper 18 hours ago. Medium ICP fit.
   → Add to nurture sequence if not already enrolled.

2 hygiene tasks omitted. (Update Apollo Salesforce stage; log KKR call notes after meeting.)

Good luck today.
— Hebbia Sales Assistant
```

---

### Email 2: Pre-Meeting Brief

**Subject:** `Pre-Meeting Brief: KKR Pricing Review — 2:00 PM Today`

```
Hi Sarah,

Your KKR Pricing Review starts in 60 minutes.

━━━━━━━━━━━━━━━━━━━
MEETING CONTEXT
━━━━━━━━━━━━━━━━━━━
Account: KKR
Type: Pricing & Negotiation
Time: 2:00 PM today
Attendees: John Smith, Mary Wong (KKR)
Deal: $240,000 ARR | Stage: Pricing & Negotiation | Closes in 10 days

━━━━━━━━━━━━━━━━━━━
LAST CALL SUMMARY
━━━━━━━━━━━━━━━━━━━
Discussed pilot scope. Customer raised data security concerns.
Requested security whitepaper and revised pricing. Rep committed to
delivering both by end of week.

━━━━━━━━━━━━━━━━━━━
COMPANY SNAPSHOT
━━━━━━━━━━━━━━━━━━━
KKR closed $20B North America PE Fund XII in March 2026 and is actively hiring
quantitative analysts and data scientists across portfolio companies.

Currently displacing: Bloomberg terminal + manual document review + Confluence.
Displacement angle: Hebbia automates portfolio company research, deal sourcing,
and LP reporting — freeing analysts from manual extraction.

━━━━━━━━━━━━━━━━━━━
OPEN ITEMS YOU OWE THEM
━━━━━━━━━━━━━━━━━━━
⚠️  Security whitepaper — promised last call, due today
⚠️  Revised pricing proposal — promised last call, due today

━━━━━━━━━━━━━━━━━━━
SUGGESTED TALK TRACK
━━━━━━━━━━━━━━━━━━━
1. Open: Confirm delivery of both documents, set agenda
2. Security deep dive: walk through whitepaper, address data residency and compliance
3. Commercial alignment: present pricing, anchor ROI on analyst time saved per deal
4. Procurement and legal path: confirm Mary's checklist, set legal review timeline
5. Exit with: signed pilot agreement or named next step with owner and date

━━━━━━━━━━━━━━━━━━━
OBJECTION HANDLING
━━━━━━━━━━━━━━━━━━━
Objection: "Pricing is above our threshold." → Start with one fund pilot, expand on ROI proof.
Objection: "Data security — we hold sensitive LP and portfolio data." → SOC 2 Type II + private cloud option + DPA.
Objection: "Bloomberg + Confluence integration will be complex." → Average PE firm goes live in 4-6 weeks; dedicated implementation manager assigned.

━━━━━━━━━━━━━━━━━━━
WATCH OUT FOR
━━━━━━━━━━━━━━━━━━━
- No legal stakeholder looped in yet — procurement is in but legal is not
- Close date in 10 days — need signed agreement fast
- Know your pricing floor before you walk in

Good luck.
— Hebbia Sales Assistant
```

---

## 6. Claude API Prompt Design

### Important: Claude receives pre-classified structured data, not raw CRM data

Claude does not apply the priority framework. It receives a structured list already classified, deduplicated, and ranked by `priority_engine.py`.

### Daily Priority Prompt

```python
system_prompt = """
You are a GTM assistant helping a sales rep at Hebbia (enterprise AI for institutional finance).

You will receive:
- Today's meeting schedule (for the schedule section only)
- A pre-classified, pre-ranked, deduplicated priority list (tiers and order are final)

Each priority item has: tier, reason_codes, suggested_action, and context fields.

Your job: write one paragraph per item in the email.
Format per item:
  [Account] What to do  ← REASON CODE(S)
  One sentence of context: why this matters today.
  → Specific action line.

Rules:
- Do not reorder. Do not reclassify. The list is final.
- Show reason codes inline in caps: CUSTOMER WAITING, COMMITMENT DUE TODAY, PILOT BLOCKED, SINGLE-THREADED RISK, MEETING PREP REQUIRED
- Write in direct, no-fluff style. No markdown, no asterisks.
- Use plain text section dividers (━━━).
- TODAY'S SCHEDULE at the top: list meetings with time and "Brief scheduled for HH:MM" (not "60 min before").
- At the end: "X hygiene tasks omitted." with one-line summary of what they are.
"""

user_prompt = f"""
Today is {today}. Rep name: {rep_name}.

Today's meetings (schedule section only):
{json.dumps(meetings_today, indent=2)}

Pre-classified priority list (do not reorder or reclassify):
{json.dumps(ranked_priorities, indent=2)}

Hygiene tasks (for count + summary line only):
{json.dumps(hygiene_tasks, indent=2)}

Generate the daily priority email.
"""
```

### Pre-Meeting Brief Prompt

```python
system_prompt = """
You are a GTM assistant helping a sales rep at Hebbia prepare for a customer call.
Hebbia sells enterprise AI document analysis to institutional finance firms.

Generate a pre-meeting brief with exactly these seven sections:

1. MEETING CONTEXT — account, deal stage, attendees with roles, ARR, days to close, account tier, industry
2. COMPANY SNAPSHOT — 2-3 bullets from recent_news; current_solution being displaced and the displacement angle
3. LAST CALL SUMMARY — summarize gong_summary in your own words; if null: "No prior call history — this appears to be a first meeting."
4. OPEN ITEMS YOU OWE THEM — ⚠️ one line per item from customer_waiting_for; if empty: "No outstanding deliverables on record."
5. SUGGESTED TALK TRACK — 5 steps tailored to this account's industry, deal stage, and current_solution; step 1 = deliver open items; step 5 = exit criteria with named owner and date
6. OBJECTION HANDLING — 3 likely objections for this account type and stage, each with a one-line response. Format: "Objection: [X] → Response: [Y]"
7. WATCH OUT FOR — 3 bullets max: deal risks, missing stakeholders, timeline pressure

Every sentence must help the rep walk in more prepared.
Use plain text with ━━━ section dividers. No markdown, no asterisks.
"""

user_prompt = f"""
Meeting in ~60 minutes:
{json.dumps(meeting_data, indent=2)}

Account deal data:
{json.dumps(deal_data, indent=2)}

Generate the pre-meeting brief.
"""
```

### Claude API Failure Handling

If the Claude API call fails:
1. Log the error to `run.log`
2. Fall back to a rule-based plain-text email built directly from the structured `priority_engine.py` output
3. Never send a blank email or silently skip the job
4. Include a footer: "Note: AI formatting unavailable. Showing structured summary."

---

## 7. External Call Detection Logic

### Primary Logic

```python
EXCLUDED_DOMAINS = [
    "zoom.us", "meet.google.com", "calendly.com",
    "gong.io", "chorus.ai"  # recording bots
]

EXCLUDED_TITLE_KEYWORDS = [
    "interview", "recruiting", "candidate",
    "investor", "board", "internal", "1:1"
]

def is_external_call(event, rep_domain):
    title = event.get("summary", "").lower()
    if any(kw in title for kw in EXCLUDED_TITLE_KEYWORDS):
        return False

    attendees = event.get("attendees", [])
    if not attendees:
        return False  # solo block

    for attendee in attendees:
        email = attendee.get("email", "")
        domain = email.split("@")[-1] if "@" in email else ""
        if (domain
            and not email.endswith(f"@{rep_domain}")
            and domain not in EXCLUDED_DOMAINS):
            return True
    return False
```

### Calendar-to-CRM Matching

Matching strategy (in order):
1. Explicit `deal_id` in mock `meetings_today` — used for demo
2. Attendee email domain → match against known account domains in mock data
3. If no match → skip brief, log as unmatched

Presentation talking point: "In production, this uses CRM contact email matching with a confidence score. Low-confidence matches are flagged for rep review rather than auto-sent."

### Brief Deduplication Key

```python
# event_id + start_time handles rescheduled meetings correctly
dedup_key = f"{event_id}_{start_time_iso}"
```

### Edge Cases

| Edge Case | Handling |
|-----------|----------|
| No attendees | Skip — internal block |
| All-day event | Skip |
| Rep declined the invite | Skip |
| Recording bot in attendee list | Exclude known bot domains |
| Title contains "interview" / "recruiting" | Skip |
| No matching account in CRM | Log as unmatched, skip brief |
| Brief already sent for this meeting instance | Check dedup key, skip |
| `--force` flag | Override dedup check, re-send |
| Meeting created with <75 min notice | Send immediately, log as LATE_BRIEF |
| Meeting cancelled after brief was sent | No cancellation email in v1 (acceptable for demo). Production: listen for Google Calendar cancellation event and send a one-line "FYI: [Meeting] has been cancelled." follow-up. Log as CANCELLED_AFTER_BRIEF. |
| Two meetings for the same account on the same day | Each meeting gets its own brief (separate dedup keys). Both appear in TODAY'S SCHEDULE in the daily email. The P0 item in the daily email is generated once per account per action_type — a second meeting does not create a duplicate P0. |
| `gong_summary` is null or empty | Claude prompt handles via explicit instruction: write "No prior call history — this appears to be a first meeting." |
| `customer_waiting_for` is empty but `customer_waiting: True` | priority_engine fallback inserts `["(pending — check CRM for details)"]` before passing to Claude. |
| Personal Gmail or consumer domain in attendee list | Consumer domains (gmail.com, yahoo.com, hotmail.com, outlook.com) are treated as external but flagged as LOW_CONFIDENCE_MATCH in log. Brief is still sent; matching is best-effort. |

---

## 8. Observability & Logging

Log all of the following to `run.log`:

```
[2026-06-05 08:00:01] INFO  Daily priority job started (weekday check passed)
[2026-06-05 08:00:03] INFO  priority_engine: 9 raw signals → after dedup: 2 P0, 3 P1, 2 P2, 2 P3
[2026-06-05 08:00:03] INFO  email cap applied: showing 2 P0, 3 P1, 2 P2; P3 omitted (count: 2)
[2026-06-05 08:00:05] INFO  Claude API: daily email generated (823 tokens)
[2026-06-05 08:00:06] INFO  Email sent to sarah.chen@gmail.com
[2026-06-05 08:00:06] INFO  Daily priority job completed

[2026-06-05 13:00:01] INFO  Calendar check: scanning 45–75 min window
[2026-06-05 13:00:01] INFO  Found: KKR Pricing Review at 14:00 (58 min away)
[2026-06-05 13:00:01] INFO  Account matched: KKR (deal_002) via attendee domain kkr.com
[2026-06-05 13:00:03] INFO  Claude API: pre-meeting brief generated (641 tokens)
[2026-06-05 13:00:04] INFO  Brief sent to sarah.chen@gmail.com
[2026-06-05 13:00:04] INFO  Dedup key meeting_001_2026-06-05T14:00:00 saved to sent_briefs.json

[2026-06-05 13:15:01] INFO  Calendar check: meeting_001 already briefed (dedup key match), skipping
```

---

## 9. Tech Stack

| Component | Tool | Why |
|-----------|------|-----|
| Scheduling | APScheduler (Python), weekday-only, timezone-aware | No external dependencies, sufficient for local demo |
| Priority classification | Python rules engine (`priority_engine.py`) | Deterministic, deduplicated, explainable, testable |
| Calendar | Google Calendar API | Detect external calls, get attendees |
| Email | Gmail SMTP + App Password (`smtplib`) | Zero OAuth setup, no credentials.json, reliable for demo; swap to Gmail API or SendGrid in production |
| AI generation | Claude API (`claude-sonnet-4-5`) | Converts structured data into email copy |
| CRM data | `mock_data.py` (dynamic dates, canonical stage enum) | Simulates Salesforce/HubSpot |
| State tracking | `sent_briefs.json` (dedup key: event_id + start_time) | Avoid duplicate pre-meeting emails |
| Logging | `run.log` | Basic observability |

**Note on production path:** APScheduler works for a local prototype but stops when the laptop sleeps or the process exits. True production requires the process to live somewhere persistent — a cloud server, a managed job runner, or a Zapier workflow (already in Hebbia's stack). See Section 10 for the migration path.

---

## 10. Rollout Plan

### Phase 1 — Internal Demo (Week 1)
- Single rep, mock data
- Manual trigger commands (`--daily-now`, `--brief --force`) for presentation
- Gmail SMTP for email delivery (app password, no OAuth)
- Validate email quality and ranking logic

### Phase 2 — Pilot with 1-2 Real Reps (Weeks 2-3)
- **Scheduling migration:** Move off laptop APScheduler → deploy app to Railway or Render (always-on free tier). Use Zapier "Schedule" trigger (already in Hebbia stack) to call a webhook endpoint on the deployed app at 8 AM weekdays and every 15 minutes for brief checks. Rep's laptop no longer needs to be open. This is the point where "push not pull" becomes real: nothing runs on anyone's machine.
- **Google Calendar API:** Replace mock `meetings_today` with live calendar data. Setup requires: (1) create a Google Cloud project, (2) enable Calendar API, (3) generate OAuth 2.0 credentials, (4) each rep completes a one-time browser auth flow to grant read access — token is cached after that. For multi-rep, use a service account with domain-wide delegation so each rep doesn't need to re-auth individually. Read-only scope (`calendar.readonly`) is sufficient.
- **Salesforce API:** Replace `mock_data.py` with live Salesforce REST API calls (read-only). Requires Salesforce Connected App setup and OAuth token per rep. Pull deals, contacts, and activity log on each job run.
- Replace Gmail SMTP with Gmail API or SendGrid for better deliverability tracking (open rates, bounce handling)
- Collect rep feedback: usefulness rating + ranking agreement

### Phase 3 — Iterate on Priority Logic + AI Coach (Week 4+)
- Tune staleness thresholds and tier rules based on pilot feedback
- Add Gong API for real call summaries (replace mock `gong_summary` field)
- Add Slack as alternative delivery channel (Hebbia already uses Slack; use Zapier Slack action)
- Add per-item rep feedback signal ("was this useful?") via reply parsing or emoji reaction
- Prune `sent_briefs.json` → migrate to a lightweight database (SQLite or Supabase) for durability
- **AI Coach (post-call coaching email):** After each external customer call ends, automatically pull the Gong transcript and send the rep a private coaching email within 30 minutes. Delivered separately from the daily email — same push model, different trigger (call end, not schedule).

  **Why it fits:** Sales coaching today requires a manager to manually review recordings, which is time-consuming and creates interpersonal pressure. AI coaching is objective, private, and scales to every call without manager bandwidth. Particularly valuable for junior reps who don't get frequent 1:1 feedback.

  **What the coaching email covers:**
  - Talk ratio (rep vs. customer — flag if rep talked >60%)
  - Discovery quality: did the rep ask open-ended questions or pitch too early?
  - Open items committed on the call — cross-referenced against CRM to flag if not logged
  - One specific suggestion for the next call with this account

  **Data source:** Gong API (transcript + call metadata, already in Hebbia's stack). Trigger: Gong webhook fires on call completion → app generates coaching email → sends to rep only (not manager).

  **Privacy design:** Coaching emails go only to the rep. No manager CC. This is intentional — reps are more likely to act on feedback they receive privately. Manager visibility can be added later as an opt-in.

### Phase 4 — Team Rollout
- Multi-rep support: per-rep config (timezone, email, Salesforce owner filter)
- Manager view: aggregate trends across reps (e.g., "3 reps consistently single-threaded at late stage") — not individual call grades
- A/B test email vs. Slack delivery
- Move scheduling entirely to Zapier or Cloud Scheduler — no self-managed server needed

---

## 11. How to Measure Success

Establish baseline during pilot before setting hard targets.

| Metric | What it measures | How to collect |
|--------|-----------------|----------------|
| Email usefulness | Did reps find it helpful? | 1–5 rating per email (reply or quick survey) |
| Ranking precision | Did top items belong in their tier? | Weekly check-in: "Did your P0s feel right?" |
| P0 action completion | Were urgent items actioned same day? | Rep self-report or CRM activity log |
| Time saved on prep | Is brief reducing pre-call prep time? | Self-reported before/after |
| Brief match accuracy | Did system match the right account? | Log confirmed vs. unmatched |
| False positives | Did irrelevant items appear as P0? | Rep flags via reply |

After 2-week pilot: define specific targets based on observed baseline.

---

## 12. Risks & Blockers

| Risk | Mitigation |
|------|-----------|
| CRM data stale or inaccurate | System is only as good as input data; flag low-confidence inputs in log |
| Calendar matching fails for ambiguous titles | Multi-layer matching + dedup key; skip rather than guess wrong |
| Claude API latency or failure | Fallback to rule-based plain-text email; log and continue |
| Rep ignores email | Test Slack delivery; specific subject line helps open rate |
| Ranking feels wrong to rep | Reason codes visible; feedback mechanism in Phase 3 |
| APScheduler stops when laptop sleeps | Acceptable for demo; production moves to Zapier or Cloud Scheduler |
| Duplicate briefs | Dedup key (event_id + start_time) in `sent_briefs.json` |
| Rescheduled meeting missed | New start_time = new dedup key = new brief sent |
| Last-minute meeting missed | Late brief rule: send immediately if meeting within 75 min and not yet briefed |
| US federal holidays (non-weekend) | v1 sends email on holidays — acceptable for demo. Production: add `holidays` library check before weekday email job fires. |
| `sent_briefs.json` grows unbounded | No cleanup in v1. Production: prune entries older than 30 days on each write. |
| Two concurrent script instances | Risk of double-send if two processes run simultaneously. Mitigation: use a file lock (fcntl) around the send step, or enforce single-instance via PID file. Acceptable for demo; production uses a proper job runner. |
| Cross-tier reason_code loss | Signals at lower tiers may be dropped if only same-tier merging is applied. Fix: priority_engine accumulates reason_codes from all tiers into the highest-tier item for that account+action_type. |

---

## 13. Demo Script (for Presentation)

**Four things to show:**

1. **Modify mock data live** — flip one field (e.g. `customer_waiting` false → true), re-run, show ranking change and merged reason codes
2. **Trigger daily email** — `python main.py --daily-now` → show email in inbox, walk through P0/P1/P2 and hygiene count line
3. **Trigger pre-meeting brief** — `python main.py --brief --meeting-id meeting_001 --force` → show brief in inbox
4. **Explain production path** — "Swap `mock_data.py` for Salesforce API. Swap `sent_briefs.json` for a database. Move scheduler to Zapier. Priority logic and Claude prompts stay the same."

**Key talking points:**

- "Push not pull — reps don't open dashboards. This arrives in their inbox."
- "Python classifies and ranks. Claude only writes. Every P0 item traces to a specific rule."
- "KKR triggered four separate signals — customer waiting, commitment due today, close date imminent, and meeting prep required. The engine merges them into one item with all four reason codes. No duplicate P0s."
- "Citadel is P2, Apollo is P1. Same weak-next-step signal, different stage — the rules make that distinction, not Claude's judgment."
- "Blackstone's deal is $180K, smaller than some P1 accounts. But it's a Tier 1 strategic account — the system ranks by strategic importance, not just deal size."
- "The mock data includes real stakeholder names and roles. The brief knows John Smith is the Economic Buyer and James Lee is the Champion — that's the level of context a rep actually needs walking into a call."
- "For the prototype, I normalized data from Salesforce, Gong, and Calendar into a simplified internal schema. In production, this pulls from Salesforce's Account, Opportunity, Contact Role, and Activity objects directly."
- "In production: Salesforce for data, Gong API for call summaries, Zapier for scheduling, Slack as alternate channel."

---

## 14. Out of Scope for Demo

- Real Salesforce / HubSpot connection (use mock data)
- Multi-rep support
- Mobile push notifications
- Rep feedback loop / ranking adjustment
- Gong API (use mock `gong_summary` field)
- Frontend UI (email is the interface)
