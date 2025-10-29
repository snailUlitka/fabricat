"""Database configuration helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_DATABASE_URL = "postgresql+psycopg://fabricat:fabricat@localhost:5432/fabricat"


@dataclass(slots=True)
class DatabaseSettings:
    """Settings container for database connectivity."""

    url: str = DEFAULT_DATABASE_URL

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        """Load settings from environment variables."""

        return cls(url=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))


settings = DatabaseSettings.from_env()
