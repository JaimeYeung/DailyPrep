from datetime import date, timedelta

today = date.today()

data = {
    "rep": {
        "name": "James Yang",
        "email": "jamesyanglh@gmail.com",
        "domain": "hebbia.ai",
        "timezone": "America/Los_Angeles"
    },
    "deals": [
        {
            "id": "deal_001",
            "account": "Blackstone",
            "account_tier": "Tier 1",
            "industry": "Private Equity",
            "current_solution": "Bloomberg Terminal + manual analyst research + internal Excel models",
            "recent_news": [
                "Blackstone raised $30B for BREIT real estate fund in Q1 2026",
                "Expanding technology infrastructure investment team — 12 open roles in NY"
            ],
            "current_use_cases": ["Investment research automation", "Document due diligence"],
            "stage": "Technical Evaluation",
            "arr": 180000,
            "close_date": str(today + timedelta(days=38)),
            "last_activity_days_ago": 12,
            "next_step": None,
            "next_step_quality": "missing",
            "contacts": [
                {"name": "David Park", "title": "VP of Research", "role": "Champion", "last_engaged_days_ago": 12}
            ],
            "customer_waiting": True,
            "customer_waiting_for": ["Security documentation"],
            "commitment_due_today": False,
            "critical_stakeholder_missing": False,
            "notes": "Champion is VP of Research. Single-threaded at Evaluation stage. No economic buyer identified."
        },
        {
            "id": "deal_002",
            "account": "KKR",
            "account_tier": "Tier 1",
            "industry": "Private Equity",
            "current_solution": "Bloomberg + manual document review + internal knowledge base (Confluence)",
            "recent_news": [
                "KKR announced $20B North America PE Fund XII closing in March 2026",
                "Actively hiring quantitative analysts and data scientists across portfolio companies"
            ],
            "current_use_cases": ["Portfolio company research", "Deal sourcing analysis", "LP reporting"],
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
            "contacts": [
                {"name": "John Smith", "title": "Head of Technology", "role": "Economic Buyer", "last_engaged_days_ago": 3},
                {"name": "Mary Wong", "title": "Head of Procurement", "role": "Procurement", "last_engaged_days_ago": 3},
                {"name": "James Lee", "title": "VP of Research", "role": "Champion", "last_engaged_days_ago": 5}
            ],
            "customer_waiting": True,
            "customer_waiting_for": ["Security whitepaper", "Revised pricing proposal"],
            "commitment_due_today": True,
            "critical_stakeholder_missing": False,
            "notes": "Strong engagement. Legal review started. Procurement loop in. Customer actively waiting on two deliverables."
        },
        {
            "id": "deal_003",
            "account": "Citadel",
            "account_tier": "Tier 2",
            "industry": "Hedge Fund",
            "current_solution": "Proprietary internal tools + Bloomberg + manual document parsing by analysts",
            "recent_news": [
                "Citadel posted record $16B profit in 2025, expanding research headcount",
                "Opening new London quantitative research hub in Q2 2026"
            ],
            "current_use_cases": ["Quantitative research", "Earnings call analysis"],
            "stage": "Discovery",
            "arr": 95000,
            "close_date": str(today + timedelta(days=75)),
            "last_activity_days_ago": 18,
            "next_step": "follow up sometime",
            "next_step_quality": "weak",
            "contacts": [
                {"name": "Rachel Kim", "title": "Director of Research", "role": "Champion", "last_engaged_days_ago": 18}
            ],
            "customer_waiting": False,
            "customer_waiting_for": [],
            "commitment_due_today": False,
            "critical_stakeholder_missing": False,
            "notes": "Met once. Champion went quiet. Single contact but still early Discovery."
        },
        {
            "id": "deal_004",
            "account": "Apollo Global",
            "account_tier": "Tier 2",
            "industry": "Private Equity",
            "current_solution": "Bloomberg + Excel-based credit models + manual portfolio monitoring reports",
            "recent_news": [
                "Apollo closed $20B flagship PE fund in February 2026",
                "Hiring credit research analysts across New York and London offices"
            ],
            "current_use_cases": ["Credit research", "Portfolio monitoring"],
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
            "contacts": [
                {"name": "Michael Chen", "title": "Managing Director", "role": "Champion", "last_engaged_days_ago": 5},
                {"name": "Sarah Liu", "title": "VP of Operations", "role": "Evaluator", "last_engaged_days_ago": 7}
            ],
            "customer_waiting": False,
            "customer_waiting_for": [],
            "commitment_due_today": False,
            "critical_stakeholder_missing": True,
            "missing_stakeholder": "IT / Security",
            "pilot_blocked": True,
            "notes": "Second demo requested. Positive signals. IT/Security not looped in — will block pilot sign-off."
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
