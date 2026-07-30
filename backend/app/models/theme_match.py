import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.article import ArticleSource
from app.models.mixins import UUIDPrimaryKeyMixin
from app.models.signal import SignalStatus


class ThemeMatch(Base, UUIDPrimaryKeyMixin):
    """A single article matched to a ThemeWatch — merges what Article+Signal are for the
    per-company path into one row, since a theme match is always AI-summarized before
    being kept (there's no separate "raw fetched, not yet analyzed" state worth
    persisting on its own). See docs/theme-search-planning.html §2.3."""

    __tablename__ = "theme_matches"

    theme_watch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theme_watches.id", ondelete="CASCADE"), nullable=False
    )
    # Google News RSS only until docs/google-news-quality-planning.html §11 lifted the
    # single-provider rule — which is exactly why this was kept as a column rather than
    # hardcoded, so the reversal needed no migration here.
    source: Mapped[ArticleSource] = mapped_column(
        Enum(
            ArticleSource,
            name="article_source",
            create_type=False,
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=ArticleSource.GOOGLE_NEWS_RSS,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Populated when NewsData.io's full-content option returns a body, or when snippet
    # enrichment fetched one. Mirrors Article.full_content — themes had no equivalent while
    # Google News RSS was their only provider, which is why every theme match was
    # permanently headline-only (docs/google-news-quality-planning.html finding F17).
    full_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The publisher URL behind a Google News redirect link, once resolved. See
    # Article.canonical_url — same role, same fallback behaviour.
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_enriched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # mistral-embed vector, feeding the cross-path duplicate check against both other
    # ThemeMatch rows and the matched company's own Article rows (see §6).
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    duplicate_of_match_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theme_matches.id", ondelete="SET NULL"), nullable=True
    )

    # What the AI extraction pass identified, verbatim from the article — not yet matched
    # against TargetCompany.name. NULL means "no specific company" (a kept, not a dropped,
    # state — see docs/theme-search-planning.html §1).
    extracted_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Auto-populated (no user action) whenever extracted_company_name case-insensitively
    # matches an existing TargetCompany — see §4.3. Drives whether "Track this company"
    # renders at all (only when this is NULL and extracted_company_name isn't).
    matched_target_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_companies.id", ondelete="SET NULL"), nullable=True
    )

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
    supporting_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    relevance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signal_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    entities: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Reuses Signal's status enum/transition UI rather than inventing a parallel type.
    status: Mapped[SignalStatus] = mapped_column(
        Enum(SignalStatus, name="signal_status", create_type=False),
        nullable=False,
        default=SignalStatus.NEW,
    )

    # Same vocabulary as Article.skip_reason: "duplicate", "triaged_out", "ai_error". No
    # "company_mismatch" — that concept doesn't apply here (see
    # docs/theme-search-planning.html §4.2).
    skip_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    triage_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Token usage for the summarization call that produced this match, same per-row cost
    # visibility Signal already has.
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    @property
    def headline_only(self) -> bool:
        """Same computed expression as Article.is_headline_only: true only for an
        unenriched Google News RSS row, whose description is a mechanical repeat of the
        title. Once a second provider serves this theme, or enrichment fetches a real
        snippet, this stops being constantly true."""
        return self.source == ArticleSource.GOOGLE_NEWS_RSS and not self.content_enriched
