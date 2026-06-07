from datetime import date, timedelta

today = date.today()

STAGE_ORDER = {
    "Discovery": 1,
    "Demo": 2,
    "Technical Evaluation": 3,
    "Pricing & Negotiation": 4
}

# Maps signal type to the action the rep must take.
# Signals with the same action_type for the same account are merged into one item.
ACTION_TYPE_MAP = {
    "customer_waiting":      "send_deliverables",
    "commitment_due_today":  "send_deliverables",
    "meeting_prep_required": "send_deliverables",
    "prospect_reply":        "respond_to_reply",
    "inbound_lead":          "respond_to_inbound",
    "missing_stakeholder":   "loop_in_stakeholder",
    "weak_next_step":        "update_next_step",
    "missing_next_step":     "update_next_step",
    "stalled_deal":          "re_engage",
    "overdue_close_date":    "review_deal",
}

TIER_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

ACCOUNT_TIER_RANK = {"Tier 1": 0, "Tier 2": 1, "Tier 3": 2}


def _merge(items: dict, account: str, action_type: str, tier: str,
           reason_codes: list, suggested_action: str, context: dict):
    key = f"{account}_{action_type}"
    if key not in items:
        items[key] = {
            "account": account,
            "action_type": action_type,
            "tier": tier,
            "reason_codes": list(reason_codes),
            "suggested_action": suggested_action,
            "context": dict(context),
        }
    else:
        existing = items[key]
        # Keep highest tier (lowest TIER_RANK number)
        if TIER_RANK[tier] < TIER_RANK[existing["tier"]]:
            existing["tier"] = tier
            existing["suggested_action"] = suggested_action
        # Always accumulate all reason codes
        for rc in reason_codes:
            if rc not in existing["reason_codes"]:
                existing["reason_codes"].append(rc)
        # Merge context fields
        existing["context"].update(context)


def classify(data: dict) -> dict:
    """
    Returns {"priorities": [...], "hygiene": [...], "meetings_today": [...]}
    priorities are sorted and ranked; hygiene is passed through as-is.
    """
    items = {}  # key: "account_action_type" → merged item

    # ── DEALS ────────────────────────────────────────────────────────────────
    for deal in data.get("deals", []):
        account = deal["account"]
        stage = deal.get("stage", "Discovery")
        stage_rank = STAGE_ORDER.get(stage, 0)
        arr = deal.get("arr", 0)
        close_date_str = deal.get("close_date")
        close_date = date.fromisoformat(close_date_str) if close_date_str else None
        days_to_close = (close_date - today).days if close_date else None
        last_activity = deal.get("last_activity_days_ago", 0)
        nq = deal.get("next_step_quality", "missing")
        contacts = deal.get("contacts", [])
        contacts_count = len(contacts) if contacts else 1

        # Null-guard: customer_waiting_for must not be empty if customer_waiting is True
        if deal.get("customer_waiting") and not deal.get("customer_waiting_for"):
            deal["customer_waiting_for"] = ["(pending — check CRM for details)"]

        base_context = {
            "arr": arr,
            "stage": stage,
            "days_to_close": days_to_close,
            "last_activity_days_ago": last_activity,
            "deal_id": deal["id"],
            "close_date": close_date_str,
            "industry": deal.get("industry"),
            "current_use_cases": deal.get("current_use_cases", []),
            "contacts": contacts,
            "account_tier": deal.get("account_tier", "Tier 3"),
        }

        # ── P0: customer waiting ─────────────────────────────────────────────
        if deal.get("customer_waiting"):
            items_waiting = deal["customer_waiting_for"]
            action = f"Send {', '.join(items_waiting)}"
            reason = ["CUSTOMER_WAITING"]
            if deal.get("commitment_due_today"):
                reason.append("COMMITMENT_DUE_TODAY")
            _merge(items, account, "send_deliverables", "P0", reason, action,
                   {**base_context, "customer_waiting_for": items_waiting})

        # ── P0: commitment due today (standalone — not already merged above) ─
        elif deal.get("commitment_due_today"):
            ns = deal.get("next_step") or {}
            action_text = ns.get("action", "Complete committed deliverable") if isinstance(ns, dict) else "Complete committed deliverable"
            _merge(items, account, "send_deliverables", "P0",
                   ["COMMITMENT_DUE_TODAY"], action_text, base_context)

        # ── P1: overdue close date ───────────────────────────────────────────
        # If account already has any item, append reason code rather than creating
        # a separate item — close date urgency is context, not a distinct action.
        if close_date and close_date < today:
            existing = [v for k, v in items.items() if v["account"] == account]
            if existing:
                for item in existing:
                    if "OVERDUE_CLOSE_DATE" not in item["reason_codes"]:
                        item["reason_codes"].append("OVERDUE_CLOSE_DATE")
            else:
                _merge(items, account, "review_deal", "P1",
                       ["OVERDUE_CLOSE_DATE"],
                       f"Review deal status — close date passed {abs(days_to_close)} days ago",
                       base_context)

        # ── P1: close date within 14 days ────────────────────────────────────
        elif days_to_close is not None and 0 <= days_to_close <= 14:
            existing = [v for k, v in items.items() if v["account"] == account]
            if existing:
                for item in existing:
                    if "CLOSE_DATE_IMMINENT" not in item["reason_codes"]:
                        item["reason_codes"].append("CLOSE_DATE_IMMINENT")
            else:
                _merge(items, account, "review_deal", "P1",
                       ["CLOSE_DATE_IMMINENT"],
                       f"Close date in {days_to_close} days — confirm next steps",
                       base_context)

        # ── P1: missing/weak next step at Technical Evaluation or later ──────
        if stage_rank >= STAGE_ORDER["Technical Evaluation"]:
            if nq == "missing":
                _merge(items, account, "update_next_step", "P1",
                       ["MISSING_NEXT_STEP"],
                       "Add a specific next step with owner and due date",
                       base_context)
            elif nq == "weak":
                _merge(items, account, "update_next_step", "P1",
                       ["WEAK_NEXT_STEP_NOT_ACTIONABLE"],
                       "Replace vague next step with a specific action, owner, and date",
                       base_context)

        # ── P2: missing/weak next step at Discovery ──────────────────────────
        elif stage_rank == STAGE_ORDER["Discovery"]:
            if nq in ("missing", "weak"):
                _merge(items, account, "update_next_step", "P2",
                       ["WEAK_NEXT_STEP_EARLY_STAGE"],
                       "Set a concrete next step before this goes cold",
                       base_context)

        # ── P1: pilot blocked by missing stakeholder ─────────────────────────
        if deal.get("critical_stakeholder_missing") and deal.get("pilot_blocked"):
            stakeholder = deal.get("missing_stakeholder", "key stakeholder")
            _merge(items, account, "loop_in_stakeholder", "P1",
                   ["PILOT_BLOCKED"],
                   f"Loop in {stakeholder} — pilot sign-off is blocked without them",
                   base_context)

        # ── Cross-tier: single-threaded at late stage ─────────────────────────
        # This appends SINGLE_THREADED_RISK to any existing item for this account,
        # or creates a P1 item if none exists yet.
        if contacts_count == 1 and stage_rank >= STAGE_ORDER["Technical Evaluation"]:
            # Find any existing item for this account and append the reason code
            account_items = [v for k, v in items.items() if v["account"] == account]
            if account_items:
                for item in account_items:
                    if "SINGLE_THREADED_RISK" not in item["reason_codes"]:
                        item["reason_codes"].append("SINGLE_THREADED_RISK")
            else:
                _merge(items, account, "update_next_step", "P1",
                       ["SINGLE_THREADED_RISK"],
                       "Single contact at late stage — identify and add a second stakeholder",
                       base_context)

    # ── MEETINGS (P0 if has_pending_deliverables) ────────────────────────────
    for meeting in data.get("meetings_today", []):
        if meeting.get("has_pending_deliverables"):
            account = meeting["account"]
            _merge(items, account, "send_deliverables", "P0",
                   ["MEETING_PREP_REQUIRED"],
                   f"Deliver open items before {meeting['time']} {meeting['title']}",
                   {"meeting_id": meeting["id"], "meeting_time": meeting["time"]})

    # ── PROSPECT REPLIES (P1) ────────────────────────────────────────────────
    for reply in data.get("prospect_replies", []):
        account = reply["account"]
        contact = reply.get("contact", "prospect")
        minutes_ago = reply.get("replied_minutes_ago", 0)
        _merge(items, account, "respond_to_reply", "P1",
               ["PROSPECT_REPLIED"],
               f"Respond to {contact}'s reply ({minutes_ago} min ago)",
               {
                   "replied_minutes_ago": minutes_ago,
                   "icp_fit": reply.get("icp_fit"),
                   "reply_summary": reply.get("reply_summary"),
               })

    # ── INBOUND LEADS ────────────────────────────────────────────────────────
    for lead in data.get("inbound_leads", []):
        account = lead["account"]
        inbound_type = lead.get("inbound_type")
        tier = "P1" if inbound_type == "demo_request" else "P2"
        reason = ["HIGH_INTENT_INBOUND"] if tier == "P1" else ["GENERAL_INBOUND"]
        _merge(items, account, "respond_to_inbound", tier,
               reason,
               f"Respond to {lead['contact']} — {inbound_type.replace('_', ' ')} ({lead['received_hours_ago']}h ago)",
               {
                   "inbound_type": inbound_type,
                   "icp_fit": lead.get("icp_fit"),
                   "received_hours_ago": lead.get("received_hours_ago"),
                   "notes": lead.get("notes"),
               })

    # ── POST-PROCESS: merge review_deal items into higher-tier items ─────────
    # review_deal items (CLOSE_DATE_IMMINENT, OVERDUE_CLOSE_DATE) are context,
    # not separate tasks. If the account already has a higher-tier item, absorb
    # the reason codes into it and drop the review_deal item.
    review_keys = [k for k, v in items.items() if v["action_type"] == "review_deal"]
    for key in review_keys:
        review_item = items[key]
        account = review_item["account"]
        other_items = [v for k, v in items.items()
                       if v["account"] == account and v["action_type"] != "review_deal"]
        if other_items:
            best = min(other_items, key=lambda x: TIER_RANK[x["tier"]])
            for rc in review_item["reason_codes"]:
                if rc not in best["reason_codes"]:
                    best["reason_codes"].append(rc)
            del items[key]

    # ── RANK ─────────────────────────────────────────────────────────────────
    priorities = list(items.values())
    priorities.sort(key=_rank_key)

    for i, item in enumerate(priorities, start=1):
        item["rank"] = i

    return {
        "priorities": priorities,
        "hygiene": data.get("hygiene_tasks", []),
        "meetings_today": data.get("meetings_today", []),
        "rep": data.get("rep", {}),
    }


def _rank_key(item: dict):
    """
    Sort order: tier → hard deadline → customer waiting → response freshness
                → deal stage → deal ARR → staleness
    """
    tier = TIER_RANK.get(item["tier"], 99)
    rc = item["reason_codes"]
    ctx = item.get("context", {})

    has_deadline    = 0 if "COMMITMENT_DUE_TODAY" in rc else 1
    has_waiting     = 0 if "CUSTOMER_WAITING" in rc else 1
    freshness       = ctx.get("replied_minutes_ago", 9999)          # lower = more recent
    stage_rank      = STAGE_ORDER.get(ctx.get("stage", ""), 0)
    acct_tier       = ACCOUNT_TIER_RANK.get(ctx.get("account_tier", "Tier 3"), 2)
    arr             = -(ctx.get("arr") or 0)                        # negate: higher ARR = lower sort value
    staleness       = ctx.get("last_activity_days_ago", 0)          # higher = more stale = higher priority

    # Sort order: tier → deadline → waiting → freshness → stage → account tier → ARR → staleness
    return (tier, has_deadline, has_waiting, freshness, -stage_rank, acct_tier, arr, -staleness)
