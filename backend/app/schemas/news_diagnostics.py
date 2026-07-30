from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import (
    validate_locale_code,
    validate_source_allowlist,
    validate_term_list,
)


class QueryPreviewRequest(BaseModel):
    """A provisional configuration to try, not a stored one — nothing here is persisted.

    Either name (+ aliases/context terms), for a company-shaped query, or query_terms, for
    a theme-shaped one. Sending both prefers query_terms.
    """

    name: str | None = Field(default=None, max_length=255)
    aliases: list[str] = Field(default_factory=list)
    context_terms: list[str] = Field(default_factory=list)
    exclusion_terms: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    # None inherits the workspace allowlist, matching how a stored entity resolves it.
    source_allowlist: list[str] | None = Field(default=None, max_length=50)
    source_denylist: list[str] = Field(default_factory=list, max_length=50)
    country: str | None = Field(default=None, max_length=8)
    language: str | None = Field(default=None, max_length=8)
    require_name_in_title: bool = False
    # None = use the workspace setting.
    time_operator_enabled: bool | None = None
    lookback_hours: int = Field(default=24, ge=1, le=168)

    @field_validator("aliases", "context_terms", "exclusion_terms", "query_terms")
    @classmethod
    def _terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("source_allowlist", "source_denylist")
    @classmethod
    def _domains_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_source_allowlist(value)

    @field_validator("country")
    @classmethod
    def _country_valid(cls, value: str | None) -> str | None:
        return validate_locale_code(value, upper=True)

    @field_validator("language")
    @classmethod
    def _language_valid(cls, value: str | None) -> str | None:
        return validate_locale_code(value, upper=False)


class QueryPreviewEntry(BaseModel):
    title: str
    source_name: str
    url: str
    published_at: datetime | None
    # "kept" or the stage that would have discarded it.
    outcome: str


class QueryPreviewResponse(BaseModel):
    query_text: str
    word_count: int
    max_words: int
    # True when the word budget forced terms out of the query — the thing Google itself
    # does silently.
    truncated: bool
    country: str
    language: str
    entries_raw: int
    drop_counts: dict[str, int]
    entries: list[QueryPreviewEntry]


class DomainPrecisionStat(BaseModel):
    source_name: str
    articles: int
    signals_kept: int
    dismissed: int
    triaged_out: int
    duplicates: int
    # (triaged_out + dismissed) / articles judged, excluding duplicates.
    waste_ratio: float
    denylist_suggested: bool
