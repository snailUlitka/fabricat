"""Application-wide configuration loaded from the environment."""

from __future__ import annotations

from functools import cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Centralized settings for the Fabricat backend service."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://fabricat:fabricat@database:5432/fabricat"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    auth_secret_key: str


@cache
def get_settings() -> BackendSettings:
    """Return the cached settings instance."""

    return BackendSettings()


settings = get_settings()

__all__ = ["BackendSettings", "get_settings", "settings"]
