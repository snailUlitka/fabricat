"""Immutable value objects shared across the domain layer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence  # noqa: TC003
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator
from pydantic.config import ConfigDict

_CURRENCY_QUANTIZE = Decimal("0.01")


class Money(BaseModel):
    """Representation of monetary values with fixed precision."""

    model_config = ConfigDict(frozen=True)

    amount: Decimal = Field(
        ..., description="Monetary amount expressed in whole currency units."
    )
    currency: str = Field(
        default="USD", min_length=3, max_length=3, description="ISO-like currency code."
    )

    @model_validator(mode="after")
    def _normalize_amount(self) -> Money:
        """Ensure the amount is rounded to two decimal places and currency uppercase."""
        quantized = self.amount.quantize(_CURRENCY_QUANTIZE, rounding=ROUND_HALF_UP)
        object.__setattr__(self, "amount", quantized)
        object.__setattr__(self, "currency", self.currency.upper())
        return self

    def add(self, other: Money) -> Money:
        """Return a new instance with *other* added to this monetary value."""
        self._assert_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        """Return a new instance with *other* subtracted from this monetary value."""
        self._assert_same_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def multiply(self, factor: Decimal | int) -> Money:
        """Scale the amount by *factor* while preserving rounding rules."""
        decimal_factor = factor if isinstance(factor, Decimal) else Decimal(factor)
        new_amount = (self.amount * decimal_factor).quantize(
            _CURRENCY_QUANTIZE, rounding=ROUND_HALF_UP
        )
        return Money(amount=new_amount, currency=self.currency)

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            msg = f"Currency mismatch: {self.currency} vs {other.currency}."
            raise ValueError(msg)


class ResourceType(StrEnum):
    """Enumeration describing supported resource categories."""

    RAW_MATERIAL = "raw_material"
    FINISHED_GOOD = "finished_good"


class ResourceQuantity(BaseModel):
    """Immutable quantity for a specific resource type."""

    model_config = ConfigDict(frozen=True)

    resource: ResourceType
    amount: int = Field(..., ge=0)

    def increase(self, delta: int) -> ResourceQuantity:
        """Return a quantity increased by *delta*."""
        if delta < 0:
            msg = "Increase delta must be non-negative."
            raise ValueError(msg)
        return ResourceQuantity(resource=self.resource, amount=self.amount + delta)

    def decrease(self, delta: int) -> ResourceQuantity:
        """Return a quantity decreased by *delta*, ensuring non-negative result."""
        if delta < 0:
            msg = "Decrease delta must be non-negative."
            raise ValueError(msg)
        new_amount = self.amount - delta
        if new_amount < 0:
            msg = f"Resource {self.resource} would become negative ({new_amount})."
            raise ValueError(msg)
        return ResourceQuantity(resource=self.resource, amount=new_amount)


class SeniorityOrder(BaseModel):
    """Represents the ordering of companies for tie-breaking and auctions."""

    model_config = ConfigDict(frozen=True)

    ranking: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_unique(self) -> SeniorityOrder:
        """Ensure each company identifier appears at most once."""
        if len(self.ranking) != len(set(self.ranking)):
            msg = "Seniority ranking must not contain duplicates."
            raise ValueError(msg)
        return self

    def rotate(self, steps: int = 1) -> SeniorityOrder:
        """Rotate the order forward by *steps* positions (cyclic)."""
        if not self.ranking:
            return self
        normalized = steps % len(self.ranking)
        if normalized == 0:
            return self
        rotated = self.ranking[normalized:] + self.ranking[:normalized]
        return SeniorityOrder(ranking=rotated)

    def promote(self, company_id: str) -> SeniorityOrder:
        """Move *company_id* to the front, preserving the relative order of others."""
        if company_id not in self.ranking:
            msg = f"Unknown company_id '{company_id}' in seniority order."
            raise ValueError(msg)
        reordered = (
            company_id,
            *(identifier for identifier in self.ranking if identifier != company_id),
        )
        return SeniorityOrder(ranking=reordered)


class PhaseIdentifier(StrEnum):
    """Enumeration of the phases executed during a monthly tick."""

    EXPENSES = "expenses"
    MARKET_ANNOUNCEMENT = "market_announcement"
    RAW_MATERIAL_PURCHASE = "raw_material_purchase"
    PRODUCTION = "production"
    FINISHED_GOODS_SALE = "finished_goods_sale"
    LOAN_MANAGEMENT = "loan_management"
    CONSTRUCTION = "construction"
    END_OF_MONTH = "end_of_month"


class PhaseSequence(BaseModel):
    """Immutable list of phase identifiers executed during a month."""

    model_config = ConfigDict(frozen=True)

    phases: tuple[PhaseIdentifier, ...]

    def ensure_contains(self, required: Sequence[PhaseIdentifier]) -> None:
        """Validate that every required phase is present in the sequence."""
        missing = [phase for phase in required if phase not in self.phases]
        if missing:
            phase_list = ", ".join(phase.value for phase in missing)
            msg = f"Missing required phases: {phase_list}"
            raise ValueError(msg)

    def as_mapping(self) -> Mapping[PhaseIdentifier, int]:
        """Return a mapping from phase identifier to its index position."""
        return {phase: index for index, phase in enumerate(self.phases)}


__all__ = [
    "Money",
    "PhaseIdentifier",
    "PhaseSequence",
    "ResourceQuantity",
    "ResourceType",
    "SeniorityOrder",
]
