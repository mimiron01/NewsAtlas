import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.signal import SignalStatus


class SignalResponse(BaseModel):
    id: uuid.UUID
    status: SignalStatus
    summary: str
    business_relevance: str
    outreach_snippet: str
    created_at: datetime
    article_id: uuid.UUID
    article_title: str
    article_url: str
    article_source_name: str
    article_published_at: datetime | None
    target_company_id: uuid.UUID
    target_company_name: str


class SignalStatusUpdate(BaseModel):
    status: SignalStatus
