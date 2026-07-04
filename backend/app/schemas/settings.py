import uuid

from pydantic import BaseModel, Field


class WorkspaceSettingsResponse(BaseModel):
    id: uuid.UUID
    company_name: str
    offering_description: str
    digest_send_time: str
    ingestion_interval_hours: int

    model_config = {"from_attributes": True}


class WorkspaceSettingsUpdate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    offering_description: str = Field(default="", max_length=8000)
    digest_send_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    ingestion_interval_hours: int = Field(ge=1, le=48)
