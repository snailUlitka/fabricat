"""Game session orchestration service exposed to the API layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fabricat_backend.game_logic import (
    CompanyState,
    ConstructionPhaseHandlerImpl,
    EndOfMonthPhaseHandlerImpl,
    ExpensesPhaseHandlerImpl,
    FinishedGoodsSalePhaseHandlerImpl,
    GameStateSnapshot,
    InMemoryGameStateStore,
    InMemoryMonthLogStore,
    LoanManagementPhaseHandlerImpl,
    MarketAnnouncementPhaseHandlerImpl,
    MonthResult,
    PhaseHandlers,
    ProductionPhaseHandlerImpl,
    RawMaterialPurchasePhaseHandlerImpl,
    SessionOrchestrator,
    build_lobby_configuration,
)
from fabricat_backend.game_logic.state import (
    FactoryPortfolio,
    FactoryRecord,
    FactoryStatus,
    InventoryLedger,
)
from fabricat_backend.shared import (
    DecisionRecord,
    DeterministicRandomService,
    MonthLog,
    PhaseIdentifier,
    ResourceType,
    SeniorityOrder,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from fabricat_backend.game_logic.configuration import EconomyConfiguration
    from fabricat_backend.game_logic.persistence import GameStateStore, MonthLogStore


@dataclass(slots=True)
class DecisionSubmission:
    """Simplified structure describing a decision submitted by a client."""

    company_id: str | None
    payload: dict[str, Any]


class GameSessionService:
    """Manage in-memory game sessions and delegate to the orchestration layer."""

    def __init__(
        self,
        *,
        orchestrator: SessionOrchestrator,
        state_store: GameStateStore,
        log_store: MonthLogStore,
    ) -> None:
        self._orchestrator = orchestrator
        self._state_store = state_store
        self._log_store = log_store

    @classmethod
    def create_default(cls) -> GameSessionService:
        """Return a service instance configured with default handlers."""
        state_store = InMemoryGameStateStore()
        log_store = InMemoryMonthLogStore()
        handlers = PhaseHandlers(
            expenses=ExpensesPhaseHandlerImpl(),
            market_announcement=MarketAnnouncementPhaseHandlerImpl(),
            raw_material_purchase=RawMaterialPurchasePhaseHandlerImpl(),
            production=ProductionPhaseHandlerImpl(),
            finished_goods_sale=FinishedGoodsSalePhaseHandlerImpl(),
            loan_management=LoanManagementPhaseHandlerImpl(),
            construction=ConstructionPhaseHandlerImpl(),
            end_of_month=EndOfMonthPhaseHandlerImpl(),
        )
        rng_service = DeterministicRandomService()
        orchestrator = SessionOrchestrator(
            handlers,
            state_store=state_store,
            log_store=log_store,
            rng_service=rng_service,
        )
        return cls(
            orchestrator=orchestrator, state_store=state_store, log_store=log_store
        )

    def ensure_session(self, session_id: str, *, company_id: str) -> GameStateSnapshot:
        """Return the active snapshot for *session_id*, creating it if needed."""
        snapshot = self._state_store.load_snapshot(session_id)
        if snapshot is not None:
            return snapshot

        configuration = build_lobby_configuration()
        inventory = InventoryLedger().apply_delta(ResourceType.RAW_MATERIAL, 8)
        company_state = CompanyState(
            company_id=company_id,
            cash=configuration.starting_cash,
            inventory=inventory,
            factories=FactoryPortfolio(
                active=(
                    FactoryRecord(
                        identifier=f"{company_id}-factory-1",
                        blueprint_id="basic",
                        status=FactoryStatus.ACTIVE,
                        months_remaining=None,
                    ),
                ),
            ),
            loans=(),
        )
        snapshot = GameStateSnapshot(
            month_index=0,
            configuration=configuration,
            companies={company_id: company_state},
            seniority_order=SeniorityOrder(ranking=(company_id,)),
        )
        return self._orchestrator.start_session(session_id, snapshot)

    def submit_phase_decisions(
        self,
        session_id: str,
        phase: PhaseIdentifier,
        decisions: Iterable[DecisionSubmission],
        *,
        default_company_id: str,
    ) -> tuple[DecisionRecord, ...]:
        """Persist *decisions* for the current month of *session_id*."""
        snapshot = self._require_snapshot(session_id)
        records = []
        for submission in decisions:
            company_id = submission.company_id or default_company_id
            if company_id not in snapshot.companies:
                msg = f"Unknown company '{company_id}' for session {session_id}."
                raise ValueError(msg)
            records.append(
                DecisionRecord(
                    month_index=snapshot.month_index,
                    phase=phase,
                    company_id=company_id,
                    payload=dict(submission.payload),
                )
            )
        return self._orchestrator.submit_phase_decisions(session_id, phase, records)

    def advance_month(self, session_id: str) -> MonthResult:
        """Advance the session by one month and return the resulting summary."""
        return self._orchestrator.advance_month(session_id)

    def get_snapshot(self, session_id: str) -> GameStateSnapshot:
        """Return the current snapshot for *session_id*."""
        return self._require_snapshot(session_id)

    def get_logs(self, session_id: str) -> tuple[MonthLog, ...]:
        """Return the stored month logs for *session_id*."""
        return self._log_store.fetch_logs(session_id)

    @staticmethod
    def serialize_snapshot(snapshot: GameStateSnapshot) -> dict[str, Any]:
        """Return a JSON-serializable mapping describing *snapshot*."""
        return snapshot.model_dump(mode="json")

    @staticmethod
    def serialize_configuration(
        configuration: EconomyConfiguration,
    ) -> dict[str, Any]:
        """Return a JSON-serializable mapping describing *configuration*."""
        return configuration.model_dump(mode="json")

    @staticmethod
    def serialize_log(log: MonthLog) -> dict[str, Any]:
        """Return a JSON-serializable mapping describing *log*."""
        return log.model_dump(mode="json")

    @staticmethod
    def serialize_month_result(result: MonthResult) -> dict[str, Any]:
        """Return a JSON-friendly representation of *result*."""
        return result.model_dump(mode="json")

    @staticmethod
    def serialize_decisions(
        decisions: Iterable[DecisionRecord],
    ) -> list[dict[str, Any]]:
        """Return JSON-serializable payloads for stored decision records."""
        return [decision.model_dump(mode="json") for decision in decisions]

    def _require_snapshot(self, session_id: str) -> GameStateSnapshot:
        snapshot = self._state_store.load_snapshot(session_id)
        if snapshot is None:
            msg = f"Session '{session_id}' has not been initialized."
            raise RuntimeError(msg)
        return snapshot


__all__ = ["DecisionSubmission", "GameSessionService"]
