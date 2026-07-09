import enum
import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKeyMixin


class ArticleSource(str, enum.Enum):
    NEWSAPI = "newsapi"
    GOOGLE_NEWS_RSS = "google_news_rss"
    NEWSDATA = "newsdata"


class Article(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "articles"

    target_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_companies.id", ondelete="CASCADE"), nullable=False
    )
    # Which ingestion provider surfaced this row — distinct from source_name below, which
    # is the underlying publisher (e.g. "TechCrunch"), not the API that returned it.
    source: Mapped[ArticleSource] = mapped_column(
        Enum(ArticleSource, name="article_source", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
        default=ArticleSource.NEWSAPI,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Full article body — only ever populated for NewsData.io articles fetched with its
    # paid-tier full-content option; null for NewsAPI.org/Google News RSS, which only ever
    # provide a title+snippet. When present, used to ground summarization instead of the
    # (much shorter) description.
    full_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NewsData.io's own sentiment/AI-tag output, captured verbatim as auxiliary metadata —
    # kept separate from (not merged into) Mistral's own confidence/signal_type/entities on
    # the resulting Signal, since they come from a different model/vendor.
    external_sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # mistral-embed vector over title+description, used for cheap semantic-duplicate
    # detection before spending a full chat-completion call on near-identical coverage.
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
    duplicate_of_article_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL"), nullable=True
    )
    # Why no Signal was created, when applicable: "duplicate", "triaged_out", "ai_error",
    # "company_mismatch" (the AI determined the article isn't actually about
    # target_company despite matching the fetch query — see
    # docs/ingestion-reliability-planning.html §5). NULL means a Signal was created (or
    # the article hasn't been processed yet).
    skip_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
