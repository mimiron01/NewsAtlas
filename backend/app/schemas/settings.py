import uuid
from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceSettingsResponse(BaseModel):
    id: uuid.UUID
    company_name: str
    offering_description: str
    digest_send_time: str
    ingestion_interval_hours: int

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

    newsdata_enabled: bool
    newsdata_api_key_configured: bool
    newsdata_api_key_source: Literal["workspace", "environment", "unset"]
    newsdata_api_key_last4: str | None
    newsdata_full_content_enabled: bool
    newsdata_use_native_dedupe: bool
    newsdata_backfill_days: int
    newsdata_max_requests_per_day: int
    newsdata_max_requests_per_minute: int

    model_config = {"from_attributes": True}


class WorkspaceSettingsUpdate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    offering_description: str = Field(default="", max_length=8000)
    digest_send_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    ingestion_interval_hours: int = Field(ge=1, le=48)

    mistral_model: str = Field(min_length=1, max_length=100)
    mistral_triage_model: str = Field(min_length=1, max_length=100)
    mistral_embed_model: str = Field(min_length=1, max_length=100)
    mistral_triage_enabled: bool = True
    mistral_dedupe_similarity_threshold: float = Field(ge=0.0, le=1.0)
    # None = leave the current key (workspace override or env fallback) untouched.
    # "" = explicitly clear the in-app override, reverting to the env-var key if any.
    # Any other value = set/replace the in-app override.
    mistral_api_key: str | None = Field(default=None, max_length=200)

    # --- News sources ---
    newsapi_enabled: bool = True
    newsapi_max_requests_per_day: int = Field(ge=1, le=100_000)

    google_news_rss_enabled: bool = False
    google_news_rss_country: str = Field(min_length=2, max_length=8)
    google_news_rss_language: str = Field(min_length=2, max_length=8)
    google_news_rss_max_requests_per_minute: int = Field(ge=1, le=1000)

    newsdata_enabled: bool = False
    # Same set/clear/leave-unchanged convention as mistral_api_key.
    newsdata_api_key: str | None = Field(default=None, max_length=200)
    newsdata_full_content_enabled: bool = True
    newsdata_use_native_dedupe: bool = True
    newsdata_backfill_days: int = Field(ge=0, le=1825)
    newsdata_max_requests_per_day: int = Field(ge=1, le=100_000)
    newsdata_max_requests_per_minute: int = Field(ge=1, le=1000)
