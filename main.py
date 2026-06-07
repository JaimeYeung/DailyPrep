import argparse
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from mock_data import data as crm_data
from priority_engine import classify
from claude_generator import generate_daily_email, generate_brief
from email_sender import send_email
from scheduler import build_scheduler

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-5s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("run.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

SENT_BRIEFS_PATH = Path("sent_briefs.json")


def load_sent_briefs() -> dict:
    if SENT_BRIEFS_PATH.exists():
        try:
            return json.loads(SENT_BRIEFS_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_sent_briefs(briefs: dict):
    SENT_BRIEFS_PATH.write_text(json.dumps(briefs, indent=2))


# ── Job: Daily Priority Email ─────────────────────────────────────────────────
def run_daily_job():
    log.info("Daily priority job started")
    classified = classify(crm_data)

    p0 = sum(1 for x in classified["priorities"] if x["tier"] == "P0")
    p1 = sum(1 for x in classified["priorities"] if x["tier"] == "P1")
    p2 = sum(1 for x in classified["priorities"] if x["tier"] == "P2")
    p3 = len(classified["hygiene"])
    log.info(f"priority_engine: {p0} P0, {p1} P1, {p2} P2, {p3} P3 (hygiene)")

    body = generate_daily_email(classified)
    log.info("Claude API: daily email generated")

    rep = classified["rep"]
    today_label = datetime.now().strftime("%A, %B %d")
    subject = f"Your Sales Priorities for {today_label}"

    send_email(subject, body, rep["email"])
    log.info(f"Daily email sent to {rep['email']}")
    log.info("Daily priority job completed")


# ── Job: Pre-Meeting Brief Check ──────────────────────────────────────────────
def run_brief_check(force_meeting_id: str = None):
    now = datetime.now()
    sent_briefs = load_sent_briefs()
    rep = crm_data["rep"]

    for meeting in crm_data.get("meetings_today", []):
        meeting_id = meeting["id"]
        meeting_time = datetime.strptime(meeting["time"], "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )
        minutes_until = (meeting_time - now).total_seconds() / 60

        dedup_key = f"{meeting_id}_{meeting_time.isoformat()}"

        # Skip non-target meetings unless explicitly forced
        if force_meeting_id and meeting_id != force_meeting_id:
            continue

        # Determine if this meeting should get a brief now
        is_in_window = 45 <= minutes_until <= 75
        is_late_brief = 0 < minutes_until < 45
        already_sent = dedup_key in sent_briefs

        if already_sent and not force_meeting_id:
            log.info(f"Meeting {meeting_id} already briefed (dedup key match), skipping")
            continue

        if not is_in_window and not is_late_brief and not force_meeting_id:
            continue

        # Find the matching deal
        deal_id = meeting.get("deal_id")
        deal = next((d for d in crm_data["deals"] if d["id"] == deal_id), None)

        if not deal:
            log.warning(f"No matching deal for meeting {meeting_id} (deal_id={deal_id}), skipping brief")
            continue

        if is_late_brief and not force_meeting_id:
            log.info(f"LATE_BRIEF: {meeting_id} starts in {int(minutes_until)} min — sending immediately")

        log.info(f"Generating brief for {meeting_id}: {meeting['title']} at {meeting['time']}")
        body = generate_brief(meeting, deal)
        log.info("Claude API: pre-meeting brief generated")

        subject = f"Pre-Meeting Brief: {meeting['title']} — {meeting['time']} Today"
        send_email(subject, body, rep["email"])
        log.info(f"Brief sent to {rep['email']}")

        sent_briefs[dedup_key] = {
            "meeting_id": meeting_id,
            "sent_at": now.isoformat(),
            "forced": bool(force_meeting_id),
        }
        save_sent_briefs(sent_briefs)
        log.info(f"Dedup key {dedup_key} saved to sent_briefs.json")


# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Hebbia Sales Assistant")
    parser.add_argument("--daily-now", action="store_true",
                        help="Immediately send daily priority email")
    parser.add_argument("--brief", action="store_true",
                        help="Send pre-meeting brief for a specific meeting")
    parser.add_argument("--meeting-id", type=str,
                        help="Meeting ID to brief (used with --brief)")
    parser.add_argument("--force", action="store_true",
                        help="Re-send brief even if already sent")
    args = parser.parse_args()

    if args.daily_now:
        run_daily_job()
        return

    if args.brief:
        if not args.meeting_id:
            parser.error("--brief requires --meeting-id")
        # When --force, clear the dedup key for this meeting first
        if args.force:
            sent_briefs = load_sent_briefs()
            keys_to_remove = [k for k in sent_briefs if k.startswith(args.meeting_id)]
            for k in keys_to_remove:
                del sent_briefs[k]
            save_sent_briefs(sent_briefs)
            log.info(f"--force: cleared dedup keys for {args.meeting_id}")
        run_brief_check(force_meeting_id=args.meeting_id)
        return

    # Default: start the scheduler
    log.info("Starting scheduler (Ctrl+C to stop)")
    timezone = crm_data["rep"].get("timezone", "America/Los_Angeles")
    scheduler = build_scheduler(run_daily_job, run_brief_check, timezone)
    scheduler.start()


if __name__ == "__main__":
    main()
