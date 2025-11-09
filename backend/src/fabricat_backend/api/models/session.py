"""Pydantic models for the gameplay WebSocket contract."""

# ruff: noqa: TC001

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from fabricat_backend.game_logic.phases import (
    GamePhase,
    PhaseAnalytics,
    PhaseReport,
    PhaseTick,
)
from fabricat_backend.game_logic.session import (
    Bid,
    SeniorityRollLogEntry,
    SenioritySnapshot,
)


class SubmitBuyBidPayload(BaseModel):
    """Client request to submit a raw-material buy bid."""

    kind: Literal["submit_buy_bid"]
    quantity: int = Field(ge=0)
    price: float = Field(gt=0)

    def to_bid(self) -> Bid:
        """Convert payload into a Bid model."""
        return Bid(quantity=self.quantity, price=self.price)


class SubmitSellBidPayload(BaseModel):
    """Client request to submit a finished-good sell bid."""

    kind: Literal["submit_sell_bid"]
    quantity: int = Field(ge=0)
    price: float = Field(gt=0)

    def to_bid(self) -> Bid:
        """Convert payload into a Bid model."""
        return Bid(quantity=self.quantity, price=self.price)


class ProductionPlanPayload(BaseModel):
    """Production plan update for the current month."""

    kind: Literal["production_plan"]
    basic: int = Field(ge=0, le=9_999)
    auto: int = Field(ge=0, le=9_999)


class LoanDecisionPayload(BaseModel):
    """Request to change the status of a specific loan slot."""

    kind: Literal["loan_decision"]
    slot: int = Field(ge=0)
    decision: Literal["call", "skip"]


class ConstructionRequestPayload(BaseModel):
    """Request to build or upgrade factories."""

    kind: Literal["construction_request"]
    project: Literal["build_basic", "build_auto", "upgrade", "idle"]


class SkipActionPayload(BaseModel):
    """Explicit skip for the phase."""

    kind: Literal["skip"]


PhaseActionPayload = Annotated[
    SubmitBuyBidPayload
    | SubmitSellBidPayload
    | ProductionPlanPayload
    | LoanDecisionPayload
    | ConstructionRequestPayload
    | SkipActionPayload,
    Field(discriminator="kind"),
]


class JoinSessionRequest(BaseModel):
    """First message sent by the client when connecting."""

    type: Literal["join"]
    session_code: str | None = None


class PhaseStatusRequest(BaseModel):
    """Ad-hoc snapshot request."""

    type: Literal["phase_status"]


class HeartbeatRequest(BaseModel):
    """Heartbeat message for connection keep-alive."""

    type: Literal["heartbeat"]
    nonce: str | None = None


class PhaseActionRequest(BaseModel):
    """Phase-bound action submission."""

    type: Literal["phase_action"]
    phase: GamePhase
    payload: PhaseActionPayload


InboundWsMessage = Annotated[
    JoinSessionRequest | PhaseStatusRequest | HeartbeatRequest | PhaseActionRequest,
    Field(discriminator="type"),
]


class SessionWelcomeResponse(BaseModel):
    """Payload sent once the socket is authenticated and ready."""

    type: Literal["welcome"] = "welcome"
    session_code: str
    month: int
    phase: GamePhase
    phase_duration_seconds: int
    analytics: PhaseAnalytics
    seniority: list[SenioritySnapshot]
    tie_break_log: list[SeniorityRollLogEntry]


class PhaseTickResponse(BaseModel):
    """Streaming countdown tick."""

    type: Literal["phase_tick"] = "phase_tick"
    tick: PhaseTick


class PhaseReportResponse(BaseModel):
    """Publication emitted when a phase completes."""

    type: Literal["phase_report"] = "phase_report"
    report: PhaseReport


class ActionAckResponse(BaseModel):
    """Acknowledgement indicating that an action was accepted."""

    type: Literal["action_ack"] = "action_ack"
    phase: GamePhase
    action: str
    detail: dict[str, Any] = Field(default_factory=dict)


class PhaseStatusResponse(BaseModel):
    """Response to ad-hoc status queries."""

    type: Literal["phase_status"] = "phase_status"
    month: int
    phase: GamePhase
    analytics: PhaseAnalytics
    remaining_seconds: int | None = None


class ErrorResponse(BaseModel):
    """Structured error payload."""

    type: Literal["error"] = "error"
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


OutboundWsMessage = Annotated[
    SessionWelcomeResponse
    | PhaseTickResponse
    | PhaseReportResponse
    | ActionAckResponse
    | PhaseStatusResponse
    | ErrorResponse,
    Field(discriminator="type"),
]


__all__ = [
    "ActionAckResponse",
    "ConstructionRequestPayload",
    "ErrorResponse",
    "HeartbeatRequest",
    "InboundWsMessage",
    "JoinSessionRequest",
    "LoanDecisionPayload",
    "OutboundWsMessage",
    "PhaseActionRequest",
    "PhaseReportResponse",
    "PhaseStatusRequest",
    "PhaseStatusResponse",
    "PhaseTickResponse",
    "ProductionPlanPayload",
    "SessionWelcomeResponse",
    "SkipActionPayload",
    "SubmitBuyBidPayload",
    "SubmitSellBidPayload",
]
