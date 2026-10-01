from __future__ import annotations

from datetime import datetime
import re

from pydantic import BaseModel, Field, field_validator


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_\-]+$")
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, min_length=1, max_length=40)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("请输入有效邮箱")
        return normalized


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class UpdateAccountRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=40)


class AuthUser(BaseModel):
    id: str
    username: str
    email: str
    display_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    user: AuthUser
