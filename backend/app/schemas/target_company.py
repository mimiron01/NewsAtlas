import uuid

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

    model_config = {"from_attributes": True}
