import uuid

from sqlalchemy import Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    # Set instead of target_company_id for a theme's fetch — the two are mutually
    # exclusive, since a call is made either on behalf of one company or one theme. Without
    # this, theme fetches logged target_company_id=None and the Settings usage view could
    # only show them as anonymous rows with no attribution at all.
    theme_watch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("theme_watches.id", ondelete="SET NULL"), nullable=True
    )
    # Credit/request cost of the call as reported by the provider (NewsData.io's response
    # includes a per-call credit cost; NewsAPI.org/Google News RSS default to 1).
    requests_used: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    articles_returned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Query/funnel diagnostics (see docs/google-news-quality-planning.html §5) ---
    # The `q=` value actually sent, pre-encoding. Without this there is no way to answer
    # "why did this company get bad results this run" after the fact — the query is built
    # from a dozen inputs (name, aliases, context terms, exclusions, both allowlists, the
    # time operator) and reconstructing it from those inputs later is guesswork.
    # NULL for providers that don't build a query string of their own.
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Entries the provider returned *before* any client-side filtering. Deliberately
    # distinct from articles_returned, which keeps its existing post-filter meaning — the
    # gap between the two is exactly what drop_counts explains.
    articles_raw: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # One key per pipeline stage that discarded a candidate, e.g.
    # {"stale": 41, "unsafe_url": 0, "not_grounded": 12, "url_duplicate": 6, "over_cap": 22}.
    # JSONB rather than columns because the stage list is expected to change as the
    # pipeline does, and these are read for diagnosis, never joined or filtered on.
    drop_counts: Mapped[dict[str, int] | None] = mapped_column(JSONB, nullable=True)
