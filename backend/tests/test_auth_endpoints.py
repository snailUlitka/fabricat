from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from fabricat_backend.api import create_api
from fabricat_backend.database import UserSchema, get_session

if TYPE_CHECKING:
    from collections.abc import Generator, Iterator
    from uuid import UUID


class FakeUserRepository:
    """In-memory repository used to mock database operations."""

    def __init__(
        self, session: Any
    ) -> None:  # pragma: no cover - session unused in fake repo
        self._session = session

    _store: dict[UUID, UserSchema] = {}  # noqa: RUF012

    @classmethod
    def reset(cls) -> None:
        cls._store = {}

    def get_by_id(self, user_id: UUID) -> UserSchema | None:
        return type(self)._store.get(user_id)

    def get_by_nickname(self, nickname: str) -> UserSchema | None:
        return next(
            (user for user in type(self)._store.values() if user.nickname == nickname),
            None,
        )

    def add(self, user: UserSchema) -> UserSchema:
        if getattr(user, "created_at", None) is None:
            timestamp = datetime.now(UTC)
            user.created_at = timestamp
            user.updated_at = timestamp
        type(self)._store[user.id] = user
        return user


@pytest.fixture(autouse=True)
def reset_repo() -> Iterator[None]:
    FakeUserRepository.reset()
    yield
    FakeUserRepository.reset()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(
        "fabricat_backend.api.services.auth.UserRepository", FakeUserRepository
    )
    monkeypatch.setattr(
        "fabricat_backend.api.dependencies.UserRepository", FakeUserRepository
    )

    app = create_api()

    def override_session() -> Generator[None, None, None]:
        yield None

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_register_user_success(client: TestClient) -> None:
    payload = {
        "nickname": "PlayerOne",
        "password": "Password123",
        "icon": "astronaut",
    }
    response = client.post("/auth/register", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["token"]["token_type"] == "bearer"  # noqa: S105
    assert data["user"]["nickname"] == payload["nickname"]
    assert "access_token" in data["token"]


def test_register_user_conflict(client: TestClient) -> None:
    payload = {
        "nickname": "PlayerOne",
        "password": "Password123",
        "icon": "astronaut",
    }
    assert client.post("/auth/register", json=payload).status_code == 201

    response = client.post("/auth/register", json=payload)

    assert response.status_code == 409


def test_login_user_success(client: TestClient) -> None:
    register_payload = {
        "nickname": "PlayerTwo",
        "password": "Password123",
        "icon": "astronaut",
    }
    assert client.post("/auth/register", json=register_payload).status_code == 201

    login_payload = {
        "nickname": register_payload["nickname"],
        "password": register_payload["password"],
    }
    response = client.post("/auth/login", json=login_payload)

    assert response.status_code == 200
    data = response.json()
    assert data["token"]["token_type"] == "bearer"  # noqa: S105
    assert data["user"]["nickname"] == register_payload["nickname"]


def test_login_user_invalid_credentials(client: TestClient) -> None:
    payload = {
        "nickname": "Unknown",
        "password": "Password123",
    }
    response = client.post("/auth/login", json=payload)

    assert response.status_code == 401
