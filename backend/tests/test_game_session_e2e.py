from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Self

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from fabricat_backend.api import create_api
from fabricat_backend.api.models.session import GamePhase
from fabricat_backend.api.routers import session as session_router
from fabricat_backend.database import UserSchema, get_session
from fabricat_backend.game_logic.phases import PHASE_SEQUENCE, PhaseReport, PhaseTick
from fabricat_backend.game_logic.session import (
    FinishedGood,
    GameSettings,
    Player,
    RawMaterial,
)
from fabricat_backend.game_logic.session import (
    GameSession as OriginalGameSession,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator
    from uuid import UUID


class FakeUserRepository:
    """In-memory repository used to mock database operations."""

    def __init__(self, session: Any) -> None:  # pragma: no cover - session unused
        self._session = session

    _store: ClassVar[dict[UUID, UserSchema]] = {}

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


class SharedSessionHarness:
    """Helper that wires session patches for deterministic two-player tests."""

    def __init__(
        self,
        *,
        settings: GameSettings,
        session_code: str,
        expected_connections: int,
    ) -> None:
        self.settings = settings
        self.session_code = session_code
        self.expected_connections = expected_connections
        self.phase_ready = dict.fromkeys(PHASE_SEQUENCE, False)
        self.session_state: dict[str, dict[str, Any]] = {}
        self._original_bootstrap = session_router._bootstrap_players

    def patch(self, monkeypatch: pytest.MonkeyPatch) -> Callable[[GamePhase], None]:
        monkeypatch.setattr(
            session_router, "_TEST_PHASE_READY", self.phase_ready, raising=False
        )
        monkeypatch.setattr(
            session_router,
            "_TEST_EXPECTED_CONNECTIONS",
            self.expected_connections,
            raising=False,
        )
        monkeypatch.setattr(
            session_router, "_bootstrap_players", self.bootstrap_players
        )
        monkeypatch.setattr(
            session_router,
            "_default_game_settings",
            lambda: self.settings.model_copy(deep=True),
        )

        PatchedGameSession.configure(self)
        PatchedSessionRuntime.configure(self)
        monkeypatch.setattr(session_router, "GameSession", PatchedGameSession)
        monkeypatch.setattr(session_router, "SessionRuntime", PatchedSessionRuntime)
        return self.release_phase

    def bootstrap_players(self, user_identifier: str) -> tuple[list[Player], Player]:
        if self.session_code != session_router._CURRENT_TEST_SESSION_CODE:
            return self._original_bootstrap(user_identifier)

        state = self.session_state.setdefault(
            self.session_code,
            {"players": self._build_players(), "assignments": {}},
        )

        assignments: dict[str, Player] = state["assignments"]
        if user_identifier not in assignments:
            player_index = len(assignments)
            if player_index >= len(state["players"]):
                msg = "No available players for assignment"
                raise RuntimeError(msg)
            assignments[user_identifier] = state["players"][player_index]

        return state["players"], assignments[user_identifier]

    def release_phase(self, phase: GamePhase) -> None:
        self.phase_ready[phase] = True

    def cleanup(self) -> None:
        session_router._CURRENT_TEST_SESSION_CODE = None
        self.session_state.clear()
        PatchedSessionRuntime.reset()
        PatchedGameSession.reset()

    def _build_players(self) -> list[Player]:
        players = [
            Player(id_=101, money=15_000.0, priority=1),
            Player(id_=202, money=15_000.0, priority=2),
        ]

        for player in players:
            player.raw_materials.append(
                RawMaterial(
                    monthly_expenses=self.settings.raw_material_monthly_expenses
                )
            )
            player.finished_goods.append(
                FinishedGood(
                    monthly_expenses=self.settings.finished_good_monthly_expenses
                )
            )

        player_one = players[0]
        player_one.loans[0].amount = 1_000.0
        player_one.loans[0].return_month = 1
        player_one.loans[0].loan_status = "in_progress"
        return players


class PatchedGameSession(OriginalGameSession):
    """GameSession that reuses a single harness-managed instance per code."""

    _registry: ClassVar[dict[str, PatchedGameSession]] = {}
    _harness: ClassVar[SharedSessionHarness | None] = None

    @classmethod
    def configure(cls, harness: SharedSessionHarness) -> None:
        cls._harness = harness

    @classmethod
    def reset(cls) -> None:
        cls._registry.clear()
        cls._harness = None

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Self:
        harness = cls._harness
        code = session_router._CURRENT_TEST_SESSION_CODE if harness else None
        if code is not None and code in cls._registry:
            return cls._registry[code]
        instance = super().__new__(cls)
        if code is not None:
            cls._registry[code] = instance
        return instance

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if getattr(self, "_initialized", False):
            return
        kwargs["seed_seniority"] = False
        super().__init__(*args, **kwargs)
        self._initialized = True


class PatchedSessionRuntime:
    """Runtime that multiplexes ticks and reports across multiple sockets."""

    _registry: ClassVar[dict[str, PatchedSessionRuntime]] = {}
    _harness: ClassVar[SharedSessionHarness | None] = None

    @classmethod
    def configure(cls, harness: SharedSessionHarness) -> None:
        cls._harness = harness

    @classmethod
    def reset(cls) -> None:
        cls._registry.clear()
        cls._harness = None

    def __new__(cls, *_args: Any, **kwargs: Any) -> Self:
        session_code = kwargs.get("session_code")
        sender = kwargs.get("sender")
        if session_code in cls._registry:
            instance = cls._registry[session_code]
            if sender is not None:
                instance._senders.append(sender)
            instance._refcount += 1
            return instance
        instance = super().__new__(cls)
        if session_code is not None:
            cls._registry[session_code] = instance
        return instance

    def __init__(self, *_args: Any, **kwargs: Any) -> None:
        if getattr(self, "_initialized", False):
            return

        harness = self._require_harness()
        self._session = kwargs["session"]
        self._session_code = kwargs["session_code"]
        # Ignore the real phase duration to keep the test tight
        self._phase_duration = 0
        sender = kwargs["sender"]
        self._current_phase = PHASE_SEQUENCE[0]
        self._last_tick: PhaseTick | None = None
        self._senders = [sender]
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._refcount = 1
        self._harness = harness
        self._initialized = True

    @property
    def current_phase(self) -> GamePhase:
        return self._current_phase

    @property
    def remaining_seconds(self) -> int | None:
        if self._last_tick is None:
            return None
        return self._last_tick.remaining_seconds

    @property
    def session(self) -> OriginalGameSession:
        return self._session

    @property
    def session_code(self) -> str:
        return self._session_code

    async def start(self) -> None:
        harness = self._require_harness()
        if self._task is None and self._refcount >= harness.expected_connections:
            self._task = asyncio.create_task(self._phase_loop())

    async def stop(self) -> None:
        self._refcount -= 1
        if self._refcount > 0:
            return
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        type(self)._registry.pop(self._session_code, None)

    async def _broadcast(self, payload: Any) -> None:
        for sender in list(self._senders):
            await sender(payload)

    async def _phase_loop(self) -> None:
        harness = self._require_harness()
        while not self._stopped.is_set():
            phase = self._current_phase
            tick = PhaseTick(
                phase=phase,
                remaining_seconds=0,
                total_seconds=self._phase_duration,
                started_at=datetime.now(tz=UTC),
            )
            self._last_tick = tick
            await self._broadcast(session_router.PhaseTickResponse(tick=tick))

            while not harness.phase_ready.get(phase, True):
                await asyncio.sleep(0)
                if self._stopped.is_set():
                    break

            if self._stopped.is_set():
                break

            report = self._session.run_phase(phase)
            await self._broadcast(session_router.PhaseReportResponse(report=report))
            harness.phase_ready[phase] = False

            if self._session.is_finished:
                self._stopped.set()
                break

            next_index = (PHASE_SEQUENCE.index(phase) + 1) % len(PHASE_SEQUENCE)
            self._current_phase = PHASE_SEQUENCE[next_index]

    @classmethod
    def _require_harness(cls) -> SharedSessionHarness:
        if cls._harness is None:
            msg = "SharedSessionHarness is not configured"
            raise RuntimeError(msg)
        return cls._harness


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


def _deterministic_settings() -> GameSettings:
    """Produce deterministic settings tuned for the end-to-end scenario."""

    return GameSettings(
        start_factory_count=2,
        max_months=2,
        basic_factory_monthly_expenses=500.0,
        auto_factory_monthly_expenses=800.0,
        raw_material_monthly_expenses=100.0,
        finished_good_monthly_expenses=150.0,
        basic_factory_launch_cost=400.0,
        auto_factory_launch_cost=600.0,
        bank_start_money=100_000.0,
        loans_monthly_expenses_in_percents=0.01,
        available_loans=[2_000.0, 3_000.0],
        loan_terms_in_months=[1, 2],
        bank_raw_material_sell_volume_range=(3, 3),
        bank_finished_good_buy_volume_range=(3, 3),
        bank_raw_material_sell_min_price_range=(200.0, 200.0),
        bank_finished_good_buy_max_price_range=(500.0, 500.0),
        month_for_upgrade=1,
        upgrade_cost=2_000.0,
        month_for_build_basic=1,
        build_basic_cost=5_000.0,
        month_for_build_auto=1,
        build_auto_cost=7_000.0,
        build_basic_payment_share=0.5,
        build_basic_final_payment_offset=0,
        build_auto_payment_share=0.5,
        build_auto_final_payment_offset=0,
        max_raw_material_storage=8,
        max_finished_good_storage=8,
        max_factories=6,
    )


@contextmanager
def _shared_session_patches(
    monkeypatch: pytest.MonkeyPatch,
    settings: GameSettings,
    session_code: str,
    *,
    expected_connections: int = 2,
) -> Generator[Callable[[GamePhase], None], None, None]:
    harness = SharedSessionHarness(
        settings=settings,
        session_code=session_code,
        expected_connections=expected_connections,
    )
    release_phase = harness.patch(monkeypatch)
    try:
        yield release_phase
    finally:
        harness.cleanup()


def _expect_ack(ws: WebSocketTestSession, phase: GamePhase, action: str) -> None:
    ack = ws.receive_json()
    assert ack["type"] == "action_ack"
    assert ack["phase"] == phase
    assert ack["action"] == action


def _journal_entries(
    reports_by_phase: dict[tuple[int, GamePhase], PhaseReport],
    month: int,
    phase: GamePhase,
    message: str,
) -> list[dict[str, Any]]:
    report = reports_by_phase[(month, phase)]
    return [entry.payload for entry in report.journal if entry.message == message]


def _assert_month_one_reports(
    reports_by_phase: dict[tuple[int, GamePhase], PhaseReport],
) -> None:
    expenses_entries = _journal_entries(
        reports_by_phase, 1, GamePhase.EXPENSES, "expenses_deducted"
    )
    assert {entry["player_id"] for entry in expenses_entries} == {101, 202}
    for entry in expenses_entries:
        assert entry["cash_after"] == pytest.approx(13_750.0)

    market_entry = _journal_entries(
        reports_by_phase, 1, GamePhase.MARKET, "market_announced"
    )[0]
    assert market_entry == {
        "raw_material_volume": 3,
        "finished_good_volume": 3,
        "raw_material_min_price": 200.0,
        "finished_good_max_price": 500.0,
    }

    buy_entries = _journal_entries(
        reports_by_phase, 1, GamePhase.BUY, "buy_bid_fulfilled"
    )
    assert {entry["player_id"] for entry in buy_entries} == {101, 202}
    assert any(
        entry["units"] == 2 for entry in buy_entries if entry["player_id"] == 101
    )
    assert any(
        entry["units"] == 1 for entry in buy_entries if entry["player_id"] == 202
    )

    production_entries = _journal_entries(
        reports_by_phase, 1, GamePhase.PRODUCTION, "production_launched"
    )
    assert {entry["player_id"] for entry in production_entries} == {101, 202}
    assert any(
        entry["produced_units"] == 2
        for entry in production_entries
        if entry["player_id"] == 101
    )
    assert any(
        entry["produced_units"] == 1
        for entry in production_entries
        if entry["player_id"] == 202
    )

    sell_entries = _journal_entries(
        reports_by_phase, 1, GamePhase.SELL, "sell_bid_cleared"
    )
    assert {entry["player_id"] for entry in sell_entries} == {101, 202}
    assert any(
        entry["units"] == 2 for entry in sell_entries if entry["player_id"] == 101
    )
    assert any(
        entry["units"] == 1 for entry in sell_entries if entry["player_id"] == 202
    )

    loan_entries = _journal_entries(
        reports_by_phase, 1, GamePhase.LOANS, "loan_activity"
    )
    loan_p1 = next(entry for entry in loan_entries if entry["player_id"] == 101)
    loan_p2 = next(entry for entry in loan_entries if entry["player_id"] == 202)
    assert loan_p1["interest_paid"] == pytest.approx(10.0)
    assert loan_p1["principal_paid"] == pytest.approx(1_000.0)
    assert loan_p1["loans_issued"] == []
    assert loan_p2["loans_issued"] == [pytest.approx(2_000.0)]

    construction_entries = _journal_entries(
        reports_by_phase, 1, GamePhase.CONSTRUCTION, "construction_started"
    )
    assert {entry["player_id"] for entry in construction_entries} == {101, 202}
    assert any(
        entry["project"] == "build_basic"
        for entry in construction_entries
        if entry["player_id"] == 101
    )
    assert any(
        entry["project"] == "upgrade"
        for entry in construction_entries
        if entry["player_id"] == 202
    )

    month_close = _journal_entries(
        reports_by_phase, 1, GamePhase.END_MONTH, "month_closed"
    )[0]
    assert month_close["seniority_order"] == [202, 101]


def _assert_month_two_reports(
    reports_by_phase: dict[tuple[int, GamePhase], PhaseReport],
) -> None:
    expenses_entries = _journal_entries(
        reports_by_phase, 2, GamePhase.EXPENSES, "expenses_deducted"
    )
    assert {entry["player_id"] for entry in expenses_entries} == {101, 202}
    assert any(
        entry["cash_after"] == pytest.approx(8_150.0)
        for entry in expenses_entries
        if entry["player_id"] == 101
    )
    assert any(
        entry["cash_after"] == pytest.approx(12_330.0)
        for entry in expenses_entries
        if entry["player_id"] == 202
    )

    buy_entries = _journal_entries(
        reports_by_phase, 2, GamePhase.BUY, "buy_bid_fulfilled"
    )
    assert {entry["player_id"] for entry in buy_entries} == {101, 202}
    assert any(
        entry["units"] == 1 for entry in buy_entries if entry["player_id"] == 101
    )
    assert any(
        entry["units"] == 2 for entry in buy_entries if entry["player_id"] == 202
    )

    production_entries = _journal_entries(
        reports_by_phase, 2, GamePhase.PRODUCTION, "production_launched"
    )
    assert {entry["player_id"] for entry in production_entries} == {101, 202}

    sell_entries = _journal_entries(
        reports_by_phase, 2, GamePhase.SELL, "sell_bid_cleared"
    )
    assert {entry["player_id"] for entry in sell_entries} == {101, 202}

    loan_entries = _journal_entries(
        reports_by_phase, 2, GamePhase.LOANS, "loan_activity"
    )
    loan_p2 = next(entry for entry in loan_entries if entry["player_id"] == 202)
    assert loan_p2["interest_paid"] == pytest.approx(20.0)
    assert loan_p2["principal_paid"] == pytest.approx(2_000.0)

    construction_payments = _journal_entries(
        reports_by_phase, 2, GamePhase.CONSTRUCTION, "construction_payment"
    )
    assert any(
        entry["player_id"] == 101 and entry["amount"] == pytest.approx(2_500.0)
        for entry in construction_payments
    )

    construction_completed = _journal_entries(
        reports_by_phase, 2, GamePhase.CONSTRUCTION, "construction_completed"
    )
    assert {entry["player_id"] for entry in construction_completed} == {101, 202}
    assert any(
        entry["result"] == "basic"
        for entry in construction_completed
        if entry["player_id"] == 101
    )
    assert any(
        entry["result"] == "upgrade"
        for entry in construction_completed
        if entry["player_id"] == 202
    )

    month_close = _journal_entries(
        reports_by_phase, 2, GamePhase.END_MONTH, "month_closed"
    )[0]
    assert month_close["bankrupt_players"] == []
    assert month_close["seniority_order"] == [101, 202]


def _register_player(client: TestClient, nickname: str) -> str:
    payload = {"nickname": nickname, "password": "Password123", "icon": "astronaut"}
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    return data["token"]["access_token"]


def test_two_player_websocket_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drive a full two-month session with two players over WebSockets."""

    settings = _deterministic_settings()
    session_code = "websock42"

    with _shared_session_patches(monkeypatch, settings, session_code) as release_phase:
        tokens = {
            "Alpha": _register_player(client, "Alpha"),
            "Beta": _register_player(client, "Beta"),
        }

        session_router._CURRENT_TEST_SESSION_CODE = session_code
        with (
            client.websocket_connect(f"/ws/game?token={tokens['Alpha']}") as ws_alpha,
            client.websocket_connect(f"/ws/game?token={tokens['Beta']}") as ws_beta,
        ):
            ws_alpha.send_json({"type": "join", "session_code": session_code})
            welcome_alpha = ws_alpha.receive_json()
            assert welcome_alpha["type"] == "welcome"
            assert welcome_alpha["phase"] == GamePhase.EXPENSES

            session_router._CURRENT_TEST_SESSION_CODE = session_code
            ws_beta.send_json({"type": "join", "session_code": session_code})
            welcome_beta = ws_beta.receive_json()
            assert welcome_beta["type"] == "welcome"
            assert welcome_beta["phase"] == GamePhase.EXPENSES

            player_sockets = {"Alpha": ws_alpha, "Beta": ws_beta}
            reports: list[PhaseReport] = []
            current_month = 1

            phase_scripts: dict[int, dict[GamePhase, dict[str, dict[str, Any]]]] = {
                1: {
                    GamePhase.BUY: {
                        "Alpha": {
                            "kind": "submit_buy_bid",
                            "quantity": 2,
                            "price": 250.0,
                        },
                        "Beta": {
                            "kind": "submit_buy_bid",
                            "quantity": 2,
                            "price": 250.0,
                        },
                    },
                    GamePhase.PRODUCTION: {
                        "Alpha": {"kind": "production_plan", "basic": 2, "auto": 0},
                        "Beta": {"kind": "production_plan", "basic": 1, "auto": 0},
                    },
                    GamePhase.SELL: {
                        "Alpha": {
                            "kind": "submit_sell_bid",
                            "quantity": 2,
                            "price": 480.0,
                        },
                        "Beta": {
                            "kind": "submit_sell_bid",
                            "quantity": 1,
                            "price": 480.0,
                        },
                    },
                    GamePhase.LOANS: {
                        "Beta": {"kind": "loan_decision", "slot": 0, "decision": "call"}
                    },
                    GamePhase.CONSTRUCTION: {
                        "Alpha": {
                            "kind": "construction_request",
                            "project": "build_basic",
                        },
                        "Beta": {"kind": "construction_request", "project": "upgrade"},
                    },
                },
                2: {
                    GamePhase.BUY: {
                        "Alpha": {
                            "kind": "submit_buy_bid",
                            "quantity": 1,
                            "price": 250.0,
                        },
                        "Beta": {
                            "kind": "submit_buy_bid",
                            "quantity": 2,
                            "price": 250.0,
                        },
                    },
                    GamePhase.PRODUCTION: {
                        "Alpha": {"kind": "production_plan", "basic": 1, "auto": 0},
                        "Beta": {"kind": "production_plan", "basic": 1, "auto": 0},
                    },
                    GamePhase.SELL: {
                        "Alpha": {
                            "kind": "submit_sell_bid",
                            "quantity": 1,
                            "price": 480.0,
                        },
                        "Beta": {
                            "kind": "submit_sell_bid",
                            "quantity": 2,
                            "price": 480.0,
                        },
                    },
                    GamePhase.CONSTRUCTION: {
                        "Alpha": {"kind": "construction_request", "project": "idle"},
                        "Beta": {"kind": "construction_request", "project": "idle"},
                    },
                },
            }

            for expected_phase in PHASE_SEQUENCE * settings.max_months:
                tick_alpha = ws_alpha.receive_json()
                tick_beta = ws_beta.receive_json()
                assert tick_alpha["type"] == "phase_tick"
                assert tick_beta["type"] == "phase_tick"
                assert tick_alpha["tick"]["phase"] == expected_phase
                assert tick_beta["tick"]["phase"] == expected_phase

                actions = phase_scripts.get(current_month, {}).get(expected_phase, {})
                for alias in ("Alpha", "Beta"):
                    payload = actions.get(alias)
                    if payload is None:
                        continue
                    ws = player_sockets[alias]
                    ws.send_json(
                        {
                            "type": "phase_action",
                            "phase": expected_phase,
                            "payload": payload,
                        }
                    )
                    _expect_ack(ws, expected_phase, payload["kind"])

                release_phase(expected_phase)

                report_alpha = ws_alpha.receive_json()
                report_beta = ws_beta.receive_json()
                assert report_alpha == report_beta
                assert report_alpha["type"] == "phase_report"
                assert report_alpha["report"]["phase"] == expected_phase
                reports.append(PhaseReport.model_validate(report_alpha["report"]))

                if expected_phase == GamePhase.END_MONTH:
                    current_month += 1

    reports_by_phase = {(report.month, report.phase): report for report in reports}

    _assert_month_one_reports(reports_by_phase)
    _assert_month_two_reports(reports_by_phase)
