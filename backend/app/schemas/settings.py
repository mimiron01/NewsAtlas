import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import validate_news_sources
from app.services.news_query import is_valid_source_hostname


class PublicWorkspaceSettingsResponse(BaseModel):
    """Non-sensitive workspace capability flags, readable by any authenticated user (see
    GET /settings/public). Add a field here only if every user genuinely needs it to
    understand the app's behavior — this response deliberately carries no API-key status,
    no provider quotas, and no AI configuration."""

    google_news_rss_enabled: bool
    google_news_rss_country: str
    google_news_rss_language: str
    # True if newsapi/google_news_rss/newsdata is enabled — i.e. whether an ingestion run
    # can fetch anything at all right now. Companies check every enabled provider (not
    # just NewsAPI), so this has to be an OR across all three, not a proxy for any single
    # one (see docs/platform-usability-onboarding-review.html F1).
    any_news_source_enabled: bool
    # Not a workspace setting but a deployment constant (app config) — surfaced here
    # because the frontend renders the per-topic fetch cooldown as a live countdown, and
    # hardcoding the duration would silently drift from the server's real limit.
    manual_trigger_cooldown_seconds: int


class WorkspaceSettingsResponse(BaseModel):
    id: uuid.UUID
    company_name: str
    offering_description: str
    digest_send_time: str
    max_articles_per_company_per_run: int
    # The workspace standard UI/AI language; individual users may override it (see
    # UserResponse.preferred_language / UserResponse.workspace_main_language).
    main_language: Literal["en", "de"]

    mistral_model: str
    mistral_triage_model: str
    mistral_embed_model: str
    mistral_triage_enabled: bool
    mistral_dedupe_similarity_threshold: float
    # The raw key is never returned — only enough to show an admin which key is
    # currently effective and let them confirm they're looking at the right one.
    mistral_api_key_configured: bool
    mistral_api_key_source: Literal["workspace", "environment", "unset"]
    mistral_api_key_last4: str | None

    # --- News sources ---
    newsapi_enabled: bool
    newsapi_max_requests_per_day: int

    google_news_rss_enabled: bool
    google_news_rss_country: str
    google_news_rss_language: str
    google_news_rss_max_requests_per_minute: int
    # Workspace-wide default trusted domains for Google News RSS (see TargetCompany's
    # own per-company list, which unions with this rather than overriding it).
    google_news_source_allowlist: list[str]
    google_news_source_denylist: list[str]
    google_news_time_operator_enabled: bool
    google_news_query_strategy: str
    google_news_resolve_urls_enabled: bool
    google_news_fetch_snippets_enabled: bool
    max_enrichment_fetches_per_run: int
    max_enrichment_seconds_per_run: int
    theme_news_sources: list[str]
    max_theme_requests_per_run_per_source: int

    newsdata_enabled: bool
    newsdata_api_key_configured: bool
    newsdata_api_key_source: Literal["workspace", "environment", "unset"]
    newsdata_api_key_last4: str | None
    newsdata_full_content_enabled: bool
    newsdata_use_native_dedupe: bool
    newsdata_backfill_days: int
    newsdata_max_requests_per_day: int
    newsdata_max_requests_per_minute: int

    # --- Theme watch cost controls (see docs/theme-search-planning.html §9) ---
    max_articles_per_theme_per_run: int
    max_active_theme_watches: int
    # Enforced floor on a theme match's LLM relevance_score (1-5); matches below it are
    # skipped rather than shown (see WorkspaceSettings.theme_match_min_relevance_score).
    theme_match_min_relevance_score: int

    model_config = {"from_attributes": True}


class WorkspaceSettingsUpdate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    offering_description: str = Field(default="", max_length=8000)
    digest_send_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # 0 disables the cap (unlimited).
    max_articles_per_company_per_run: int = Field(ge=0, le=1000)
    main_language: Literal["en", "de"] = "en"

    mistral_model: str = Field(min_length=1, max_length=100)
    mistral_triage_model: str = Field(min_length=1, max_length=100)
    mistral_embed_model: str = Field(min_length=1, max_length=100)
    mistral_triage_enabled: bool = True
    mistral_dedupe_similarity_threshold: float = Field(ge=0.0, le=1.0)
    # None = leave the current key (workspace override or env fallback) untouched.
    # "" = explicitly clear the in-app override, reverting to the env-var key if any.
    # Any other value = set/replace the in-app override.
    mistral_api_key: str | None = Field(default=None, max_length=200)

    # --- News sources --- (defaults mirror WorkspaceSettings' column defaults, see there)
    newsapi_enabled: bool = False
    newsapi_max_requests_per_day: int = Field(ge=1, le=100_000)

    google_news_rss_enabled: bool = True
    google_news_rss_country: str = Field(min_length=2, max_length=8)
    google_news_rss_language: str = Field(min_length=2, max_length=8)
    google_news_rss_max_requests_per_minute: int = Field(ge=1, le=1000)
    google_news_source_allowlist: list[str] = Field(default_factory=list, max_length=50)
    google_news_source_denylist: list[str] = Field(default_factory=list, max_length=50)
    google_news_time_operator_enabled: bool = True
    google_news_query_strategy: str = "single"
    google_news_resolve_urls_enabled: bool = False
    google_news_fetch_snippets_enabled: bool = False
    max_enrichment_fetches_per_run: int = Field(default=50, ge=0, le=1000)
    max_enrichment_seconds_per_run: int = Field(default=120, ge=0, le=3600)
    theme_news_sources: list[str] = Field(default_factory=lambda: ["google_news_rss"])
    max_theme_requests_per_run_per_source: int = Field(default=0, ge=0, le=1000)

    newsdata_enabled: bool = False
    # Same set/clear/leave-unchanged convention as mistral_api_key.
    newsdata_api_key: str | None = Field(default=None, max_length=200)
    newsdata_full_content_enabled: bool = True
    newsdata_use_native_dedupe: bool = True
    newsdata_backfill_days: int = Field(ge=0, le=1825)
    newsdata_max_requests_per_day: int = Field(ge=1, le=100_000)
    newsdata_max_requests_per_minute: int = Field(ge=1, le=1000)

    # --- Theme watch cost controls (see docs/theme-search-planning.html §9) ---
    # 0 disables the cap (unlimited), matching max_articles_per_company_per_run.
    max_articles_per_theme_per_run: int = Field(ge=0, le=1000)
    # Not a "0 = off" toggle like the field above — this is a hard ceiling on how many
    # active theme watches a workspace can have at once, so it starts at 1.
    max_active_theme_watches: int = Field(ge=1, le=1000)
    # 1 = enforce nothing (every triaged-in match is shown, today's behaviour); the
    # prompt's own scale tops out at 5.
    theme_match_min_relevance_score: int = Field(default=3, ge=1, le=5)

    @field_validator("google_news_query_strategy")
    @classmethod
    def _query_strategy_valid(cls, value: str) -> str:
        if value not in ("single", "split"):
            raise ValueError('query strategy must be "single" or "split"')
        return value

    @field_validator("theme_news_sources")
    @classmethod
    def _theme_sources_valid(cls, value: list[str]) -> list[str]:
        return validate_news_sources(value) or []

    @field_validator("google_news_source_allowlist", "google_news_source_denylist")
    @classmethod
    def _validate_source_allowlist(cls, value: list[str]) -> list[str]:
        cleaned = [domain.strip().lower() for domain in value]
        for domain in cleaned:
            if not is_valid_source_hostname(domain):
                raise ValueError(
                    f"{domain!r} is not a valid bare hostname (no scheme, no path)"
                )
        return cleaned
