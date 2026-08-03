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
    # Legacy/derived: kept in sync as aliases + context_terms on every write (see
    # services/target_company_terms.py). NewsAPI.org/NewsData.io query building and the AI
    # prompts still read this single flat list, so splitting the term roles below didn't
    # have to touch any of them (docs/google-news-quality-planning.html §7.2).
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    # --- Term roles (docs/google-news-quality-planning.html §7.1) ---
    # One `keywords` list previously did two incompatible jobs: the Google query treated it
    # as a required topic narrower (name AND (kw…)) while the grounding guard treated it as
    # an identity alias (name OR kw…). Neither role worked properly, and a generic keyword
    # was enough for an article that never named the company to be attributed to it.
    #
    # aliases are identity: other ways this company is named. They are OR'd with the name,
    # and they are the ONLY terms that satisfy the grounding guard.
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    # context_terms are topicality: AND'd as an OR-group to narrow the query. They never
    # satisfy grounding — an article matching only these isn't about this company.
    context_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    # exclude_terms are negations, emitted as Google's -term.
    exclude_terms: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Trusted domains this company's Google News query is restricted to.
    # NULL = inherit workspace_settings.google_news_source_allowlist; [] = explicitly
    # unrestricted; non-empty = replaces the workspace list entirely. This overrides rather
    # than extends (superseding docs/v1-release-roadmap.html §2.3) because site: is a hard
    # restriction: under the old union semantics a workspace allowlist silently
    # hard-restricted every company, and no company could ever narrow or opt out.
    google_news_source_allowlist: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=None
    )
    # Domains never accepted for this company, emitted as -site:. Unlike the allowlist this
    # is unioned with the workspace denylist: a subtractive workspace-wide policy shouldn't
    # be silently droppable by one company, and union fails safe (see §7.6).
    google_news_source_denylist: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list
    )
    # Wraps identity terms in Google's intitle:, so only articles naming the company in the
    # headline match. A strong precision lever for generic company names and an equally
    # strong recall cost otherwise, so it's per-company and off by default.
    google_news_require_name_in_title: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    # Per-company news edition, with the same NULL-means-inherit semantics ThemeWatch
    # already uses (see models/theme_watch.py). A single workspace-wide edition can only
    # ever be right for one market: searching a German company in the US:en edition
    # returns whatever thin English-language coverage happens to exist, which is noise by
    # construction (docs/google-news-quality-planning.html finding F4). Also drives the
    # `language` parameter sent to NewsAPI.org/NewsData.io, so one company has one
    # language concept rather than three.
    google_news_country: Mapped[str | None] = mapped_column(String(8), nullable=True)
    google_news_language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Set once a NewsData.io historical archive backfill has run for this company (see
    # services/newsdata_backfill.py) — guards against re-spending archive credits every
    # time a paused company is reactivated.
    backfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
