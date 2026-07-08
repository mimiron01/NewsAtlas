import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IngestionRunResult(BaseModel):
    target_companies_processed: int
    articles_fetched: int
    articles_new: int
    signals_created: int
    duplicates_skipped: int = 0
    triaged_out: int = 0
    # Articles fetched per source (e.g. {"newsapi": 12, "google_news_rss": 4}) — shows
    # which providers are actually contributing once more than one can be enabled.
    by_source: dict[str, int] = Field(default_factory=dict)
    # Target companies skipped per source this run because its configured rate limit was
    # already reached before the call would have been made (no request was sent).
    rate_limited: dict[str, int] = Field(default_factory=dict)
    errors: list[str]


class IngestionRunStatusResponse(BaseModel):
    """Snapshot of one ingestion_runs row — both the live progress a running pipeline is
    making (companies/articles counters, current step) and, once finished, the same
    counts as IngestionRunResult plus bookkeeping (trigger, timestamps, errors)."""

    id: uuid.UUID
    status: str
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    progress_percent: int

    current_step: str | None
    current_company_name: str | None
    companies_total: int
    companies_processed: int
    articles_total_this_company: int
    articles_processed_this_company: int

    articles_fetched: int
    articles_new: int
    signals_created: int
    duplicates_skipped: int
    triaged_out: int
    by_source: dict[str, int] = Field(default_factory=dict)
    rate_limited: dict[str, int] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    fatal_error: str | None

    model_config = {"from_attributes": True}
