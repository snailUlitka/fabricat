"""WebSocket endpoints for gameplay sessions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import TypeAdapter, ValidationError

from fabricat_backend.api.dependencies import (
    get_auth_service,
    get_game_session_service,
)
from fabricat_backend.api.models import (
    GameSessionDecisionsStoredResponse,
    GameSessionErrorResponse,
    GameSessionMonthResultResponse,
    GameSessionRequest,
    GameSessionSettingsResponse,
    GameSessionStateResponse,
    GameSessionSubmitDecisionsRequest,
)
from fabricat_backend.api.services import (
    AuthService,
    DecisionSubmission,
    GameSessionService,
)
from fabricat_backend.shared.value_objects import PhaseIdentifier

router = APIRouter(tags=["session"])

_REQUEST_ADAPTER = TypeAdapter(GameSessionRequest)


def _without_configuration(payload: dict[str, Any]) -> dict[str, Any]:
    """Return *payload* without the ``configuration`` entry."""
    normalized = dict(payload)
    normalized.pop("configuration", None)
    return normalized


@router.websocket("/ws/game")
async def game_session(
    websocket: WebSocket,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    session_service: Annotated[GameSessionService, Depends(get_game_session_service)],
) -> None:
    """Handle the lifecycle of an interactive gameplay session."""
    token = websocket.query_params.get("token")
    if token is None:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Missing token"
        )
        return

    try:
        payload = auth_service.decode_access_token(token)
    except Exception:  # noqa: BLE001
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token"
        )
        return

    session_id = websocket.query_params.get("session_id") or payload.sub
    company_id = websocket.query_params.get("company_id") or payload.sub

    await websocket.accept()
    snapshot = session_service.ensure_session(session_id, company_id=company_id)
    await websocket.send_json(
        GameSessionSettingsResponse(
            type="session_settings",
            session_id=session_id,
            configuration=session_service.serialize_configuration(
                snapshot.configuration
            ),
        ).model_dump(mode="json")
    )
    logs = session_service.get_logs(session_id)
    await websocket.send_json(
        GameSessionStateResponse(
            type="session_state",
            session_id=session_id,
            snapshot=_without_configuration(
                session_service.serialize_snapshot(snapshot)
            ),
            logs=[session_service.serialize_log(log) for log in logs],
        ).model_dump(mode="json")
    )

    while True:
        try:
            message = await websocket.receive_json()
        except WebSocketDisconnect:
            break
        except RuntimeError:
            break

        try:
            command = _REQUEST_ADAPTER.validate_python(message)
        except ValidationError as exc:
            await websocket.send_json(
                GameSessionErrorResponse(
                    type="error",
                    message="Invalid request payload",
                    detail=str(exc),
                ).model_dump(mode="json")
            )
            continue

        if isinstance(command, GameSessionSubmitDecisionsRequest):
            phase = PhaseIdentifier(command.phase)
            submissions = [
                DecisionSubmission(
                    company_id=decision.company_id,
                    payload=decision.payload,
                )
                for decision in command.decisions
            ]
            try:
                stored = session_service.submit_phase_decisions(
                    session_id,
                    phase,
                    submissions,
                    default_company_id=company_id,
                )
            except ValueError as exc:
                await websocket.send_json(
                    GameSessionErrorResponse(
                        type="error",
                        message="Invalid decision payload",
                        detail=str(exc),
                    ).model_dump(mode="json")
                )
                continue

            await websocket.send_json(
                GameSessionDecisionsStoredResponse(
                    type="decisions_stored",
                    session_id=session_id,
                    phase=phase.value,
                    decisions=session_service.serialize_decisions(stored),
                ).model_dump(mode="json")
            )
            continue

        if command.action == "join":
            snapshot = session_service.ensure_session(session_id, company_id=company_id)
            logs = session_service.get_logs(session_id)
            await websocket.send_json(
                GameSessionStateResponse(
                    type="session_state",
                    session_id=session_id,
                    snapshot=_without_configuration(
                        session_service.serialize_snapshot(snapshot)
                    ),
                    logs=[session_service.serialize_log(log) for log in logs],
                ).model_dump(mode="json")
            )
            continue

        result = session_service.advance_month(session_id)
        snapshot = session_service.get_snapshot(session_id)
        logs = session_service.get_logs(session_id)
        await websocket.send_json(
            GameSessionMonthResultResponse(
                type="month_result",
                session_id=session_id,
                result=_without_configuration(
                    session_service.serialize_month_result(result)
                ),
                snapshot=_without_configuration(
                    session_service.serialize_snapshot(snapshot)
                ),
                log=session_service.serialize_log(result.log),
            ).model_dump(mode="json")
        )
        await websocket.send_json(
            GameSessionStateResponse(
                type="session_state",
                session_id=session_id,
                snapshot=_without_configuration(
                    session_service.serialize_snapshot(snapshot)
                ),
                logs=[session_service.serialize_log(log) for log in logs],
            ).model_dump(mode="json")
        )
