import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.article import ArticleSource
from app.models.signal import SignalStatus


class SignalResponse(BaseModel):
    id: uuid.UUID
    status: SignalStatus
    summary: str
    business_relevance: str
    supporting_quote: str
    outreach_snippet_email: str
    outreach_snippet_linkedin: str
    outreach_call_opener: str
    relevance_score: int | None
    signal_type: str | None
    confidence: str | None
    entities: dict[str, Any] | None
    created_at: datetime
    article_id: uuid.UUID
    article_title: str
    article_url: str
    article_source_name: str
    article_published_at: datetime | None
    # Which ingestion provider surfaced the underlying article, plus NewsData.io's own
    # sentiment/AI-tag output when that source captured it (see
    # docs/news-source-expansion-planning.html §10.3) — auxiliary metadata shown
    # alongside, not merged into, Mistral's own confidence/signal_type/entities above.
    article_source: ArticleSource
    article_external_sentiment: str | None
    article_external_tags: list[str] | None
    # True when the underlying article came from a source (Google News RSS) whose
    # description field is never real content, only a repeat of the title — shown to
    # end users as a "Limited detail" badge so they know to click through before trusting
    # supporting_quote/business_relevance the same way they would for a full-snippet source.
    headline_only: bool
    target_company_id: uuid.UUID
    target_company_name: str
    is_favorited: bool
    open_todo_count: int


class SignalStatusUpdate(BaseModel):
    status: SignalStatus
