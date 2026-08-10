from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.db.session import SessionLocal
from app.models.ingestion_run import TRIGGER_SCHEDULED
from app.services.digest import send_daily_digest
from app.services.ingestion_runs import create_run, execute_ingestion_run, get_running_run

# Full signal runs (companies + topics) on a fixed cadence: every 4 hours Monday
# through Friday, and once in the evening on Saturday/Sunday when there's far less
# news volume to justify the weekday frequency. Two jobs rather than one cron
# expression because the weekday and weekend cadences don't share a single pattern.
INGESTION_JOB_ID_WEEKDAY = "news_ingestion_weekday"
INGESTION_JOB_ID_WEEKEND = "news_ingestion_weekend"
DIGEST_JOB_ID = "daily_digest"

_scheduler: BackgroundScheduler | None = None


def _run_ingestion_job() -> None:
    db = SessionLocal()
    try:
        # Skips this tick rather than overlapping with a manual run still in progress
        # (e.g. a long run from "Fetch new signals" still summarizing when the interval
        # ticks over) — the next scheduled tick picks up whatever it missed.
        if get_running_run(db) is not None:
            return
        run_id = create_run(db, trigger=TRIGGER_SCHEDULED).id
    finally:
        db.close()
    execute_ingestion_run(run_id)


def _run_digest_job() -> None:
    db = SessionLocal()
    try:
        send_daily_digest(db)
    finally:
        db.close()


def _parse_time(value: str) -> tuple[int, int]:
    hour_str, minute_str = value.split(":")
    return int(hour_str), int(minute_str)


def start(send_time: str) -> None:
    """Start a fresh scheduler instance. Safe to call after shutdown()."""
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_ingestion_job,
        CronTrigger(day_of_week="mon-fri", hour="0,4,8,12,16,20", minute=0, timezone="UTC"),
        id=INGESTION_JOB_ID_WEEKDAY,
    )
    _scheduler.add_job(
        _run_ingestion_job,
        CronTrigger(day_of_week="sat,sun", hour=20, minute=0, timezone="UTC"),
        id=INGESTION_JOB_ID_WEEKEND,
    )
    hour, minute = _parse_time(send_time)
    _scheduler.add_job(
        _run_digest_job, CronTrigger(hour=hour, minute=minute, timezone="UTC"), id=DIGEST_JOB_ID
    )
    _scheduler.start()


def reschedule(send_time: str) -> None:
    """Apply a new digest send-time to the running scheduler, if any. No-op otherwise.
    The ingestion cadence is fixed, not configurable, so there's nothing to reschedule
    for those jobs."""
    if _scheduler is None or not _scheduler.running:
        return
    hour, minute = _parse_time(send_time)
    _scheduler.reschedule_job(DIGEST_JOB_ID, trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"))


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
