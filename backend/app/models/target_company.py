import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TargetCompany(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "target_companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Additive to workspace_settings.google_news_source_allowlist (union, not override —
    # see docs/v1-release-roadmap.html §2.3): trusted domains this company's Google News
    # RSS query is additionally restricted to, on top of the workspace-wide defaults.
    google_news_source_allowlist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Set once a NewsData.io historical archive backfill has run for this company (see
    # services/newsdata_backfill.py) — guards against re-spending archive credits every
    # time a paused company is reactivated.
    backfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
