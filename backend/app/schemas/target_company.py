import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import (
    validate_locale_code,
    validate_source_allowlist,
    validate_term_list,
)


def _validate_keywords(value: list[str]) -> list[str]:
    return validate_term_list(value)


def _validate_source_allowlist(value: list[str]) -> list[str]:
    return validate_source_allowlist(value)


class TargetCompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    # Term roles, see models/target_company.py. `keywords` stays accepted as a legacy
    # alias for context_terms — the role it actually played in the query — so existing
    # clients and the CSV importer keep working; it's ignored when context_terms is given
    # explicitly, and the stored column is always re-derived from the split fields.
    keywords: list[str] | None = None
    aliases: list[str] = Field(default_factory=list)
    context_terms: list[str] = Field(default_factory=list)
    exclude_terms: list[str] = Field(default_factory=list)
    industry: str | None = Field(default=None, max_length=255)
    # None = inherit the workspace allowlist; [] = explicitly unrestricted; a non-empty
    # list replaces the workspace list (see docs/google-news-quality-planning.html §7.6).
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)
    google_news_source_denylist: list[str] = Field(default_factory=list, max_length=50)
    google_news_country: str | None = Field(default=None, max_length=8)
    google_news_language: str | None = Field(default=None, max_length=8)
    google_news_require_name_in_title: bool = False

    @field_validator("keywords", "aliases", "context_terms", "exclude_terms")
    @classmethod
    def _terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else _validate_keywords(value)

    @field_validator("google_news_source_allowlist", "google_news_source_denylist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else _validate_source_allowlist(value)

    @field_validator("google_news_country")
    @classmethod
    def _country_valid(cls, value: str | None) -> str | None:
        return validate_locale_code(value, upper=True)

    @field_validator("google_news_language")
    @classmethod
    def _language_valid(cls, value: str | None) -> str | None:
        return validate_locale_code(value, upper=False)


class TargetCompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    # Legacy alias for context_terms, see TargetCompanyCreate.
    keywords: list[str] | None = None
    aliases: list[str] | None = None
    context_terms: list[str] | None = None
    exclude_terms: list[str] | None = None
    industry: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    # None is ambiguous here in a way it isn't elsewhere on this model: it's both this
    # schema's "field not provided" sentinel and the allowlist's own "inherit the
    # workspace list" value. The route distinguishes them with model_fields_set — see
    # api/target_companies.py — so an explicit null really does revert to inheriting.
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)
    google_news_source_denylist: list[str] | None = Field(default=None, max_length=50)
    google_news_country: str | None = Field(default=None, max_length=8)
    google_news_language: str | None = Field(default=None, max_length=8)
    google_news_require_name_in_title: bool | None = None

    @field_validator("keywords", "aliases", "context_terms", "exclude_terms")
    @classmethod
    def _terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else _validate_keywords(value)

    @field_validator("google_news_source_allowlist", "google_news_source_denylist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else _validate_source_allowlist(value)

    @field_validator("google_news_country")
    @classmethod
    def _country_valid(cls, value: str | None) -> str | None:
        return validate_locale_code(value, upper=True)

    @field_validator("google_news_language")
    @classmethod
    def _language_valid(cls, value: str | None) -> str | None:
        return validate_locale_code(value, upper=False)


class TargetCompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    # Derived from aliases + context_terms and kept in the response because the CSV
    # import/export and existing clients still speak in terms of it.
    keywords: list[str]
    aliases: list[str]
    context_terms: list[str]
    exclude_terms: list[str]
    industry: str | None
    is_active: bool
    # None means "inheriting the workspace allowlist" — the frontend renders that as a
    # distinct state from an explicitly empty (unrestricted) list.
    google_news_source_allowlist: list[str] | None
    google_news_source_denylist: list[str]
    google_news_country: str | None = None
    google_news_language: str | None = None
    google_news_require_name_in_title: bool = False
    # None for a company created before created_by existed — treated the same as a
    # non-creator by the edit-permission check (see api/target_companies.py).
    created_by: uuid.UUID | None = None
    # Per-follow fields: None when the requester (an admin using ?scope=all) doesn't
    # themselves follow this company.
    is_muted: bool | None = None
    follower_count: int
    # Set once a NewsData.io historical archive backfill has run for this company; None
    # means either backfill isn't configured/enabled, or it hasn't completed yet — the
    # frontend uses this to show a "backfilling..." indicator (see
    # docs/news-source-expansion-planning.html §10.4).
    backfilled_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompanyFollowerResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    is_muted: bool
    assigned_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TargetCompanyImportSkipped(BaseModel):
    row: int
    name: str
    reason: str


class TargetCompanyImportError(BaseModel):
    row: int
    reason: str


class TargetCompanyImportResult(BaseModel):
    created: list[TargetCompanyResponse]
    skipped: list[TargetCompanyImportSkipped]
    errors: list[TargetCompanyImportError]


class TargetCompanyBulkDeleteRequest(BaseModel):
    target_company_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


class TargetCompanyBulkDeleteResult(BaseModel):
    deleted: int
    not_found: int
