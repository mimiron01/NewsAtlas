from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db.session import SessionLocal
from app.models.ingestion_run import TRIGGER_SCHEDULED
from app.services.digest import send_daily_digest
from app.services.ingestion_runs import create_run, execute_ingestion_run, get_running_run

INGESTION_JOB_ID = "news_ingestion"
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


def start(interval_hours: int, send_time: str) -> None:
    """Start a fresh scheduler instance. Safe to call after shutdown()."""
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _run_ingestion_job, IntervalTrigger(hours=interval_hours), id=INGESTION_JOB_ID
    )
    hour, minute = _parse_time(send_time)
    _scheduler.add_job(
        _run_digest_job, CronTrigger(hour=hour, minute=minute), id=DIGEST_JOB_ID
    )
    _scheduler.start()


def reschedule(interval_hours: int, send_time: str) -> None:
    """Apply new interval/send-time to the running scheduler, if any. No-op otherwise."""
    if _scheduler is None or not _scheduler.running:
        return
    _scheduler.reschedule_job(INGESTION_JOB_ID, trigger=IntervalTrigger(hours=interval_hours))
    hour, minute = _parse_time(send_time)
    _scheduler.reschedule_job(DIGEST_JOB_ID, trigger=CronTrigger(hour=hour, minute=minute))


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
