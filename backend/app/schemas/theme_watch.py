import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import (
    validate_news_sources,
    validate_source_allowlist,
    validate_term_list,
)


def _normalize_country(value: str | None) -> str | None:
    """Empty string means "inherit the workspace default", same as never having set one —
    normalized to None so the two spellings can't diverge in the DB. Google's `gl`
    parameter expects an uppercase ISO-3166 country code."""
    if value is None:
        return None
    value = value.strip().upper()
    if not value:
        return None
    if not value.isalpha() or not 2 <= len(value) <= 8:
        raise ValueError("Country must be a 2-letter country code, e.g. DE or US")
    return value


def _normalize_language(value: str | None) -> str | None:
    """Same inherit-on-empty rule as _normalize_country. Google's `hl` expects a lowercase
    language code, optionally region-qualified (e.g. "de", "pt-BR" → stored lowercase)."""
    if value is None:
        return None
    value = value.strip().lower()
    if not value:
        return None
    if not value.replace("-", "").isalpha() or not 2 <= len(value) <= 8:
        raise ValueError("Language must be a 2-letter language code, e.g. de or en")
    return value


class ThemeWatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    query_terms: list[str] = Field(min_length=1, max_length=20)
    industry: str | None = Field(default=None, max_length=255)
    # None = inherit the workspace allowlist; [] = explicitly unrestricted; non-empty
    # replaces it (docs/google-news-quality-planning.html §7.6).
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)
    google_news_source_denylist: list[str] = Field(default_factory=list, max_length=50)
    exclusion_terms: list[str] = Field(default_factory=list)
    # None = inherit workspace_settings.theme_news_sources (§11.3).
    news_sources: list[str] | None = None
    # None/"" = inherit the workspace-wide Google News edition (see ThemeWatch model).
    google_news_country: str | None = Field(default=None, max_length=8)
    google_news_language: str | None = Field(default=None, max_length=8)

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("google_news_source_allowlist", "google_news_source_denylist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_source_allowlist(value)

    @field_validator("exclusion_terms")
    @classmethod
    def _exclusions_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("news_sources")
    @classmethod
    def _news_sources_valid(cls, value: list[str] | None) -> list[str] | None:
        return validate_news_sources(value)

    @field_validator("google_news_country")
    @classmethod
    def _country_valid(cls, value: str | None) -> str | None:
        return _normalize_country(value)

    @field_validator("google_news_language")
    @classmethod
    def _language_valid(cls, value: str | None) -> str | None:
        return _normalize_language(value)


class ThemeWatchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    query_terms: list[str] | None = Field(default=None, min_length=1, max_length=20)
    industry: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)
    google_news_source_denylist: list[str] | None = Field(default=None, max_length=50)
    exclusion_terms: list[str] | None = None
    news_sources: list[str] | None = None
    google_news_country: str | None = Field(default=None, max_length=8)
    google_news_language: str | None = Field(default=None, max_length=8)

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("google_news_source_allowlist", "google_news_source_denylist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_source_allowlist(value)

    @field_validator("exclusion_terms")
    @classmethod
    def _exclusions_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("news_sources")
    @classmethod
    def _news_sources_valid(cls, value: list[str] | None) -> list[str] | None:
        return validate_news_sources(value)

    @field_validator("google_news_country")
    @classmethod
    def _country_valid(cls, value: str | None) -> str | None:
        return _normalize_country(value)

    @field_validator("google_news_language")
    @classmethod
    def _language_valid(cls, value: str | None) -> str | None:
        return _normalize_language(value)


class ThemeWatchResponse(BaseModel):
    id: uuid.UUID
    name: str
    query_terms: list[str]
    industry: str | None
    is_active: bool
    google_news_source_allowlist: list[str] | None
    google_news_source_denylist: list[str] = []
    exclusion_terms: list[str] = []
    news_sources: list[str] | None = None
    # None = inheriting the workspace-wide Google News edition; the frontend renders that
    # as an explicit "workspace default" choice rather than a blank field.
    google_news_country: str | None = None
    google_news_language: str | None = None
    # Drives the per-theme fetch button's cooldown countdown, so the button can be disabled
    # with a live timer instead of letting the click fail with a 429.
    last_manual_run_at: datetime | None = None
    created_by: uuid.UUID | None = None
    # Per-follow fields: None when the requester (an admin using ?scope=all) doesn't
    # themselves follow this theme.
    is_muted: bool | None = None
    follower_count: int

    model_config = {"from_attributes": True}


class ThemeFollowerResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    is_muted: bool
    assigned_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
