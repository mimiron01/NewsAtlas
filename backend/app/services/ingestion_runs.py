import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.audit import log_event
from app.db.session import SessionLocal
from app.models.ingestion_run import (
    STATUS_CANCELLED,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_RUNNING,
    IngestionRun,
)
from app.models.target_company import TargetCompany
from app.schemas.ingestion import IngestionRunStatusResponse
from app.services.ingestion import run_ingestion


class ProgressTracker:
    """Writes live progress from a running ingestion pipeline onto its IngestionRun row —
    the concrete IngestionProgress implementation used outside of tests. Each call is its
    own small commit: runs are long enough (seconds to low minutes) that the write cost is
    negligible next to the news-fetch/AI calls it's bracketing, and it means a poller never
    sees a half-written update."""

    def __init__(self, db: Session, run_id: uuid.UUID) -> None:
        self.db = db
        self.run_id = run_id

    def update(self, **fields: object) -> None:
        self.db.query(IngestionRun).filter(IngestionRun.id == self.run_id).update(fields)
        self.db.commit()

    def append_error(self, message: str) -> None:
        run = self.db.get(IngestionRun, self.run_id)
        if run is None:
            return
        run.errors = [*run.errors, message]
        self.db.commit()

    def should_cancel(self) -> bool:
        # Single-column read, called at the same cadence as update() (every checkpoint) —
        # cheap next to the news-fetch/AI call it's bracketing.
        return bool(
            self.db.query(IngestionRun.cancel_requested)
            .filter(IngestionRun.id == self.run_id)
            .scalar()
        )


def get_running_run(db: Session) -> IngestionRun | None:
    return (
        db.query(IngestionRun)
        .filter(IngestionRun.status == STATUS_RUNNING)
        .order_by(IngestionRun.started_at.desc())
        .first()
    )


def get_latest_run(db: Session) -> IngestionRun | None:
    return db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).first()


def list_runs(db: Session, limit: int = 50) -> list[IngestionRun]:
    return db.query(IngestionRun).order_by(IngestionRun.started_at.desc()).limit(limit).all()


def request_cancel(db: Session, run_id: uuid.UUID) -> IngestionRun | None:
    """Marks a running IngestionRun for cancellation; the pipeline notices at its next
    checkpoint (see IngestionProgress.should_cancel / ProgressTracker.should_cancel above)
    and stops cleanly, flipping status to "cancelled" itself once it does. Returns the run
    row regardless of its current status (None only if run_id doesn't exist) — the caller
    (api/ingestion.py) decides the right HTTP response for an already-finished run."""
    run = db.get(IngestionRun, run_id)
    if run is None:
        return None
    if run.status == STATUS_RUNNING and not run.cancel_requested:
        run.cancel_requested = True
        db.commit()
        db.refresh(run)
    return run


def create_run(
    db: Session, *, trigger: str, triggered_by_user_id: uuid.UUID | None = None
) -> IngestionRun:
    # A best-effort initial estimate — run_ingestion() re-confirms it via progress.update()
    # once it queries active target companies itself, moments later.
    companies_total = db.query(TargetCompany).filter(TargetCompany.is_active.is_(True)).count()
    run = IngestionRun(
        trigger=trigger,
        status=STATUS_RUNNING,
        triggered_by_user_id=triggered_by_user_id,
        companies_total=companies_total,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_ingestion_run(run_id: uuid.UUID) -> None:
    """Runs the ingestion pipeline against `run_id`'s row and finalizes it — the top-level
    boundary for both the manual-trigger background task and the scheduled job, so it opens
    its own session rather than reusing a request-scoped or caller-scoped one.

    Catches any exception, not just the pipeline's own recoverable NewsClientError/
    AIClientError (already handled inside run_ingestion and folded into `errors`): an
    unexpected crash here must still flip the row out of "running", or the progress bar
    would spin forever and the failure would never reach the admin Logs view.
    """
    db = SessionLocal()
    try:
        tracker = ProgressTracker(db, run_id)
        try:
            result = run_ingestion(db, progress=tracker)
        except Exception as exc:  # noqa: BLE001 - top-level background job boundary
            log_event("ingestion_run_failed", run_id=str(run_id), error=str(exc))
            db.query(IngestionRun).filter(IngestionRun.id == run_id).update(
                {
                    "status": STATUS_FAILED,
                    "fatal_error": str(exc),
                    "finished_at": datetime.now(timezone.utc),
                }
            )
            db.commit()
            return

        db.query(IngestionRun).filter(IngestionRun.id == run_id).update(
            {
                # A cancellation is a clean stop, not a failure — result already holds
                # accurate partial counters for whatever was processed before the
                # pipeline noticed cancel_requested (see run_ingestion/should_cancel).
                "status": STATUS_CANCELLED if result.cancelled else STATUS_COMPLETED,
                "finished_at": datetime.now(timezone.utc),
                "companies_processed": result.target_companies_processed,
                "articles_fetched": result.articles_fetched,
                "articles_new": result.articles_new,
                "signals_created": result.signals_created,
                "duplicates_skipped": result.duplicates_skipped,
                "triaged_out": result.triaged_out,
                "by_source": result.by_source,
                "rate_limited": result.rate_limited,
                "errors": result.errors,
            }
        )
        db.commit()
    finally:
        db.close()


def progress_percent(run: IngestionRun) -> int:
    if run.status != STATUS_RUNNING:
        return 100
    if run.companies_total <= 0:
        return 0
    companies_done = float(run.companies_processed)
    if run.articles_total_this_company > 0:
        companies_done += min(
            run.articles_processed_this_company / run.articles_total_this_company, 1.0
        )
    # Capped below 100 while still running so the bar never claims "done" a beat before
    # the row is actually marked completed/failed.
    return min(99, int(companies_done / run.companies_total * 100))


def to_status_response(run: IngestionRun) -> IngestionRunStatusResponse:
    return IngestionRunStatusResponse(
        id=run.id,
        status=run.status,
        cancel_requested=run.cancel_requested,
        trigger=run.trigger,
        started_at=run.started_at,
        finished_at=run.finished_at,
        progress_percent=progress_percent(run),
        current_step=run.current_step,
        current_company_name=run.current_company_name,
        companies_total=run.companies_total,
        companies_processed=run.companies_processed,
        articles_total_this_company=run.articles_total_this_company,
        articles_processed_this_company=run.articles_processed_this_company,
        articles_fetched=run.articles_fetched,
        articles_new=run.articles_new,
        signals_created=run.signals_created,
        duplicates_skipped=run.duplicates_skipped,
        triaged_out=run.triaged_out,
        by_source=run.by_source,
        rate_limited=run.rate_limited,
        errors=run.errors,
        fatal_error=run.fatal_error,
    )
