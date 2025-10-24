"""Repository helpers for working with users."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fabricat_backend.database.schemas import UserSchema


class UserRepository:
    """Encapsulates persistence operations for :class:`UserSchema`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, user_id: UUID) -> UserSchema | None:
        return self._session.get(UserSchema, user_id)

    def get_by_nickname(self, nickname: str) -> UserSchema | None:
        stmt = select(UserSchema).where(UserSchema.nickname == nickname)
        return self._session.scalar(stmt)

    def add(self, user: UserSchema) -> UserSchema:
        self._session.add(user)
        self._session.flush()
        self._session.refresh(user)
        return user
