"""Phase orchestration utilities for Fabricat gameplay."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
else:  # pragma: no cover - runtime fallback
    AsyncIterator = Any

from pydantic import BaseModel, Field


class GamePhase(StrEnum):
    """Enumeration of strict monthly phases."""

    EXPENSES = "expenses"
    MARKET = "market"
    BUY = "buy"
    PRODUCTION = "production"
    SELL = "sell"
    LOANS = "loans"
    CONSTRUCTION = "construction"
    END_MONTH = "end_month"


PHASE_SEQUENCE: tuple[GamePhase, ...] = (
    GamePhase.EXPENSES,
    GamePhase.MARKET,
    GamePhase.BUY,
    GamePhase.PRODUCTION,
    GamePhase.SELL,
    GamePhase.LOANS,
    GamePhase.CONSTRUCTION,
    GamePhase.END_MONTH,
)

DEFAULT_PHASE_DURATION_SECONDS = 60


class PhaseTick(BaseModel):
    """Single countdown tick delivered to clients."""

    phase: GamePhase
    remaining_seconds: int
    total_seconds: int
    started_at: datetime


class PhaseJournalEntry(BaseModel):
    """Structured action log entry for a phase."""

    month: int
    phase: GamePhase
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class PlayerPhaseAnalytics(BaseModel):
    """Compact per-player snapshot shared with the front-end."""

    player_id: int
    money: float
    raw_materials: int
    finished_goods: int
    factories: int
    bankrupt: bool
    active_loans: int


class PhaseAnalytics(BaseModel):
    """Aggregated analytics block accompanying a phase report."""

    players: list[PlayerPhaseAnalytics]
    bankrupt_players: list[int] = Field(default_factory=list)


class PhaseReport(BaseModel):
    """Result payload published once a phase finishes."""

    phase: GamePhase
    month: int
    completed_at: datetime
    journal: list[PhaseJournalEntry]
    analytics: PhaseAnalytics


class PhaseTimer:
    """Asynchronous countdown helper used by the WebSocket API."""

    def __init__(
        self,
        *,
        default_duration_seconds: int = DEFAULT_PHASE_DURATION_SECONDS,
        tick_resolution_seconds: float = 1.0,
    ) -> None:
        if default_duration_seconds < 0:
            msg = "Phase duration must be non-negative."
            raise ValueError(msg)

        if tick_resolution_seconds < 0:
            msg = "Tick resolution must be non-negative."
            raise ValueError(msg)

        self._default_duration = default_duration_seconds
        self._resolution = tick_resolution_seconds
        self._cancel_event: asyncio.Event | None = None

    async def ticks(
        self,
        *,
        phase: GamePhase,
        duration_seconds: int | None = None,
    ) -> AsyncIterator[PhaseTick]:
        """Yield countdown ticks until completion or cancellation."""
        total = (
            duration_seconds if duration_seconds is not None else self._default_duration
        )
        if total < 0:
            msg = "Phase duration must be non-negative."
            raise ValueError(msg)

        cancel_event = asyncio.Event()
        self._cancel_event = cancel_event
        started_at = datetime.now(tz=UTC)
        remaining = total

        while remaining >= 0:
            yield PhaseTick(
                phase=phase,
                remaining_seconds=remaining,
                total_seconds=total,
                started_at=started_at,
            )

            if remaining == 0 or cancel_event.is_set():
                break

            try:
                await asyncio.wait_for(cancel_event.wait(), timeout=self._resolution)
            except TimeoutError:
                remaining -= 1
                continue

            if cancel_event.is_set():
                break

        self._cancel_event = None

    def cancel(self) -> None:
        """Stop the active countdown, if any."""
        if self._cancel_event is not None:
            self._cancel_event.set()


__all__ = [
    "DEFAULT_PHASE_DURATION_SECONDS",
    "PHASE_SEQUENCE",
    "GamePhase",
    "PhaseAnalytics",
    "PhaseJournalEntry",
    "PhaseReport",
    "PhaseTick",
    "PhaseTimer",
    "PlayerPhaseAnalytics",
]
