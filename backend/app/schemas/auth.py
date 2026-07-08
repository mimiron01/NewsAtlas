import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class SignupRequest(BaseModel):
    email: EmailStr
    # max_length matches bcrypt's 72-byte input limit (see core/security.py)
    password: str = Field(min_length=10, max_length=72)
    name: str = Field(min_length=1, max_length=255)
    invite_code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    role: UserRole
    # None = no personal override, follow workspace_main_language.
    preferred_language: Literal["en", "de"] | None
    # The workspace's current main_language, embedded here so any authenticated user
    # (not just admins, who alone can call GET /settings) can learn the standard
    # language without a separate endpoint.
    workspace_main_language: Literal["en", "de"]

    model_config = {"from_attributes": True}


class UpdateLanguagePreferenceRequest(BaseModel):
    preferred_language: Literal["en", "de"] | None = None
