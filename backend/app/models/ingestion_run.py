import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

TRIGGER_MANUAL = "manual"
TRIGGER_SCHEDULED = "scheduled"


class IngestionRun(Base, UUIDPrimaryKeyMixin):
    """One row per ingestion pipeline execution (manual button click or the periodic
    scheduler job). Doubles as both the live-progress record a running pipeline updates
    as it works through target companies/articles (see services/ingestion_runs.py) and
    the persisted history an admin reads on the Settings > Logs tab — including any
    errors, so a scheduled run that fails overnight isn't silently invisible."""

    __tablename__ = "ingestion_runs"

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_RUNNING)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Live progress, updated in place while status == "running" (see ProgressTracker) ---
    companies_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    companies_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_step: Mapped[str | None] = mapped_column(String(16), nullable=True)
    current_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    articles_total_this_company: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_processed_this_company: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Final result, populated once the run finishes (mirrors IngestionRunResult) ---
    articles_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    articles_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signals_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicates_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    triaged_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    by_source: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    rate_limited: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    # Appended to live, as each error happens, not just assembled at the end — so a run
    # that never reaches a settled state still shows what went wrong so far.
    errors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Set only when the whole run crashed unexpectedly (vs. the per-article/per-source
    # failures already captured in `errors`, which the pipeline recovers from and continues).
    fatal_error: Mapped[str | None] = mapped_column(Text, nullable=True)
