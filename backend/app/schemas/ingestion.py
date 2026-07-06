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
