import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.article import ArticleSource


class SkippedArticleResponse(BaseModel):
    """An article the ingestion pipeline fetched but did not turn into a Signal — the
    review queue behind the "why is everything low relevance" question (see
    services/ingestion.py's triage/dedupe gates)."""

    id: uuid.UUID
    title: str
    url: str
    source_name: str
    source: ArticleSource
    published_at: datetime | None
    fetched_at: datetime
    skip_reason: str
    triage_reason: str | None
    target_company_id: uuid.UUID
    target_company_name: str
