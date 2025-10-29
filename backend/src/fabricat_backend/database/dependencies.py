"""FastAPI dependencies for database access."""

from collections.abc import Iterator
from functools import cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from fabricat_backend.database.service import DatabaseService
from fabricat_backend.settings import BackendSettings, get_settings

SettingsDep = Annotated[BackendSettings, Depends(get_settings)]


@cache
def _build_database_service(database_url: str) -> DatabaseService:
    """Create a cached :class:`DatabaseService` for the given connection string."""
    return DatabaseService(database_url)


def get_database(settings: SettingsDep) -> DatabaseService:
    """Return the cached database service instance."""
    return _build_database_service(settings.database_url)


def get_session(
    db: Annotated[DatabaseService, Depends(get_database)],
) -> Iterator[Session]:
    """Yield a SQLAlchemy session managed by :class:`DatabaseService`."""
    with db.session() as session:
        yield session
