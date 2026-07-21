import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.services.news_query import is_valid_source_hostname

# A company can be a "Tier 1 supplier"-style multi-word phrase — 100 chars comfortably
# covers legitimate use while capping the cost/DB-bloat/prompt-injection surface a huge
# array of huge strings would otherwise open (see docs/v1-release-roadmap.html §5).
_MAX_KEYWORDS = 20
_MAX_KEYWORD_LENGTH = 100


def _validate_keywords(value: list[str]) -> list[str]:
    if len(value) > _MAX_KEYWORDS:
        raise ValueError(f"at most {_MAX_KEYWORDS} keywords are allowed")
    for keyword in value:
        if len(keyword) > _MAX_KEYWORD_LENGTH:
            raise ValueError(f"each keyword must be at most {_MAX_KEYWORD_LENGTH} characters")
    return value


def _validate_source_allowlist(value: list[str]) -> list[str]:
    cleaned = [domain.strip().lower() for domain in value]
    for domain in cleaned:
        if not is_valid_source_hostname(domain):
            raise ValueError(f"{domain!r} is not a valid bare hostname (no scheme, no path)")
    return cleaned


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
