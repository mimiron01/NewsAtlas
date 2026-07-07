import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SignalTodoCreate(BaseModel):
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped


class SignalTodoUpdate(BaseModel):
    text: str | None = Field(default=None, min_length=1, max_length=1000)
    is_done: bool | None = None

    @field_validator("text")
    @classmethod
    def _strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        stripped = value.strip()
        if not stripped:
            raise ValueError("text must not be blank")
        return stripped


class SignalTodoResponse(BaseModel):
    id: uuid.UUID
    signal_id: uuid.UUID
    text: str
    is_done: bool
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SignalTodoWithContext(SignalTodoResponse):
    article_title: str
    target_company_name: str
