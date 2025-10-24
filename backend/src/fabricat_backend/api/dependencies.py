"""Dependency providers for FastAPI routers."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from fabricat_backend.api.services import AuthService
from fabricat_backend.database import UserRepository, get_session

_security = HTTPBearer(auto_error=False)
_auth_service = AuthService()


def get_auth_service() -> AuthService:
    """Return the shared :class:`AuthService` instance."""

    return _auth_service


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
    session: Session = Depends(get_session),
    auth_service: AuthService = Depends(get_auth_service),
):
    """Resolve the authenticated user from a bearer token."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing credentials"
        )

    try:
        payload = auth_service.decode_access_token(credentials.credentials)
    except Exception as exc:  # pragma: no cover - pyjwt raises various subclasses
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc

    repository = UserRepository(session)
    try:
        user_id = UUID(payload.sub)
    except ValueError as exc:  # pragma: no cover - should not happen for valid tokens
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject"
        ) from exc

    user = repository.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )

    return user


__all__ = ["get_auth_service", "get_current_user"]
