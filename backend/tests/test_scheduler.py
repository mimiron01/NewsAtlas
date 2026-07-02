from app.services import scheduler


def test_start_registers_jobs_and_shutdown_clears_them():
    scheduler.start(interval_hours=6, send_time="07:30")
    try:
        job_ids = {job.id for job in scheduler._scheduler.get_jobs()}
        assert job_ids == {scheduler.INGESTION_JOB_ID, scheduler.DIGEST_JOB_ID}

        digest_job = scheduler._scheduler.get_job(scheduler.DIGEST_JOB_ID)
        assert digest_job.trigger.fields[5].expressions[0].first == 7  # hour
        assert digest_job.trigger.fields[6].expressions[0].first == 30  # minute
    finally:
        scheduler.shutdown()

    assert scheduler._scheduler is None


def test_reschedule_updates_running_jobs():
    scheduler.start(interval_hours=6, send_time="07:00")
    try:
        scheduler.reschedule(interval_hours=12, send_time="09:15")
        digest_job = scheduler._scheduler.get_job(scheduler.DIGEST_JOB_ID)
        assert digest_job.trigger.fields[5].expressions[0].first == 9
        assert digest_job.trigger.fields[6].expressions[0].first == 15

        ingestion_job = scheduler._scheduler.get_job(scheduler.INGESTION_JOB_ID)
        assert ingestion_job.trigger.interval.total_seconds() == 12 * 3600
    finally:
        scheduler.shutdown()


def test_reschedule_is_noop_when_not_started():
    scheduler.reschedule(interval_hours=1, send_time="00:00")  # should not raise
