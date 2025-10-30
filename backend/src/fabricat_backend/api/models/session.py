"""Pydantic models describing the WebSocket game session protocol."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fabricat_backend.shared.value_objects import PhaseIdentifier


class GameSessionDecisionRequest(BaseModel):
    """Encapsulates a single decision submitted by the client."""

    model_config = ConfigDict(populate_by_name=True)

    company_id: str | None = Field(default=None, alias="companyId")
    payload: dict[str, Any] = Field(default_factory=dict)


class GameSessionJoinRequest(BaseModel):
    """Explicit request for the current session snapshot."""

    action: Literal["join"]


class GameSessionSubmitDecisionsRequest(BaseModel):
    """Request carrying decisions for a specific phase."""

    action: Literal["submit_decisions"]
    phase: str
    decisions: list[GameSessionDecisionRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_phase(self) -> GameSessionSubmitDecisionsRequest:
        """Ensure the provided phase identifier is valid."""
        try:
            normalized = PhaseIdentifier(self.phase).value
        except ValueError as exc:  # pragma: no cover - defensive guard
            message = f"Unknown phase '{self.phase}'."
            raise ValueError(message) from exc
        object.__setattr__(self, "phase", normalized)
        return self


class GameSessionAdvanceMonthRequest(BaseModel):
    """Request to advance the simulation by one month."""

    action: Literal["advance_month"]


GameSessionRequest = Annotated[
    GameSessionJoinRequest
    | GameSessionSubmitDecisionsRequest
    | GameSessionAdvanceMonthRequest,
    Field(discriminator="action"),
]


class GameSessionSettingsResponse(BaseModel):
    """Message broadcasting the fixed economic configuration for a session."""

    type: Literal["session_settings"]
    session_id: str
    configuration: dict[str, Any]


class GameSessionStateResponse(BaseModel):
    """Message broadcasting the latest snapshot and accumulated logs."""

    type: Literal["session_state"]
    session_id: str
    snapshot: dict[str, Any]
    logs: list[dict[str, Any]] = Field(default_factory=list)


class GameSessionDecisionsStoredResponse(BaseModel):
    """Acknowledgement that a batch of decisions has been stored."""

    type: Literal["decisions_stored"]
    session_id: str
    phase: str
    decisions: list[dict[str, Any]] = Field(default_factory=list)


class GameSessionMonthResultResponse(BaseModel):
    """Message broadcasting the result of a month execution."""

    type: Literal["month_result"]
    session_id: str
    result: dict[str, Any]
    snapshot: dict[str, Any]
    log: dict[str, Any]


class GameSessionAckResponse(BaseModel):
    """Generic acknowledgement message for commands without payloads."""

    type: Literal["ack"]
    action: str
    detail: str | None = None


class GameSessionErrorResponse(BaseModel):
    """Error message emitted when a request fails validation."""

    type: Literal["error"]
    message: str
    detail: str | None = None


__all__ = [
    "GameSessionAckResponse",
    "GameSessionAdvanceMonthRequest",
    "GameSessionDecisionRequest",
    "GameSessionDecisionsStoredResponse",
    "GameSessionErrorResponse",
    "GameSessionJoinRequest",
    "GameSessionMonthResultResponse",
    "GameSessionRequest",
    "GameSessionSettingsResponse",
    "GameSessionStateResponse",
    "GameSessionSubmitDecisionsRequest",
]
