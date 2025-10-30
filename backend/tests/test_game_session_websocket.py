"""Integration tests for the game session WebSocket API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from fabricat_backend.api import create_api
from fabricat_backend.api import dependencies as dependency_module
from fabricat_backend.api.dependencies import get_game_session_service
from fabricat_backend.api.services import AuthService, GameSessionService
from fabricat_backend.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Return a FastAPI test client with isolated game session state."""

    dependency_module.get_game_session_service.cache_clear()
    app = create_api()
    session_service = GameSessionService.create_default()
    app.dependency_overrides[get_game_session_service] = lambda: session_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    dependency_module.get_game_session_service.cache_clear()


def _issue_token(subject: str) -> str:
    """Create a signed access token for *subject*."""
    auth_service = AuthService(settings=get_settings())
    return auth_service.create_access_token(subject)


def test_websocket_game_flow(client: TestClient) -> None:
    token = _issue_token("player-1")
    company_id = "acme-industries"

    with client.websocket_connect(
        f"/ws/game?token={token}&company_id={company_id}"
    ) as websocket:
        initial_settings = websocket.receive_json()
        assert initial_settings["type"] == "session_settings"
        assert initial_settings["session_id"] == "player-1"
        assert "configuration" in initial_settings

        initial_state = websocket.receive_json()
        assert initial_state["type"] == "session_state"
        assert initial_state["session_id"] == "player-1"
        assert initial_state["snapshot"]["month_index"] == 0
        assert "configuration" not in initial_state["snapshot"]

        websocket.send_json({"action": "join"})
        snapshot_again = websocket.receive_json()
        assert snapshot_again["type"] == "session_state"
        assert snapshot_again["snapshot"]["month_index"] == 0
        assert "configuration" not in snapshot_again["snapshot"]

        websocket.send_json(
            {
                "action": "submit_decisions",
                "phase": "production",
                "decisions": [
                    {
                        "company_id": company_id,
                        "payload": {"orders": [{"quantity": 2}]},
                    }
                ],
            }
        )
        stored = websocket.receive_json()
        assert stored["type"] == "decisions_stored"
        assert stored["phase"] == "production"
        assert len(stored["decisions"]) == 1
        assert stored["decisions"][0]["company_id"] == company_id

        websocket.send_json({"action": "advance_month"})
        month_result = websocket.receive_json()
        assert month_result["type"] == "month_result"
        assert month_result["result"]["month_index"] == 0
        assert month_result["snapshot"]["month_index"] == 1
        assert "configuration" not in month_result["result"]
        assert "configuration" not in month_result["snapshot"]

        follow_up = websocket.receive_json()
        assert follow_up["type"] == "session_state"
        assert follow_up["snapshot"]["month_index"] == 1
        assert len(follow_up["logs"]) >= 1
        assert "configuration" not in follow_up["snapshot"]
