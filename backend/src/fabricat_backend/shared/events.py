"""Event and decision logging primitives shared across the backend."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict

from fabricat_backend.shared.value_objects import PhaseIdentifier  # noqa: TC001


class LoggedEvent(BaseModel):
    """Represents a single immutable log entry produced during phase execution."""

    model_config = ConfigDict(frozen=True)

    month_index: int = Field(..., ge=0)
    phase: PhaseIdentifier
    event_type: str = Field(..., min_length=1)
    message: str | None = None
    company_id: str | None = Field(default=None, min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionRecord(BaseModel):
    """Captures an immutable snapshot of a player's submitted decision."""

    model_config = ConfigDict(frozen=True)

    month_index: int = Field(..., ge=0)
    phase: PhaseIdentifier
    company_id: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class PhaseLog(BaseModel):
    """Container bundling all notable events and decisions for a phase."""

    model_config = ConfigDict(frozen=True)

    phase: PhaseIdentifier
    month_index: int = Field(..., ge=0)
    decisions: tuple[DecisionRecord, ...] = Field(default_factory=tuple)
    events: tuple[LoggedEvent, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _ensure_alignment(self) -> PhaseLog:
        """Ensure decision and event metadata align with the log metadata."""
        for decision in self.decisions:
            if (
                decision.phase is not self.phase
                or decision.month_index != self.month_index
            ):
                msg = "Decision metadata does not match the owning PhaseLog."
                raise ValueError(msg)
        for event in self.events:
            if event.phase is not self.phase or event.month_index != self.month_index:
                msg = "Event metadata does not match the owning PhaseLog."
                raise ValueError(msg)
        return self


class MonthLog(BaseModel):
    """Aggregated log output produced by the month engine."""

    model_config = ConfigDict(frozen=True)

    month_index: int = Field(..., ge=0)
    phases: tuple[PhaseLog, ...] = Field(default_factory=tuple)

    def append(self, log: PhaseLog) -> MonthLog:
        """Return a new :class:`MonthLog` with *log* appended."""
        if log.month_index != self.month_index:
            msg = "PhaseLog month index must match MonthLog."
            raise ValueError(msg)
        return MonthLog(month_index=self.month_index, phases=(*self.phases, log))


__all__ = [
    "DecisionRecord",
    "LoggedEvent",
    "MonthLog",
    "PhaseLog",
]
