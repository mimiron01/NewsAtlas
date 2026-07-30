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
    # Same override semantics as TargetCompany.google_news_source_allowlist: NULL inherits
    # the workspace list, [] is explicitly unrestricted, non-empty replaces it entirely
    # (docs/google-news-quality-planning.html §7.6, superseding v1 roadmap §2.3's union).
    google_news_source_allowlist: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=None
    )
    # Unioned with the workspace denylist, unlike the allowlist above (§7.6).
    google_news_source_denylist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    # Emitted as Google's -term. A theme's query terms are broad by construction, so
    # negation is the main precision tool available to it.
    exclusion_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    # Which providers may serve this theme. NULL inherits
    # workspace_settings.theme_news_sources. Themes were Google-News-only until
    # docs/google-news-quality-planning.html §11 — a provider still has to be enabled
    # workspace-wide to be called, so this can never resurrect a disabled source.
    news_sources: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True, default=None)
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
