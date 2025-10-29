"""Database session management utilities."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import Iterator


class DatabaseService:
    """Wraps SQLAlchemy engine and session factory."""

    def __init__(self, url: str) -> None:
        self._engine = create_engine(url, future=True)
        self._session_factory = sessionmaker(
            bind=self._engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )

    @property
    def engine(self) -> Engine:
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
