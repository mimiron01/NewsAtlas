import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.article import ArticleSource


class NewsSourceUsageEntry(BaseModel):
    call_type: str
    # Mutually exclusive: a call is made on behalf of one company or one theme. Both None
    # for a pre-attribution historical row.
    target_company_name: str | None
    theme_watch_name: str | None = None
    requests_used: int
    articles_returned: int
    created_at: datetime
    # Phase 0 funnel diagnostics (docs/google-news-quality-planning.html §5.1). None on
    # rows written before the instrumentation existed, and on providers that build no
    # query string of their own.
    query_text: str | None = None
    articles_raw: int = 0
    drop_counts: dict[str, int] | None = None


class NewsSourceUsageStat(BaseModel):
    source: ArticleSource
    enabled: bool
    requests_last_minute: int
    requests_per_minute_limit: int | None
    requests_today: int
    requests_per_day_limit: int | None
    rate_limited_last_24h: int
    recent: list[NewsSourceUsageEntry]


class NewsUsageSummary(BaseModel):
    sources: list[NewsSourceUsageStat]


class BackfillTriggerResult(BaseModel):
    scheduled: bool
    message: str
    target_company_id: uuid.UUID
