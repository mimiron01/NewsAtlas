import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.common_validators import validate_source_allowlist, validate_term_list


class TopicTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    category: str | None
    language: str | None
    query_terms: list[str]
    exclude_terms: list[str]
    suggested_source_allowlist: list[str]
    is_active: bool
    sort_order: int

    model_config = {"from_attributes": True}


class TopicTemplateCreate(BaseModel):
    """Admin-only — see docs/topics-ux-improvements-planning.html §2.1: templates are
    admin-managed rows, not a hardcoded list, specifically so §2.4's performance data can
    drive edits without a deploy."""

    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=500)
    category: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=8)
    query_terms: list[str] = Field(min_length=1, max_length=20)
    exclude_terms: list[str] = Field(default_factory=list, max_length=20)
    suggested_source_allowlist: list[str] = Field(default_factory=list, max_length=50)
    sort_order: int = 0

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("exclude_terms")
    @classmethod
    def _exclude_terms_valid(cls, value: list[str]) -> list[str]:
        return validate_term_list(value)

    @field_validator("suggested_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str]) -> list[str]:
        return validate_source_allowlist(value)


class TopicTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)
    language: str | None = Field(default=None, max_length=8)
    query_terms: list[str] | None = Field(default=None, min_length=1, max_length=20)
    exclude_terms: list[str] | None = Field(default=None, max_length=20)
    suggested_source_allowlist: list[str] | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("query_terms")
    @classmethod
    def _query_terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("exclude_terms")
    @classmethod
    def _exclude_terms_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_term_list(value)

    @field_validator("suggested_source_allowlist")
    @classmethod
    def _allowlist_valid(cls, value: list[str] | None) -> list[str] | None:
        return value if value is None else validate_source_allowlist(value)


class TopicTemplateApplyRequest(BaseModel):
    """Body for POST /topic-templates/{id}/apply — every field is an optional override of
    the template's own value, so a user can tweak (e.g. add a workspace-specific term)
    before committing rather than taking the template as-is. Still goes through the same
    duplicate-name confirmation as a manual create (§1.4) via confirm_merge."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    query_terms: list[str] | None = Field(default=None, min_length=1, max_length=20)
    exclude_terms: list[str] | None = Field(default=None, max_length=20)
    industry: str | None = Field(default=None, max_length=255)
    google_news_source_allowlist: list[str] | None = Field(default=None, max_length=50)
    confirm_merge: bool = False

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


class SuggestedTopicResponse(BaseModel):
    name: str
    query_terms: list[str]
    exclude_terms: list[str]
    rationale: str
    based_on_template_id: uuid.UUID | None = None
    based_on_template_name: str | None = None


class TopicTemplatePerformanceResponse(BaseModel):
    """Admin-only aggregate over every ThemeWatch created from this template, across the
    workspace — see docs/topics-ux-improvements-planning.html §2.4."""

    template_id: uuid.UUID
    adoption_count: int
    matches_total: int
    dismiss_rate: float | None = None
    avg_relevance_score: float | None = None
