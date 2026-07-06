import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.article import ArticleSource
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class NewsSourceUsageLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One row per outbound call to a news provider — mirrors AIUsageLog's role for
    Mistral spend, but for news-fetch requests/credits. Has two jobs: it's what an admin
    reads on the Settings page to see usage against their plan, and it's the data
    services/news_rate_limiter.py queries to decide whether a source still has headroom
    before making another call (see docs/news-source-expansion-planning.html §9)."""

    __tablename__ = "news_source_usage_logs"

    source: Mapped[ArticleSource] = mapped_column(
        Enum(ArticleSource, name="article_source", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    # "latest" for routine polling calls, "archive" for one-time historical backfill calls.
    call_type: Mapped[str] = mapped_column(String(16), nullable=False, default="latest")
    target_company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("target_companies.id", ondelete="SET NULL"), nullable=True
    )
    # Credit/request cost of the call as reported by the provider (NewsData.io's response
    # includes a per-call credit cost; NewsAPI.org/Google News RSS default to 1).
    requests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    articles_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
