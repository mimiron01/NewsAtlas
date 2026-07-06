import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.article import ArticleSource


class NewsSourceUsageEntry(BaseModel):
    call_type: str
    target_company_name: str | None
    requests_used: int
    articles_returned: int
    created_at: datetime


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
