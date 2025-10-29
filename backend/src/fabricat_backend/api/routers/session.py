"""WebSocket endpoints for gameplay sessions."""

from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, status

from fabricat_backend.api.dependencies import get_auth_service
from fabricat_backend.api.services import AuthService

router = APIRouter(tags=["session"])


@router.websocket("/ws/game")
async def game_session(
    websocket: WebSocket,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """WebSocket placeholder for the game session."""
    token = websocket.query_params.get("token")
    if token is None:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Missing token"
        )
        return

    try:
        auth_service.decode_access_token(token)
    except Exception:  # noqa: BLE001
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token"
        )
        return

    await websocket.accept()
    await websocket.send_json({"message": "connected"})
