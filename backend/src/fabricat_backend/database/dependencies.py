"""FastAPI dependencies for database access."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlalchemy.orm import Session

from fabricat_backend.database.service import DatabaseService, database_service


def get_database() -> DatabaseService:
    """Return the shared database service instance."""

    return database_service


def get_session(db: DatabaseService = Depends(get_database)) -> Iterator[Session]:
    """Yield a SQLAlchemy session managed by :class:`DatabaseService`."""

    with db.session() as session:
        yield session
