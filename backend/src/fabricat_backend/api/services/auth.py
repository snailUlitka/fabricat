"""Authentication domain logic."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Tuple
from uuid import uuid4

import jwt
from sqlalchemy.orm import Session

from fabricat_backend.database import UserRepository, UserSchema
from fabricat_backend.shared import AvatarIcon
from fabricat_backend.settings import BackendSettings, get_settings


class UserAlreadyExistsError(Exception):
    """Raised when attempting to create a duplicate user."""


class InvalidCredentialsError(Exception):
    """Raised when supplied credentials are invalid."""


@dataclass(slots=True)
class TokenPayload:
    """Represents encoded token metadata."""

    sub: str
    exp: datetime


class AuthService:
    """Handles password hashing and token generation."""

    def __init__(
        self,
        *,
        secret_key: str | None = None,
        algorithm: str = "HS256",
        access_token_ttl_minutes: int = 60,
        settings: BackendSettings | None = None,
    ) -> None:
        config = settings or get_settings()
        self._secret_key = secret_key or config.auth_secret_key
        self._algorithm = algorithm
        self._access_token_ttl = timedelta(minutes=access_token_ttl_minutes)

    def hash_password(self, password: str) -> str:
        """Hash a password using PBKDF2 with a random salt."""

        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return f"{base64.b64encode(salt).decode()}:{base64.b64encode(digest).decode()}"

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Validate a password against a stored PBKDF2 hash."""

        try:
            salt_b64, hash_b64 = password_hash.split(":", 1)
        except ValueError:
            return False
        salt = base64.b64decode(salt_b64.encode())
        expected = base64.b64decode(hash_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(actual, expected)

    def create_access_token(self, subject: str) -> str:
        expires_at = datetime.now(tz=timezone.utc) + self._access_token_ttl
        payload = {"sub": subject, "exp": expires_at}
        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

    def decode_access_token(self, token: str) -> TokenPayload:
        data = jwt.decode(token, self._secret_key, algorithms=[self._algorithm])
        return TokenPayload(
            sub=data["sub"], exp=datetime.fromtimestamp(data["exp"], tz=timezone.utc)
        )

    def register_user(
        self,
        *,
        session: Session,
        nickname: str,
        password: str,
        icon: AvatarIcon,
    ) -> Tuple[UserSchema, str]:
        repository = UserRepository(session)
        if repository.get_by_nickname(nickname) is not None:
            raise UserAlreadyExistsError(nickname)

        password_hash = self.hash_password(password)
        user = UserSchema(
            id=uuid4(),
            nickname=nickname,
            password_hash=password_hash,
            icon=icon,
        )
        user = repository.add(user)
        token = self.create_access_token(str(user.id))
        return user, token

    def authenticate_user(
        self, *, session: Session, nickname: str, password: str
    ) -> Tuple[UserSchema, str]:
        repository = UserRepository(session)
        user = repository.get_by_nickname(nickname)
        if user is None or not self.verify_password(password, user.password_hash):
            raise InvalidCredentialsError(nickname)
        token = self.create_access_token(str(user.id))
        return user, token
