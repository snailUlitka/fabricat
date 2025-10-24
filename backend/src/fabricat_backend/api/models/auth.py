"""Pydantic models for authentication endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fabricat_backend.shared import AvatarIcon


NICKNAME_PATTERN = r"^[A-Za-z0-9_]{3,32}$"
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 64


class UserResponse(BaseModel):
    """Public representation of a registered user."""

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id_: UUID = Field(alias="id")
    nickname: str
    icon: AvatarIcon
    created_at: datetime
    updated_at: datetime


class AuthTokenResponse(BaseModel):
    """Bearer token payload returned by the API."""

    access_token: str
    token_type: str = "bearer"


class UserRegisterRequest(BaseModel):
    """Payload for creating a new user."""

    nickname: str = Field(pattern=NICKNAME_PATTERN)
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )
    icon: AvatarIcon

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, value: str) -> str:
        if not value.strip():
            msg = "nickname must not be empty"
            raise ValueError(msg)
        return value

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isalpha() for char in value):
            msg = "password must contain at least one letter"
            raise ValueError(msg)
        if not any(char.isdigit() for char in value):
            msg = "password must contain at least one digit"
            raise ValueError(msg)
        return value


class UserRegisterResponse(BaseModel):
    """Response returned after a successful registration."""

    user: UserResponse
    token: AuthTokenResponse


class UserLoginRequest(BaseModel):
    """Payload for authenticating an existing user."""

    nickname: str = Field(pattern=NICKNAME_PATTERN)
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(char.isalpha() for char in value):
            msg = "password must contain at least one letter"
            raise ValueError(msg)
        if not any(char.isdigit() for char in value):
            msg = "password must contain at least one digit"
            raise ValueError(msg)
        return value


class UserLoginResponse(BaseModel):
    """Response returned after a successful authentication."""

    user: UserResponse
    token: AuthTokenResponse
