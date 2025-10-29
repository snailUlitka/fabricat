"""Phase interfaces and data structures used by the month engine."""

from __future__ import annotations

from collections.abc import (
    Callable,
    Mapping,
)
from dataclasses import dataclass
from decimal import Decimal  # noqa: TC003
from typing import Protocol

from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict

from fabricat_backend.game_logic.configuration import (
    EconomyConfiguration,  # noqa: TC001
)
from fabricat_backend.game_logic.state import CompanyState  # noqa: TC001
from fabricat_backend.shared import DeterministicRandomService  # noqa: TC001
from fabricat_backend.shared.events import (  # noqa: TC001
    DecisionRecord,
    LoggedEvent,
    PhaseLog,
)
from fabricat_backend.shared.value_objects import (
    PhaseIdentifier,
    SeniorityOrder,
)


class PhaseResultBase(BaseModel):
    """Base class for describing the outcome of a phase execution."""

    model_config = ConfigDict(frozen=True)

    phase: PhaseIdentifier
    month_index: int = Field(..., ge=0)
    updated_companies: Mapping[str, CompanyState]
    log: PhaseLog
    summary: str | None = None
    metrics: Mapping[str, float | int | Decimal] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_log_alignment(self) -> PhaseResultBase:
        """Validate that the attached :class:`PhaseLog` matches the phase metadata."""
        if self.log.phase is not self.phase or self.log.month_index != self.month_index:
            msg = "PhaseLog metadata does not match PhaseResult metadata."
            raise ValueError(msg)
        return self


class PhaseInputBase(BaseModel):
    """Immutable payload provided to every phase handler."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    month_index: int = Field(..., ge=0)
    configuration: EconomyConfiguration
    company_states: Mapping[str, CompanyState]
    seniority_order: SeniorityOrder
    decisions: tuple[DecisionRecord, ...] = Field(default_factory=tuple)
    previous_results: tuple[PhaseResultBase, ...] = Field(default_factory=tuple)
    previous_events: tuple[LoggedEvent, ...] = Field(default_factory=tuple)
    rng_service: DeterministicRandomService | None = None


class ExpensesPhaseInput(PhaseInputBase):
    """Input payload for the expenses phase."""


class MarketAnnouncementPhaseInput(PhaseInputBase):
    """Input payload for the market announcement phase."""


class RawMaterialPurchasePhaseInput(PhaseInputBase):
    """Input payload for the raw material purchase phase."""


class ProductionPhaseInput(PhaseInputBase):
    """Input payload for the production phase."""


class FinishedGoodsSalePhaseInput(PhaseInputBase):
    """Input payload for the finished goods sale phase."""


class LoanManagementPhaseInput(PhaseInputBase):
    """Input payload for the loan management phase."""


class ConstructionPhaseInput(PhaseInputBase):
    """Input payload for the construction and upgrade phase."""


class EndOfMonthPhaseInput(PhaseInputBase):
    """Input payload for the end-of-month wrap-up phase."""


class ExpensesPhaseResult(PhaseResultBase):
    """Structured result for the expenses phase."""


class MarketAnnouncementPhaseResult(PhaseResultBase):
    """Structured result for the market announcement phase."""


class RawMaterialPurchasePhaseResult(PhaseResultBase):
    """Structured result for the raw material purchase phase."""


class ProductionPhaseResult(PhaseResultBase):
    """Structured result for the production phase."""


class FinishedGoodsSalePhaseResult(PhaseResultBase):
    """Structured result for the finished goods sale phase."""


class LoanManagementPhaseResult(PhaseResultBase):
    """Structured result for the loan management phase."""


class ConstructionPhaseResult(PhaseResultBase):
    """Structured result for the construction and upgrade phase."""


class EndOfMonthPhaseResult(PhaseResultBase):
    """Structured result for the end-of-month wrap-up phase."""


class ExpensesPhaseHandler(Protocol):
    """Interface implemented by the expenses phase handler."""

    def handle(self, input_data: ExpensesPhaseInput) -> ExpensesPhaseResult:
        """Process the expenses phase and return its result."""


class MarketAnnouncementPhaseHandler(Protocol):
    """Interface implemented by the market announcement phase handler."""

    def handle(
        self, input_data: MarketAnnouncementPhaseInput
    ) -> MarketAnnouncementPhaseResult:
        """Process the market announcement phase and return its result."""


class RawMaterialPurchasePhaseHandler(Protocol):
    """Interface implemented by the raw material purchase phase handler."""

    def handle(
        self, input_data: RawMaterialPurchasePhaseInput
    ) -> RawMaterialPurchasePhaseResult:
        """Process the raw material purchase phase and return its result."""


class ProductionPhaseHandler(Protocol):
    """Interface implemented by the production phase handler."""

    def handle(self, input_data: ProductionPhaseInput) -> ProductionPhaseResult:
        """Process the production phase and return its result."""


class FinishedGoodsSalePhaseHandler(Protocol):
    """Interface implemented by the finished goods sale phase handler."""

    def handle(
        self, input_data: FinishedGoodsSalePhaseInput
    ) -> FinishedGoodsSalePhaseResult:
        """Process the finished goods sale phase and return its result."""


class LoanManagementPhaseHandler(Protocol):
    """Interface implemented by the loan management phase handler."""

    def handle(self, input_data: LoanManagementPhaseInput) -> LoanManagementPhaseResult:
        """Process the loan management phase and return its result."""


class ConstructionPhaseHandler(Protocol):
    """Interface implemented by the construction and upgrade phase handler."""

    def handle(self, input_data: ConstructionPhaseInput) -> ConstructionPhaseResult:
        """Process the construction phase and return its result."""


class EndOfMonthPhaseHandler(Protocol):
    """Interface implemented by the end-of-month wrap-up phase handler."""

    def handle(self, input_data: EndOfMonthPhaseInput) -> EndOfMonthPhaseResult:
        """Process the end-of-month phase and return its result."""


PhaseHandlerCallable = Callable[[PhaseInputBase], PhaseResultBase]


@dataclass(frozen=True)
class PhaseHandlers:
    """Collection of strongly-typed phase handlers for the month engine."""

    expenses: ExpensesPhaseHandler
    market_announcement: MarketAnnouncementPhaseHandler
    raw_material_purchase: RawMaterialPurchasePhaseHandler
    production: ProductionPhaseHandler
    finished_goods_sale: FinishedGoodsSalePhaseHandler
    loan_management: LoanManagementPhaseHandler
    construction: ConstructionPhaseHandler
    end_of_month: EndOfMonthPhaseHandler

    def as_mapping(self) -> dict[PhaseIdentifier, PhaseHandlerCallable]:
        """Return a mapping from :class:`PhaseIdentifier` to handler callables."""
        return {
            PhaseIdentifier.EXPENSES: self.expenses.handle,
            PhaseIdentifier.MARKET_ANNOUNCEMENT: self.market_announcement.handle,
            PhaseIdentifier.RAW_MATERIAL_PURCHASE: self.raw_material_purchase.handle,
            PhaseIdentifier.PRODUCTION: self.production.handle,
            PhaseIdentifier.FINISHED_GOODS_SALE: self.finished_goods_sale.handle,
            PhaseIdentifier.LOAN_MANAGEMENT: self.loan_management.handle,
            PhaseIdentifier.CONSTRUCTION: self.construction.handle,
            PhaseIdentifier.END_OF_MONTH: self.end_of_month.handle,
        }


PHASE_INPUT_TYPES: dict[PhaseIdentifier, type[PhaseInputBase]] = {
    PhaseIdentifier.EXPENSES: ExpensesPhaseInput,
    PhaseIdentifier.MARKET_ANNOUNCEMENT: MarketAnnouncementPhaseInput,
    PhaseIdentifier.RAW_MATERIAL_PURCHASE: RawMaterialPurchasePhaseInput,
    PhaseIdentifier.PRODUCTION: ProductionPhaseInput,
    PhaseIdentifier.FINISHED_GOODS_SALE: FinishedGoodsSalePhaseInput,
    PhaseIdentifier.LOAN_MANAGEMENT: LoanManagementPhaseInput,
    PhaseIdentifier.CONSTRUCTION: ConstructionPhaseInput,
    PhaseIdentifier.END_OF_MONTH: EndOfMonthPhaseInput,
}

PHASE_RESULT_TYPES: dict[PhaseIdentifier, type[PhaseResultBase]] = {
    PhaseIdentifier.EXPENSES: ExpensesPhaseResult,
    PhaseIdentifier.MARKET_ANNOUNCEMENT: MarketAnnouncementPhaseResult,
    PhaseIdentifier.RAW_MATERIAL_PURCHASE: RawMaterialPurchasePhaseResult,
    PhaseIdentifier.PRODUCTION: ProductionPhaseResult,
    PhaseIdentifier.FINISHED_GOODS_SALE: FinishedGoodsSalePhaseResult,
    PhaseIdentifier.LOAN_MANAGEMENT: LoanManagementPhaseResult,
    PhaseIdentifier.CONSTRUCTION: ConstructionPhaseResult,
    PhaseIdentifier.END_OF_MONTH: EndOfMonthPhaseResult,
}


__all__ = [
    "PHASE_INPUT_TYPES",
    "PHASE_RESULT_TYPES",
    "ConstructionPhaseHandler",
    "ConstructionPhaseInput",
    "ConstructionPhaseResult",
    "EndOfMonthPhaseHandler",
    "EndOfMonthPhaseInput",
    "EndOfMonthPhaseResult",
    "ExpensesPhaseHandler",
    "ExpensesPhaseInput",
    "ExpensesPhaseResult",
    "FinishedGoodsSalePhaseHandler",
    "FinishedGoodsSalePhaseInput",
    "FinishedGoodsSalePhaseResult",
    "LoanManagementPhaseHandler",
    "LoanManagementPhaseInput",
    "LoanManagementPhaseResult",
    "MarketAnnouncementPhaseHandler",
    "MarketAnnouncementPhaseInput",
    "MarketAnnouncementPhaseResult",
    "PhaseHandlers",
    "PhaseInputBase",
    "PhaseResultBase",
    "ProductionPhaseHandler",
    "ProductionPhaseInput",
    "ProductionPhaseResult",
    "RawMaterialPurchasePhaseHandler",
    "RawMaterialPurchasePhaseInput",
    "RawMaterialPurchasePhaseResult",
]
