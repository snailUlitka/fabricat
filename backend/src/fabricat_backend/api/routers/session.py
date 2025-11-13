"""WebSocket endpoints for gameplay sessions."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, TypeAdapter, ValidationError

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
    SessionControlAckResponse,
    SessionControlRequest,
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

INBOUND_WS_MESSAGE_ADAPTER = TypeAdapter(InboundWsMessage)


MIN_PLAYERS_TO_AUTO_START = 2
MAX_PLAYERS = 4
AUTO_START_DELAY_SECONDS = 60


PHASE_ACTION_RULES: dict[GamePhase, set[str]] = {
    GamePhase.BUY: {"submit_buy_bid"},
    GamePhase.PRODUCTION: {"production_plan"},
    GamePhase.SELL: {"submit_sell_bid"},
    GamePhase.LOANS: {"loan_decision"},
    GamePhase.CONSTRUCTION: {"construction_request"},
}


@dataclass
class SessionContext:
    """Shared state for a joinable gameplay session."""

    session_code: str
    session: GameSession
    runtime: SessionRuntime
    players: list[Player]
    assignments: dict[str, Player] = field(default_factory=dict)
    user_connections: dict[str, int] = field(default_factory=dict)
    listeners: list[ActionSender] = field(default_factory=list)
    session_started: bool = False
    auto_start_task: asyncio.Task | None = None
    connections: int = 0

    def assign_player(self, user_identifier: str) -> Player:
        """Attach the user to an available player seat."""
        player = self.assignments.get(user_identifier)
        if player is not None:
            return player
        assigned_ids = {entry.id_ for entry in self.assignments.values()}
        for candidate in self.players:
            if candidate.id_ not in assigned_ids:
                self.assignments[user_identifier] = candidate
                return candidate
        msg = "Session is full"
        raise RuntimeError(msg)

    def active_player_count(self) -> int:
        """Count players with at least one active websocket."""
        return sum(1 for count in self.user_connections.values() if count > 0)


_SESSION_REGISTRY: dict[str, SessionContext] = {}
_SESSION_LOCK = asyncio.Lock()


class SessionJoinError(Exception):
    """Raised when a user cannot join the requested session."""

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail = detail or {}


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


def _refresh_unstarted_context(context: SessionContext) -> None:
    """Rebuild the runtime when the player roster changes pre-launch."""
    if context.session_started:
        return
    listeners = list(context.listeners)
    session = GameSession(players=context.players, settings=_default_game_settings())
    runtime = SessionRuntime(
        session=session,
        phase_duration=DEFAULT_PHASE_DURATION_SECONDS,
        sender=None,
        session_code=context.session_code,
    )
    for listener in listeners:
        runtime.add_sender(listener)
    context.session = session
    context.runtime = runtime


def _spawn_player_slot(context: SessionContext) -> Player:
    """Create a fresh player seat with deterministic identifiers."""
    next_id = (
        max((player.id_ for player in context.players), default=0) + 1
        if context.players
        else abs(hash(context.session_code)) % 9_000 + 1
    )
    priority = len(context.players) + 1
    return Player(id_=next_id, money=10_000.0, priority=priority)


async def _register_connection(
    *,
    requested_code: str | None,
    user_identifier: str,
    send: ActionSender,
) -> tuple[SessionContext, str, Player, bool]:
    """Create or reuse a session context and attach the user to it."""
    async with _SESSION_LOCK:
        session_code = requested_code or _generate_session_code()
        context = _SESSION_REGISTRY.get(session_code)
        if context is None:
            players, controlled_player = _bootstrap_players(user_identifier)
            session = GameSession(players=players, settings=_default_game_settings())
            runtime = SessionRuntime(
                session=session,
                phase_duration=DEFAULT_PHASE_DURATION_SECONDS,
                sender=None,
                session_code=session_code,
            )
            runtime.add_sender(send)
            context = SessionContext(
                session_code=session_code,
                session=session,
                runtime=runtime,
                players=players,
                assignments={user_identifier: controlled_player},
                user_connections={user_identifier: 1},
                listeners=[send],
                connections=1,
            )
            _SESSION_REGISTRY[session_code] = context
            return context, session_code, controlled_player, True

        if context.session.is_finished:
            msg = "Session already finished"
            raise SessionJoinError(msg, {"session_code": session_code})
        if (
            context.session_started
            and context.runtime.has_started
            and user_identifier not in context.assignments
        ):
            msg = "Session already in progress"
            raise SessionJoinError(msg, {"session_code": session_code})
        if (
            user_identifier not in context.assignments
            and len(context.assignments) >= MAX_PLAYERS
        ):
            msg = "Session is full"
            raise SessionJoinError(
                msg,
                {"session_code": session_code, "max_players": MAX_PLAYERS},
            )

        if (
            user_identifier not in context.assignments
            and len(context.players) < MAX_PLAYERS
            and not context.session_started
            and len(context.assignments) >= len(context.players)
        ):
            context.players.append(_spawn_player_slot(context))
            _refresh_unstarted_context(context)

        controlled_player = context.assign_player(user_identifier)
        context.runtime.add_sender(send)
        if send not in context.listeners:
            context.listeners.append(send)
        context.connections += 1
        context.user_connections[user_identifier] = (
            context.user_connections.get(user_identifier, 0) + 1
        )
        return context, session_code, controlled_player, False


async def _release_connection(
    context: SessionContext,
    *,
    user_identifier: str,
    sender: ActionSender,
) -> None:
    """Detach a websocket from the shared session context."""
    should_cleanup = False
    async with _SESSION_LOCK:
        context.runtime.remove_sender(sender)
        context.connections = max(context.connections - 1, 0)
        with contextlib.suppress(ValueError):
            context.listeners.remove(sender)
        if user_identifier in context.user_connections:
            context.user_connections[user_identifier] = max(
                context.user_connections[user_identifier] - 1, 0
            )
            if (
                context.user_connections[user_identifier] == 0
                and not context.session_started
            ):
                context.assignments.pop(user_identifier, None)
        if context.connections == 0:
            _SESSION_REGISTRY.pop(context.session_code, None)
            should_cleanup = True
    if should_cleanup:
        _cancel_auto_start(context)
        await context.runtime.stop()


def _cancel_auto_start(context: SessionContext) -> None:
    """Stop the pending auto-start countdown."""
    if context.auto_start_task is not None:
        context.auto_start_task.cancel()
        context.auto_start_task = None


def _ensure_auto_start(context: SessionContext) -> None:
    """Schedule the auto-start timer if it is not running."""
    if context.session_started or context.auto_start_task is not None:
        return
    context.auto_start_task = asyncio.create_task(_auto_start_lobby(context))


async def _auto_start_lobby(context: SessionContext) -> None:
    """Background task that launches the session after inactivity."""
    while True:
        try:
            await asyncio.sleep(AUTO_START_DELAY_SECONDS)
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            return

        started, detail = await _start_context_session(
            context,
            reason="auto_timer",
            responder=None,
            broadcast=True,
        )
        if started:
            return
        if detail.get("reason") == "session_finished":
            return


async def _start_context_session(
    context: SessionContext,
    *,
    reason: str,
    responder: ActionSender | None,
    broadcast: bool,
) -> tuple[bool, dict[str, Any]]:
    """Attempt to kick off the session runtime."""
    async with _SESSION_LOCK:
        if context.session.is_finished:
            return False, {"reason": "session_finished"}
        if context.session_started or context.runtime.has_started:
            return False, {"reason": "already_running"}
        active_players = context.active_player_count()
        if active_players < MIN_PLAYERS_TO_AUTO_START:
            return False, {
                "reason": "insufficient_players",
                "connected_players": active_players,
            }
        context.session_started = True
        _cancel_auto_start(context)

    phase = context.runtime.current_phase
    payload = SessionControlAckResponse(
        command="start",
        started=True,
        detail={"reason": reason, "phase": phase.value},
    )
    if broadcast:
        await context.runtime.broadcast(payload)
    elif responder is not None:
        await responder(payload)
    await context.runtime.start()
    return True, {"reason": reason}


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
        self._senders: list[ActionSender] = []
        if sender is not None:
            self._senders.append(sender)
        self._session_code = session_code
        self._timer = PhaseTimer(default_duration_seconds=phase_duration)
        self._phase_index = 0
        self._current_phase = PHASE_SEQUENCE[self._phase_index]
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._last_tick: PhaseTick | None = None
        self._has_started = False

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

    @property
    def has_started(self) -> bool:
        """Return True if the phase loop has been started."""
        return self._has_started

    def add_sender(self, sender: ActionSender) -> None:
        """Register a new outbound channel."""
        if sender not in self._senders:
            self._senders.append(sender)

    def remove_sender(self, sender: ActionSender) -> None:
        """Remove an outbound channel."""
        with contextlib.suppress(ValueError):
            self._senders.remove(sender)

    async def start(self) -> None:
        """Begin streaming ticks and reports."""
        if self._task is None:
            self._task = asyncio.create_task(self._phase_loop())
            self._has_started = True

    async def stop(self) -> None:
        """Stop the background loop."""
        self._stopped.set()
        self._timer.cancel()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._has_started = False

    def fast_forward_phase(self) -> None:
        """Cancel the active timer to finish the phase immediately."""
        self._timer.cancel()

    async def _phase_loop(self) -> None:
        """Iterate through the monthly phase sequence indefinitely."""
        while not self._stopped.is_set():
            phase = self._current_phase
            async for tick in self._timer.ticks(
                phase=phase, duration_seconds=self._phase_duration
            ):
                self._last_tick = tick
                await self._broadcast(PhaseTickResponse(tick=tick))

            report = self._session.run_phase(phase)
            await self._broadcast(PhaseReportResponse(report=report))

            if self._session.is_finished:
                self._stopped.set()
                break

            self._phase_index = (self._phase_index + 1) % len(PHASE_SEQUENCE)
            self._current_phase = PHASE_SEQUENCE[self._phase_index]

    async def _broadcast(self, model: BaseModel) -> None:
        """Send a payload to all registered listeners."""
        for sender in list(self._senders):
            await sender(model)

    async def broadcast(self, model: BaseModel) -> None:
        """Public wrapper used outside the runtime loop."""
        await self._broadcast(model)


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
            await websocket.send_json(model.model_dump(mode="json"))

    context: SessionContext | None = None
    controlled_player: Player | None = None
    session_code_value: str | None = None
    user_identifier: str | None = None

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:  # pragma: no cover - network event
                break

            try:
                message = INBOUND_WS_MESSAGE_ADAPTER.validate_python(data)
            except ValidationError as exc:
                await send(
                    ErrorResponse(
                        message="Invalid payload",
                        detail={"errors": exc.errors()},
                    )
                )
                continue

            if context is None:
                if not isinstance(message, JoinSessionRequest):
                    await send(
                        ErrorResponse(
                            message="Join required before sending other messages",
                            detail={"received": getattr(message, "type", None)},
                        )
                    )
                    continue

                user_identifier = payload.sub
                try:
                    (
                        context,
                        session_code_value,
                        controlled_player,
                        _created,
                    ) = await _register_connection(
                        requested_code=message.session_code,
                        user_identifier=user_identifier,
                        send=send,
                    )
                except SessionJoinError as exc:
                    await send(
                        ErrorResponse(message=str(exc), detail=exc.detail),
                    )
                    continue

                runtime = context.runtime
                await send(
                    SessionWelcomeResponse(
                        session_code=session_code_value,
                        month=context.session.month,
                        phase=runtime.current_phase,
                        phase_duration_seconds=DEFAULT_PHASE_DURATION_SECONDS,
                        analytics=context.session.snapshot_analytics(),
                        seniority=context.session.seniority_history,
                        tie_break_log=context.session.tie_break_log,
                    )
                )
                _ensure_auto_start(context)
                continue

            if isinstance(message, JoinSessionRequest):
                await send(
                    ErrorResponse(
                        message="Session already initialized",
                        detail={"session_code": context.session_code},
                    )
                )
                continue

            if isinstance(message, SessionControlRequest):
                if message.command != "start":
                    await send(
                        ErrorResponse(
                            message="Unsupported session command",
                            detail={"command": message.command},
                        )
                    )
                    continue

                started, detail = await _start_context_session(
                    context,
                    reason="manual",
                    responder=send,
                    broadcast=False,
                )
                if not started:
                    await send(
                        SessionControlAckResponse(
                            command="start",
                            started=False,
                            detail=detail,
                        )
                    )
                continue

            if isinstance(message, HeartbeatRequest):
                await send(
                    ActionAckResponse(
                        phase=context.runtime.current_phase,
                        action="heartbeat",
                        detail={"nonce": message.nonce},
                    )
                )
                continue

            if isinstance(message, PhaseStatusRequest):
                await send(
                    PhaseStatusResponse(
                        month=context.session.month,
                        phase=context.runtime.current_phase,
                        analytics=context.session.snapshot_analytics(),
                        remaining_seconds=context.runtime.remaining_seconds,
                    )
                )
                continue

            if isinstance(message, PhaseActionRequest):
                if context is None:
                    await send(
                        ErrorResponse(
                            message="Session not initialized",
                            detail={"action": message.payload.kind},
                        )
                    )
                    continue

                if not context.session_started or not context.runtime.has_started:
                    await send(
                        ErrorResponse(
                            message="Session not started",
                            detail={"action": message.payload.kind},
                        )
                    )
                    continue

                if controlled_player is None:
                    await send(
                        ErrorResponse(
                            message="Session not ready for actions",
                            detail={},
                        )
                    )
                    continue

                if message.phase != context.runtime.current_phase:
                    await send(
                        ErrorResponse(
                            message="Phase mismatch",
                            detail={
                                "expected": context.runtime.current_phase.value,
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

                if message.payload.kind == "skip":
                    context.runtime.fast_forward_phase()

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
        if context is not None and user_identifier is not None:
            await _release_connection(
                context,
                user_identifier=user_identifier,
                sender=send,
            )
