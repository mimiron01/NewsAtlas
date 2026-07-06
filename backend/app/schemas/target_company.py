import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TargetCompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    keywords: list[str] = Field(default_factory=list)
    industry: str | None = None


class TargetCompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    keywords: list[str] | None = None
    industry: str | None = None
    is_active: bool | None = None


class TargetCompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    keywords: list[str]
    industry: str | None
    is_active: bool
    # Per-follow fields: None when the requester (an admin using ?scope=all) doesn't
    # themselves follow this company.
    is_muted: bool | None = None
    follower_count: int

    model_config = {"from_attributes": True}


class CompanyFollowerResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    is_muted: bool
    assigned_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
