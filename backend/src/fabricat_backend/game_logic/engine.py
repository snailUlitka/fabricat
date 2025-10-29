"""Month orchestration engine coordinating the execution of game phases."""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003

from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict

from fabricat_backend.game_logic.configuration import (
    EconomyConfiguration,  # noqa: TC001
)
from fabricat_backend.game_logic.phases import (
    PHASE_INPUT_TYPES,
    PhaseHandlers,
    PhaseResultBase,
)
from fabricat_backend.game_logic.state import CompanyState  # noqa: TC001
from fabricat_backend.shared import DeterministicRandomService  # noqa: TC001
from fabricat_backend.shared.events import (
    DecisionRecord,
    LoggedEvent,
    MonthLog,
)
from fabricat_backend.shared.value_objects import (  # noqa: TC001
    PhaseIdentifier,
    PhaseSequence,
    SeniorityOrder,
)


class MonthContext(BaseModel):
    """Immutable payload describing the inputs required to run a month."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    month_index: int = Field(..., ge=0)
    configuration: EconomyConfiguration
    company_states: Mapping[str, CompanyState]
    seniority_order: SeniorityOrder
    decisions: Mapping[PhaseIdentifier, tuple[DecisionRecord, ...]] = Field(
        default_factory=dict
    )
    previous_log: MonthLog | None = None
    rng_service: DeterministicRandomService | None = None

    @model_validator(mode="after")
    def _validate_decisions(self) -> MonthContext:
        """Ensure decision metadata matches the context metadata."""
        for phase, records in self.decisions.items():
            for record in records:
                if record.month_index != self.month_index or record.phase is not phase:
                    msg = "Decision metadata does not match MonthContext metadata."
                    raise ValueError(msg)
        if self.previous_log and self.previous_log.month_index != self.month_index:
            msg = "MonthLog month index must match the context month index."
            raise ValueError(msg)
        return self


class MonthResult(BaseModel):
    """Aggregate outcome returned after executing all phases for a month."""

    model_config = ConfigDict(frozen=True)

    month_index: int = Field(..., ge=0)
    configuration: EconomyConfiguration
    final_company_states: Mapping[str, CompanyState]
    phase_results: tuple[PhaseResultBase, ...]
    log: MonthLog

    @model_validator(mode="after")
    def _validate_log_alignment(self) -> MonthResult:
        """Ensure the month log aligns with the result metadata."""
        if self.log.month_index != self.month_index:
            msg = "MonthLog month index must match MonthResult month index."
            raise ValueError(msg)
        return self


class MonthEngine:
    """Coordinate execution of all month phases in the configured order."""

    def __init__(
        self,
        handlers: PhaseHandlers,
        *,
        rng_service: DeterministicRandomService | None = None,
    ) -> None:
        self._handlers = handlers
        self._rng_service = rng_service

    def run_month(self, context: MonthContext) -> MonthResult:
        """Execute every configured phase for *context* and return a month summary."""
        handler_map = self._handlers.as_mapping()
        phase_sequence: PhaseSequence = context.configuration.phase_sequence
        missing = [phase for phase in phase_sequence.phases if phase not in handler_map]
        if missing:
            phase_labels = ", ".join(phase.value for phase in missing)
            msg = f"No handlers registered for phases: {phase_labels}"
            raise ValueError(msg)

        rng_service = context.rng_service or self._rng_service
        month_log = context.previous_log or MonthLog(month_index=context.month_index)
        events_accumulator: list[LoggedEvent] = [
            event for phase_log in month_log.phases for event in phase_log.events
        ]
        current_states: Mapping[str, CompanyState] = dict(context.company_states)
        phase_results: list[PhaseResultBase] = []

        for phase in phase_sequence.phases:
            input_type = PHASE_INPUT_TYPES[phase]
            handler_callable = handler_map[phase]
            previous_results = tuple(phase_results)
            phase_decisions = context.decisions.get(phase, ())
            phase_input = input_type(
                month_index=context.month_index,
                configuration=context.configuration,
                company_states=current_states,
                seniority_order=context.seniority_order,
                decisions=phase_decisions,
                previous_results=previous_results,
                previous_events=tuple(events_accumulator),
                rng_service=rng_service,
            )
            result = handler_callable(phase_input)
            if result.phase is not phase:
                msg = "Phase handler returned a result tagged with a different phase."
                raise ValueError(msg)
            phase_results.append(result)
            events_accumulator.extend(result.log.events)
            month_log = month_log.append(result.log)
            current_states = result.updated_companies

        return MonthResult(
            month_index=context.month_index,
            configuration=context.configuration,
            final_company_states=current_states,
            phase_results=tuple(phase_results),
            log=month_log,
        )


__all__ = ["MonthContext", "MonthEngine", "MonthResult"]
