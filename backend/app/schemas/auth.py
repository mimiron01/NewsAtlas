import uuid

from pydantic import BaseModel, EmailStr, Field


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

    model_config = {"from_attributes": True}
