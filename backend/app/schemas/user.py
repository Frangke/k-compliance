from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class UserCreate(BaseModel):
    username: str
    password: str
    name: str
    email: str
    role: Literal["cpo", "security_officer", "privacy_handler", "auditor"]
    department: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    role: Literal["cpo", "security_officer", "privacy_handler", "auditor"] | None = None
    department: str | None = None
    is_active: bool | None = None


class AdminPasswordReset(BaseModel):
    new_password: str


class UserResponse(BaseModel):
    id: int
    username: str
    name: str
    email: str
    role: str
    department: str | None
    is_active: bool
    last_login_at: datetime | None
    password_changed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int


class TokenPayload(BaseModel):
    sub: int
    role: str
    exp: datetime
