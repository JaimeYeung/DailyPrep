# Hebbia Sales Assistant — Daily Prep Automation

Automated push emails for sales reps. Two emails, zero manual effort:

1. **Daily Priority Email** — sent every weekday at 8:00 AM with a ranked P0/P1/P2 task list
2. **Pre-Meeting Brief** — sent 60 minutes before any external customer call

**Design principle:** Push, not pull. Reps never open a dashboard — everything arrives in their inbox automatically.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get a Gmail App Password

1. Go to your Google Account → Security → Enable 2-Step Verification
2. Security → App Passwords → Generate → copy the 16-character password

### 3. Get an Anthropic API Key

Get your key from [console.anthropic.com](https://console.anthropic.com)

### 4. Set environment variables

```bash
export GMAIL_APP_PASSWORD="your-16-char-app-password"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

### 5. Set your email address

In `mock_data.py`, update `rep.email` to your Gmail address.

---

## Running

### Start the scheduler (runs continuously)

```bash
python main.py
```

- Daily priority email fires every weekday at 8:00 AM (America/Los_Angeles)
- Brief check runs every 15 minutes; sends when a meeting is 45–75 min away

### Manual triggers

```bash
# Send daily priority email right now
python main.py --daily-now

# Send pre-meeting brief for a specific meeting
python main.py --brief --meeting-id meeting_001

# Force re-send even if brief was already sent
python main.py --brief --meeting-id meeting_001 --force
```

---

## File Structure

```
├── main.py              # Entry point; CLI flags for manual triggers
├── scheduler.py         # APScheduler: weekday-only, timezone-aware
├── priority_engine.py   # Rules engine: classify, deduplicate, rank
├── claude_generator.py  # Claude API: convert structured data to email copy
├── email_sender.py      # Gmail SMTP: send emails
├── mock_data.py         # Mock CRM data with dynamic relative dates
├── sent_briefs.json     # Tracks sent briefs to avoid duplicates
├── run.log              # Observability log
└── requirements.txt
```

## Architecture

```
mock_data.py (CRM data)
  → priority_engine.py (classify + deduplicate + rank — deterministic)
      → structured output: tier, reason_codes, rank, suggested_action
  → claude_generator.py (convert to email copy)
  → email_sender.py (send via Gmail SMTP)
```

Claude receives pre-classified, pre-ranked data. It does not decide what is P0 or P1.
