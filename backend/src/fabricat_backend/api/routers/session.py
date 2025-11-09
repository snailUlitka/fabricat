"""WebSocket endpoints for gameplay sessions."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, ValidationError

from fabricat_backend.api.dependencies import get_auth_service
from fabricat_backend.api.models.session import (
    ActionAckResponse,
    ErrorResponse,
    HeartbeatRequest,
    InboundWsMessage,
    JoinSessionRequest,
    PhaseActionRequest,
    PhaseReportResponse,
    PhaseStatusRequest,
    PhaseStatusResponse,
    PhaseTickResponse,
    SessionWelcomeResponse,
    SubmitBuyBidPayload,
    SubmitSellBidPayload,
)
from fabricat_backend.api.services import AuthService  # noqa: TC001
from fabricat_backend.game_logic.phases import (
    DEFAULT_PHASE_DURATION_SECONDS,
    PHASE_SEQUENCE,
    GamePhase,
    PhaseTick,
    PhaseTimer,
)
from fabricat_backend.game_logic.session import GameSession, GameSettings, Player

router = APIRouter(tags=["session"])


ActionSender = Callable[[BaseModel], Awaitable[None]]


PHASE_ACTION_RULES: dict[GamePhase, set[str]] = {
    GamePhase.BUY: {"submit_buy_bid"},
    GamePhase.PRODUCTION: {"production_plan"},
    GamePhase.SELL: {"submit_sell_bid"},
    GamePhase.LOANS: {"loan_decision"},
    GamePhase.CONSTRUCTION: {"construction_request"},
}


def _default_game_settings() -> GameSettings:
    """Return a baseline set of deterministic session settings."""
    return GameSettings(
        start_factory_count=2,
        max_months=12,
        basic_factory_monthly_expenses=1_000.0,
        auto_factory_monthly_expenses=1_500.0,
        raw_material_monthly_expenses=300.0,
        finished_good_monthly_expenses=500.0,
        basic_factory_launch_cost=2_000.0,
        auto_factory_launch_cost=3_000.0,
        bank_start_money=100_000.0,
        loans_monthly_expenses_in_percents=0.01,
        available_loans=[5_000.0, 10_000.0],
        loan_terms_in_months=[2, 3],
        bank_raw_material_sell_volume_range=(5, 9),
        bank_finished_good_buy_volume_range=(5, 9),
        bank_raw_material_sell_min_price_range=(200.0, 400.0),
        bank_finished_good_buy_max_price_range=(400.0, 600.0),
        month_for_upgrade=9,
        upgrade_cost=7_000.0,
        month_for_build_basic=5,
        build_basic_cost=5_000.0,
        month_for_build_auto=7,
        build_auto_cost=10_000.0,
        build_basic_payment_share=0.5,
        build_basic_final_payment_offset=1,
        build_auto_payment_share=0.5,
        build_auto_final_payment_offset=1,
        max_raw_material_storage=10,
        max_finished_good_storage=10,
        max_factories=6,
    )


def _bootstrap_players(user_identifier: str) -> tuple[list[Player], Player]:
    """Create a minimal roster with the user and a placeholder rival."""
    base_id = abs(hash(user_identifier)) % 9_000 + 1
    user_player = Player(id_=base_id, money=10_000.0, priority=1)
    rival = Player(id_=base_id + 1, money=10_000.0, priority=2)
    return [user_player, rival], user_player


def _generate_session_code() -> str:
    """Produce a random short session code."""
    return uuid4().hex[:8]


def _is_action_allowed(phase: GamePhase, kind: str) -> bool:
    if kind == "skip":
        return True
    allowed = PHASE_ACTION_RULES.get(phase, set())
    return kind in allowed


def _clear_phase_state(player: Player, phase: GamePhase) -> None:
    """Reset player state when they skip a phase."""
    match phase:
        case GamePhase.BUY:
            player.buy_bid = None
        case GamePhase.SELL:
            player.sell_bid = None
        case GamePhase.PRODUCTION:
            player.production_call_for_basic = 0
            player.production_call_for_auto = 0
        case GamePhase.LOANS:
            for loan in player.loans:
                if loan.loan_status == "call":
                    loan.loan_status = "idle"
        case GamePhase.CONSTRUCTION:
            player.build_or_upgrade_call = "idle"
        case _:
            return


def _apply_phase_action(  # noqa: C901
    player: Player, request: PhaseActionRequest
) -> dict[str, Any]:
    """Mutate the player according to the payload and return ack details."""
    payload = request.payload
    match payload.kind:
        case "submit_buy_bid":
            if not isinstance(payload, SubmitBuyBidPayload):
                msg = "Invalid payload for submit_buy_bid action."
                raise TypeError(msg)
            player.buy_bid = payload.to_bid()
            return {"buy_bid": player.buy_bid.model_dump()}
        case "submit_sell_bid":
            if not isinstance(payload, SubmitSellBidPayload):
                msg = "Invalid payload for submit_sell_bid action."
                raise TypeError(msg)
            player.sell_bid = payload.to_bid()
            return {"sell_bid": player.sell_bid.model_dump()}
        case "production_plan":
            player.production_call_for_basic = payload.basic
            player.production_call_for_auto = payload.auto
            return {
                "production_call_for_basic": payload.basic,
                "production_call_for_auto": payload.auto,
            }
        case "loan_decision":
            slot = payload.slot
            if slot < 0 or slot >= len(player.loans):
                msg = f"Loan slot {slot} is invalid."
                raise ValueError(msg)
            loan = player.loans[slot]
            if payload.decision == "call":
                loan.loan_status = "call"
            elif loan.loan_status == "call":
                loan.loan_status = "idle"
            return {"slot": slot, "loan_status": loan.loan_status}
        case "construction_request":
            player.build_or_upgrade_call = payload.project
            return {"project": payload.project}
        case "skip":
            _clear_phase_state(player, request.phase)
            return {"skipped": True}
    msg = f"Unsupported action: {payload.kind}"
    raise ValueError(msg)


class SessionRuntime:
    """Managed runtime that streams phase ticks and reports."""

    def __init__(
        self,
        *,
        session: GameSession,
        phase_duration: int,
        sender: ActionSender,
        session_code: str,
    ) -> None:
        self._session = session
        self._phase_duration = phase_duration
        self._sender = sender
        self._session_code = session_code
        self._timer = PhaseTimer(default_duration_seconds=phase_duration)
        self._phase_index = 0
        self._current_phase = PHASE_SEQUENCE[self._phase_index]
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._last_tick: PhaseTick | None = None

    @property
    def current_phase(self) -> GamePhase:
        """Currently running game phase."""
        return self._current_phase

    @property
    def remaining_seconds(self) -> int | None:
        """Seconds left in the active countdown."""
        if self._last_tick is None:
            return None
        return self._last_tick.remaining_seconds

    @property
    def session(self) -> GameSession:
        """Expose the underlying game session."""
        return self._session

    @property
    def session_code(self) -> str:
        """Return the joinable session code."""
        return self._session_code

    async def start(self) -> None:
        """Begin streaming ticks and reports."""
        if self._task is None:
            self._task = asyncio.create_task(self._phase_loop())

    async def stop(self) -> None:
        """Stop the background loop."""
        self._stopped.set()
        self._timer.cancel()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _phase_loop(self) -> None:
        """Iterate through the monthly phase sequence indefinitely."""
        while not self._stopped.is_set():
            phase = self._current_phase
            async for tick in self._timer.ticks(
                phase=phase, duration_seconds=self._phase_duration
            ):
                self._last_tick = tick
                await self._sender(PhaseTickResponse(tick=tick))

            report = self._session.run_phase(phase)
            await self._sender(PhaseReportResponse(report=report))

            if self._session.is_finished:
                self._stopped.set()
                break

            self._phase_index = (self._phase_index + 1) % len(PHASE_SEQUENCE)
            self._current_phase = PHASE_SEQUENCE[self._phase_index]


@router.websocket("/ws/game")
async def game_session(  # noqa: C901, PLR0912, PLR0915
    websocket: WebSocket,
    auth_service: AuthService = Depends(get_auth_service),  # noqa: B008
) -> None:
    """WebSocket endpoint that streams timers, reports, and accepts actions."""
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

    await websocket.accept()

    send_lock = asyncio.Lock()

    async def send(model: BaseModel) -> None:
        async with send_lock:
            await websocket.send_json(model.model_dump())

    runtime: SessionRuntime | None = None
    controlled_player: Player | None = None

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:  # pragma: no cover - network event
                break

            try:
                message = InboundWsMessage.model_validate(data)
            except ValidationError as exc:
                await send(
                    ErrorResponse(
                        message="Invalid payload",
                        detail={"errors": exc.errors()},
                    )
                )
                continue

            if runtime is None:
                if not isinstance(message, JoinSessionRequest):
                    await send(
                        ErrorResponse(
                            message="Join required before sending other messages",
                            detail={"received": getattr(message, "type", None)},
                        )
                    )
                    continue

                session_code = message.session_code or _generate_session_code()
                players, controlled_player = _bootstrap_players(payload.sub)
                session = GameSession(
                    players=players, settings=_default_game_settings()
                )
                runtime = SessionRuntime(
                    session=session,
                    phase_duration=DEFAULT_PHASE_DURATION_SECONDS,
                    sender=send,
                    session_code=session_code,
                )

                await send(
                    SessionWelcomeResponse(
                        session_code=session_code,
                        month=session.month,
                        phase=runtime.current_phase,
                        phase_duration_seconds=DEFAULT_PHASE_DURATION_SECONDS,
                        analytics=session.snapshot_analytics(),
                        seniority=session.seniority_history,
                        tie_break_log=session.tie_break_log,
                    )
                )
                await runtime.start()
                continue

            if isinstance(message, JoinSessionRequest):
                await send(
                    ErrorResponse(
                        message="Session already initialized",
                        detail={"session_code": runtime.session_code},
                    )
                )
                continue

            if isinstance(message, HeartbeatRequest):
                await send(
                    ActionAckResponse(
                        phase=runtime.current_phase,
                        action="heartbeat",
                        detail={"nonce": message.nonce},
                    )
                )
                continue

            if isinstance(message, PhaseStatusRequest):
                await send(
                    PhaseStatusResponse(
                        month=runtime.session.month,
                        phase=runtime.current_phase,
                        analytics=runtime.session.snapshot_analytics(),
                        remaining_seconds=runtime.remaining_seconds,
                    )
                )
                continue

            if isinstance(message, PhaseActionRequest):
                if controlled_player is None:
                    await send(
                        ErrorResponse(
                            message="Session not ready for actions",
                            detail={},
                        )
                    )
                    continue

                if message.phase != runtime.current_phase:
                    await send(
                        ErrorResponse(
                            message="Phase mismatch",
                            detail={
                                "expected": runtime.current_phase.value,
                                "received": message.phase.value,
                            },
                        )
                    )
                    continue

                if not _is_action_allowed(message.phase, message.payload.kind):
                    await send(
                        ErrorResponse(
                            message="Action not allowed in this phase",
                            detail={
                                "phase": message.phase.value,
                                "action": message.payload.kind,
                            },
                        )
                    )
                    continue

                try:
                    detail = _apply_phase_action(controlled_player, message)
                except (TypeError, ValueError) as exc:
                    await send(
                        ErrorResponse(
                            message=str(exc),
                            detail={"phase": message.phase.value},
                        )
                    )
                    continue

                await send(
                    ActionAckResponse(
                        phase=message.phase,
                        action=message.payload.kind,
                        detail=detail,
                    )
                )
                continue

            await send(
                ErrorResponse(
                    message="Unsupported message type",
                    detail={"type": getattr(message, "type", None)},
                )
            )
    finally:
        if runtime is not None:
            await runtime.stop()
