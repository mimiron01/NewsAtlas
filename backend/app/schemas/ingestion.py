import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IngestionRunResult(BaseModel):
    target_companies_processed: int
    # True if the run stopped early because an admin requested cancellation (see
    # IngestionProgress.should_cancel) rather than running to completion.
    cancelled: bool = False
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
    # ThemeWatch results (see docs/theme-search-planning.html §5) — a ThemeMatch isn't a
    # Signal, so it gets its own counter rather than folding into signals_created;
    # theme-path duplicates/triaged-out articles do fold into duplicates_skipped/
    # triaged_out above, since those are the same kind of event regardless of path.
    theme_matches_created: int = 0
    themes_processed: int = 0
    themes_total: int = 0


class IngestionRunStatusResponse(BaseModel):
    """Snapshot of one ingestion_runs row — both the live progress a running pipeline is
    making (companies/articles counters, current step) and, once finished, the same
    counts as IngestionRunResult plus bookkeeping (trigger, timestamps, errors)."""

    id: uuid.UUID
    status: str
    cancel_requested: bool
    trigger: str
    started_at: datetime
    finished_at: datetime | None
    progress_percent: int

    # Set only for a single-theme run started from the Themes page; None for an ordinary
    # full run over every company and theme.
    theme_watch_id: uuid.UUID | None = None
    # Set only for a run scoped to one or more companies from the "My companies" table's
    # per-row or multi-select "fetch now" action; None otherwise.
    target_company_ids: list[uuid.UUID] | None = None

    current_step: str | None
    current_company_name: str | None
    current_theme_name: str | None = None
    companies_total: int
    companies_processed: int
    # Reused by the theme phase for its own per-match progress (the field name predates
    # themes; both phases mean "items in the batch currently being summarized").
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
    # themes_total/themes_processed are live (updated as the theme loop runs, same as the
    # company counters above); theme_matches_created settles once the run finishes.
    themes_total: int = 0
    themes_processed: int = 0
    theme_matches_created: int = 0

    model_config = {"from_attributes": True}
