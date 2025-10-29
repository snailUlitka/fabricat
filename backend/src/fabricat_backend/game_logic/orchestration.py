"""High-level orchestration helpers connecting the engine to external callers.

This module exposes a thin façade that the API layer can use to manage game
sessions. It coordinates persistence adapters, decision submissions, and the
`MonthEngine` to provide a stable contract for future integrations.
"""

from __future__ import annotations

from collections.abc import Iterable  # noqa: TC003

from fabricat_backend.game_logic.engine import MonthContext, MonthEngine, MonthResult
from fabricat_backend.game_logic.persistence import (
    GameStateSnapshot,
    GameStateStore,
    MonthLogStore,
)
from fabricat_backend.game_logic.phases import PhaseHandlers  # noqa: TC001
from fabricat_backend.shared import (  # noqa: TC001
    DecisionRecord,
    DeterministicRandomService,
)
from fabricat_backend.shared.events import MonthLog  # noqa: TC001
from fabricat_backend.shared.value_objects import (
    PhaseIdentifier,
    SeniorityOrder,
)


class SessionNotInitializedError(RuntimeError):
    """Raised when orchestration is requested for an unknown session."""


class SessionOrchestrator:
    """Coordinate game sessions for the API layer.

    The orchestrator encapsulates the mechanics of running a month, persisting
    state, and collecting decisions. API-facing services can use the public
    methods to create a new session, accept phase submissions, and advance the
    simulation without needing direct access to the underlying engine.
    """

    def __init__(
        self,
        handlers: PhaseHandlers,
        state_store: GameStateStore,
        log_store: MonthLogStore,
        *,
        rng_service: DeterministicRandomService | None = None,
    ) -> None:
        self._engine = MonthEngine(handlers, rng_service=rng_service)
        self._state_store = state_store
        self._log_store = log_store
        self._pending_decisions: dict[
            str, dict[int, dict[PhaseIdentifier, list[DecisionRecord]]]
        ] = {}

    def start_session(
        self,
        session_id: str,
        snapshot: GameStateSnapshot,
    ) -> GameStateSnapshot:
        """Persist the initial *snapshot* for *session_id* and reset state."""
        self._state_store.save_snapshot(session_id, snapshot)
        self._pending_decisions[session_id] = {snapshot.month_index: {}}
        return snapshot

    def submit_phase_decisions(
        self,
        session_id: str,
        phase: PhaseIdentifier,
        decisions: Iterable[DecisionRecord],
    ) -> tuple[DecisionRecord, ...]:
        """Store *decisions* for *phase* in the session's active month."""
        snapshot = self._require_snapshot(session_id)
        month_bucket = self._pending_decisions.setdefault(session_id, {})
        phase_bucket = month_bucket.setdefault(snapshot.month_index, {})
        decision_list = [
            self._validate_decision(snapshot.month_index, phase, decision)
            for decision in decisions
        ]
        phase_bucket[phase] = decision_list
        return tuple(decision_list)

    def advance_month(self, session_id: str) -> MonthResult:
        """Execute the month for *session_id* and persist the resulting state."""
        snapshot = self._require_snapshot(session_id)
        month_decisions = self._pending_decisions.get(session_id, {}).pop(
            snapshot.month_index, {}
        )
        context = MonthContext(
            month_index=snapshot.month_index,
            configuration=snapshot.configuration,
            company_states=snapshot.companies,
            seniority_order=snapshot.seniority_order,
            decisions={
                phase: tuple(decisions)
                for phase, decisions in sorted(
                    month_decisions.items(), key=lambda item: item[0].value
                )
            },
        )
        result = self._engine.run_month(context)

        new_order = self._determine_seniority_order(
            snapshot.seniority_order, result.log
        )
        updated_snapshot = GameStateSnapshot(
            month_index=snapshot.month_index + 1,
            configuration=result.configuration,
            companies=result.final_company_states,
            seniority_order=new_order,
        )
        self._state_store.save_snapshot(session_id, updated_snapshot)
        self._log_store.append_log(session_id, result.log)
        self._pending_decisions.setdefault(session_id, {})[
            updated_snapshot.month_index
        ] = {}
        return result

    def _require_snapshot(self, session_id: str) -> GameStateSnapshot:
        snapshot = self._state_store.load_snapshot(session_id)
        if snapshot is None:
            msg = f"Session '{session_id}' has not been initialized."
            raise SessionNotInitializedError(msg)
        return snapshot

    @staticmethod
    def _validate_decision(
        expected_month: int,
        expected_phase: PhaseIdentifier,
        decision: DecisionRecord,
    ) -> DecisionRecord:
        if decision.month_index != expected_month:
            msg = (
                "Decision month index does not match the active session month: "
                f"{decision.month_index} vs {expected_month}."
            )
            raise ValueError(msg)
        if decision.phase is not expected_phase:
            msg = (
                "Decision phase identifier does not match the submission phase: "
                f"{decision.phase} vs {expected_phase}."
            )
            raise ValueError(msg)
        return decision

    @staticmethod
    def _determine_seniority_order(
        previous_order: SeniorityOrder, log: MonthLog
    ) -> SeniorityOrder:
        """Extract the updated seniority order from the month *log*."""
        for phase_log in log.phases:
            if phase_log.phase is not PhaseIdentifier.END_OF_MONTH:
                continue
            for event in reversed(phase_log.events):
                if event.event_type == "seniority_rotated":
                    payload = event.payload or {}
                    ranking = payload.get("new_order")
                    if isinstance(ranking, (list, tuple)):
                        return SeniorityOrder(ranking=tuple(ranking))
        return previous_order


__all__ = ["SessionNotInitializedError", "SessionOrchestrator"]
