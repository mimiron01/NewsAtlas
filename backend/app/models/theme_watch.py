import uuid
from datetime import datetime

from sqlalchemy import ARRAY, Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ThemeWatch(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A topic to track (e.g. "Automotive", "Startup Series B") independent of any single
    named company — see docs/theme-search-planning.html. Shares TargetCompany's shape and
    permission model (shared catalog, case-insensitive dedupe, creator-or-admin edits)
    almost exactly, since it's a deliberate parallel concept, not a subclass of it."""

    __tablename__ = "theme_watches"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # At least one required — unlike TargetCompany.keywords, there's no company name to
    # fall back to, so an empty list would search nothing (see build_theme_query).
    query_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Same additive/union semantics with workspace_settings.google_news_source_allowlist
    # as TargetCompany.google_news_source_allowlist (v1 roadmap §2.3).
    google_news_source_allowlist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    # Per-theme Google News edition override. NULL means "inherit the workspace-wide
    # google_news_rss_country/language" — deliberately NULL-as-inherit rather than copying
    # the workspace value at creation time, so changing the workspace default later still
    # propagates to every theme that never opted out. A theme tracking a national market
    # ("Startups DE") needs its own edition; the workspace default can only ever be right
    # for one market at a time.
    google_news_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    google_news_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Per-theme cooldown clock for POST /theme-watches/{id}/run-now, deliberately separate
    # from workspace_settings.last_manual_ingestion_at: a single-theme run is one Google
    # News request plus a handful of Mistral calls, so it doesn't need to share the
    # workspace-wide manual-trigger budget with a full run over every company.
    last_manual_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
