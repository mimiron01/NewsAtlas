import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import validate_source_allowlist, validate_term_list


def _validate_keywords(value: list[str]) -> list[str]:
    return validate_term_list(value)


def _validate_source_allowlist(value: list[str]) -> list[str]:
    return validate_source_allowlist(value)


class TargetCompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list)
    industry: str | None = Field(default=None, max_length=255)
    google_news_source_allowlist: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("keywords")
    @classmethod
    def _keywords_valid(cls, value: list[str]) -> list[str]:
        return _validate_keywords(value)

    @field_validator("google_news_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str]) -> list[str]:
        return _validate_source_allowlist(value)


class TargetCompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    keywords: list[str] | None = None
    industry: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)

    @field_validator("keywords")
    @classmethod
    def _keywords_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else _validate_keywords(value)

    @field_validator("google_news_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else _validate_source_allowlist(value)


class TargetCompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    keywords: list[str]
    industry: str | None
    is_active: bool
    google_news_source_allowlist: list[str]
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
