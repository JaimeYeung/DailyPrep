from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

def build_scheduler(daily_job_fn, brief_check_fn, timezone_str="America/Los_Angeles"):
    tz = pytz.timezone(timezone_str)
    scheduler = BlockingScheduler(timezone=tz)

    # Daily priority email — weekdays only at 8:00 AM
    scheduler.add_job(
        daily_job_fn,
        CronTrigger(day_of_week="mon-fri", hour=8, minute=0, timezone=tz),
        id="daily_priority",
        name="Daily Priority Email",
    )

    # Pre-meeting brief check — every 15 minutes
    scheduler.add_job(
        brief_check_fn,
        IntervalTrigger(minutes=15),
        id="brief_check",
        name="Pre-Meeting Brief Check",
    )

    return scheduler
