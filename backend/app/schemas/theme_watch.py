import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import validate_source_allowlist, validate_term_list


class ThemeWatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    query_terms: list[str] = Field(min_length=1, max_length=20)
    industry: str | None = Field(default=None, max_length=255)
    google_news_source_allowlist: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("google_news_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str]) -> list[str]:
        return validate_source_allowlist(value)


class ThemeWatchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    query_terms: list[str] | None = Field(default=None, min_length=1, max_length=20)
    industry: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("google_news_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_source_allowlist(value)


class ThemeWatchResponse(BaseModel):
    id: uuid.UUID
    name: str
    query_terms: list[str]
    industry: str | None
    is_active: bool
    google_news_source_allowlist: list[str]
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
