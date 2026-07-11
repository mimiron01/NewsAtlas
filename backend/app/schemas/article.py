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
    # True for Google News RSS articles: that feed's description field is never real
    # content, only a repeat of the title, so a skip on one of these is judged from the
    # headline alone (see services/ingestion.py's _is_headline_only).
    headline_only: bool
    target_company_id: uuid.UUID
    target_company_name: str
