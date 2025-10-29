"""Persistence abstractions for game state and logging snapshots.

These interfaces allow the game logic layer to store the authoritative state of
an ongoing session without depending on the yet-to-be-built database layer. The
API layer can provide concrete adapters (in-memory, database-backed, etc.) that
comply with these protocols.
"""

from __future__ import annotations

from collections.abc import Mapping  # noqa: TC003
from typing import Protocol

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict

from fabricat_backend.game_logic.configuration import (  # noqa: TC001
    EconomyConfiguration,
)
from fabricat_backend.game_logic.state import CompanyState  # noqa: TC001
from fabricat_backend.shared import MonthLog, SeniorityOrder  # noqa: TC001


class GameStateSnapshot(BaseModel):
    """Immutable snapshot representing the state of a running game session."""

    model_config = ConfigDict(frozen=True)

    month_index: int = Field(..., ge=0)
    configuration: EconomyConfiguration
    companies: Mapping[str, CompanyState]
    seniority_order: SeniorityOrder


class GameStateStore(Protocol):
    """Protocol describing how game state snapshots are persisted."""

    def save_snapshot(self, session_id: str, snapshot: GameStateSnapshot) -> None:
        """Persist *snapshot* for *session_id*, replacing any previous value."""

    def load_snapshot(self, session_id: str) -> GameStateSnapshot | None:
        """Return the latest stored snapshot for *session_id* or ``None``."""


class MonthLogStore(Protocol):
    """Protocol describing how month execution logs are persisted."""

    def append_log(self, session_id: str, log: MonthLog) -> None:
        """Persist *log* alongside existing logs for *session_id*."""

    def fetch_logs(self, session_id: str) -> tuple[MonthLog, ...]:
        """Return all stored logs for *session_id* ordered by execution."""


class InMemoryGameStateStore:
    """Trivial in-memory implementation of :class:`GameStateStore`."""

    def __init__(self) -> None:
        self._snapshots: dict[str, GameStateSnapshot] = {}

    def save_snapshot(self, session_id: str, snapshot: GameStateSnapshot) -> None:
        """Store *snapshot* keyed by *session_id*."""
        self._snapshots[session_id] = snapshot

    def load_snapshot(self, session_id: str) -> GameStateSnapshot | None:
        """Return the stored snapshot for *session_id* if available."""
        return self._snapshots.get(session_id)


class InMemoryMonthLogStore:
    """Trivial in-memory implementation of :class:`MonthLogStore`."""

    def __init__(self) -> None:
        self._logs: dict[str, list[MonthLog]] = {}

    def append_log(self, session_id: str, log: MonthLog) -> None:
        """Append *log* to the stored sequence for *session_id*."""
        self._logs.setdefault(session_id, []).append(log)

    def fetch_logs(self, session_id: str) -> tuple[MonthLog, ...]:
        """Return all logs stored for *session_id*."""
        return tuple(self._logs.get(session_id, ()))


__all__ = [
    "GameStateSnapshot",
    "GameStateStore",
    "InMemoryGameStateStore",
    "InMemoryMonthLogStore",
    "MonthLogStore",
]
