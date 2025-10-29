"""Database session management utilities."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from fabricat_backend.settings import BackendSettings, get_settings


class DatabaseService:
    """Wraps SQLAlchemy engine and session factory."""

    def __init__(
        self,
        url: str | None = None,
        *,
        settings: BackendSettings | None = None,
    ) -> None:
        config = settings or get_settings()
        self._engine = create_engine(url or config.database_url, future=True)
        self._session_factory = sessionmaker(
            bind=self._engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )

    @property
    def engine(self):  # type: ignore[override]
        """Expose the SQLAlchemy engine."""

        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Provide a transactional session scope."""

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


database_service = DatabaseService()
