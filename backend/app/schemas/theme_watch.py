import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import validate_source_allowlist, validate_term_list


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
    exclude_terms: list[str] = Field(default_factory=list, max_length=20)
    industry: str | None = Field(default=None, max_length=255)
    google_news_source_allowlist: list[str] = Field(default_factory=list, max_length=50)
    # None/"" = inherit the workspace-wide Google News edition (see ThemeWatch model).
    google_news_country: str | None = Field(default=None, max_length=8)
    google_news_language: str | None = Field(default=None, max_length=8)
    # When a topic with this name already exists (case-insensitive), the create endpoint
    # normally 409s with the existing topic's terms rather than silently merging (see
    # docs/topics-ux-improvements-planning.html §1.4) — set true to proceed anyway and
    # follow the existing topic, same as re-clicking "Follow existing topic" in the UI.
    confirm_merge: bool = False

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("exclude_terms")
    @classmethod
    def _exclude_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("google_news_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str]) -> list[str]:
        return validate_source_allowlist(value)

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
    exclude_terms: list[str] | None = Field(default=None, max_length=20)
    industry: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)
    google_news_country: str | None = Field(default=None, max_length=8)
    google_news_language: str | None = Field(default=None, max_length=8)

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("exclude_terms")
    @classmethod
    def _exclude_terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("google_news_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_source_allowlist(value)

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
    exclude_terms: list[str] = []
    industry: str | None
    is_active: bool
    google_news_source_allowlist: list[str]
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


class ThemeQueryPreviewRequest(BaseModel):
    """Body for POST /theme-watches/preview — see
    docs/topics-ux-improvements-planning.html §1.3. Deliberately takes the raw fields
    rather than a theme_watch_id so it works before a topic has ever been saved (live,
    debounced preview while the create form is being filled in)."""

    query_terms: list[str] = Field(min_length=1, max_length=20)
    exclude_terms: list[str] = Field(default_factory=list, max_length=20)
    google_news_source_allowlist: list[str] = Field(default_factory=list, max_length=50)
    google_news_country: str | None = Field(default=None, max_length=8)
    google_news_language: str | None = Field(default=None, max_length=8)

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("exclude_terms")
    @classmethod
    def _exclude_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("google_news_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str]) -> list[str]:
        return validate_source_allowlist(value)

    @field_validator("google_news_country")
    @classmethod
    def _country_valid(cls, value: str | None) -> str | None:
        return _normalize_country(value)

    @field_validator("google_news_language")
    @classmethod
    def _language_valid(cls, value: str | None) -> str | None:
        return _normalize_language(value)


class ThemeQueryPreviewResponse(BaseModel):
    article_count: int
    sample_headlines: list[str]


class ThemeWatchStatsResponse(BaseModel):
    """Per-topic health snapshot — see docs/topics-ux-improvements-planning.html §3.2."""

    matches_last_7d: int
    matches_last_30d: int
    dismiss_rate_30d: float | None = None
    avg_relevance_score_30d: float | None = None
    last_match_at: datetime | None = None

    model_config = {"from_attributes": True}
