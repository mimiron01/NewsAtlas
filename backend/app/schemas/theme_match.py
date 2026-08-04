import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.article import ArticleSource
from app.models.signal import SignalStatus


class ThemeMatchResponse(BaseModel):
    id: uuid.UUID
    status: SignalStatus
    summary: str | None
    business_relevance: str | None
    supporting_quote: str | None
    relevance_score: int | None
    signal_type: str | None
    confidence: str | None
    entities: dict[str, Any] | None
    fetched_at: datetime
    title: str
    url: str
    source_name: str
    published_at: datetime | None
    source: ArticleSource
    headline_only: bool
    theme_watch_id: uuid.UUID
    theme_watch_name: str
    # What the AI extraction pass identified, if anything — see
    # docs/theme-search-planning.html §4.3. matched_target_company_id/name are set once
    # that name resolves to an existing, already-tracked TargetCompany (automatically,
    # no user action); "Track this company" is only offered when extracted_company_name
    # is set but matched_target_company_id isn't.
    extracted_company_name: str | None
    matched_target_company_id: uuid.UUID | None
    matched_target_company_name: str | None
    is_favorited: bool = False


class ThemeMatchStatusUpdate(BaseModel):
    status: SignalStatus
