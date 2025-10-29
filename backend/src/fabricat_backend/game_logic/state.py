"""Player-centric state containers used by the game logic layer."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, PositiveInt, model_validator
from pydantic.config import ConfigDict

from fabricat_backend.shared.value_objects import Money, ResourceQuantity, ResourceType

if TYPE_CHECKING:
    from collections.abc import Mapping


def _default_inventory() -> tuple[ResourceQuantity, ...]:
    """Return the canonical empty inventory layout."""
    return (
        ResourceQuantity(resource=ResourceType.RAW_MATERIAL, amount=0),
        ResourceQuantity(resource=ResourceType.FINISHED_GOOD, amount=0),
    )


class InventoryLedger(BaseModel):
    """Tracks resource holdings for a company in an immutable fashion."""

    model_config = ConfigDict(frozen=True)

    holdings: tuple[ResourceQuantity, ...] = Field(default_factory=_default_inventory)

    @model_validator(mode="after")
    def _validate_unique_resources(self) -> InventoryLedger:
        """Ensure that each resource type appears at most once."""
        seen = {quantity.resource for quantity in self.holdings}
        if len(seen) != len(self.holdings):
            msg = "Inventory holdings must not contain duplicate resource entries."
            raise ValueError(msg)
        return self

    def quantity(self, resource: ResourceType) -> ResourceQuantity:
        """Return the stored quantity for *resource* (zero when absent)."""
        for quantity in self.holdings:
            if quantity.resource == resource:
                return quantity
        return ResourceQuantity(resource=resource, amount=0)

    def apply_delta(self, resource: ResourceType, delta: int) -> InventoryLedger:
        """Return a new ledger with *delta* applied to the given resource."""
        current = self.quantity(resource)
        updated = current.increase(delta) if delta >= 0 else current.decrease(-delta)
        holdings = {quantity.resource: quantity for quantity in self.holdings}
        holdings[resource] = updated
        ordered = tuple(
            holdings[key] for key in sorted(holdings, key=lambda res: res.value)
        )
        return InventoryLedger(holdings=ordered)

    def apply_many(self, changes: Mapping[ResourceType, int]) -> InventoryLedger:
        """Return a ledger with multiple adjustments applied atomically."""
        ledger = self
        for resource, delta in changes.items():
            ledger = ledger.apply_delta(resource, delta)
        return ledger


class FactoryStatus(StrEnum):
    """Lifecycle stages tracked for factories."""

    ACTIVE = "active"
    UNDER_CONSTRUCTION = "under_construction"
    UPGRADING = "upgrading"


class FactoryRecord(BaseModel):
    """Represents a single factory slot owned by a company."""

    model_config = ConfigDict(frozen=True)

    identifier: str
    blueprint_id: str
    status: FactoryStatus
    months_remaining: PositiveInt | None = None

    @model_validator(mode="after")
    def _validate_timing(self) -> FactoryRecord:
        """Ensure timing metadata matches the status."""
        if self.status is FactoryStatus.ACTIVE and self.months_remaining is not None:
            msg = "Active factories cannot have a remaining-month counter."
            raise ValueError(msg)
        if (
            self.status in {FactoryStatus.UNDER_CONSTRUCTION, FactoryStatus.UPGRADING}
            and self.months_remaining is None
        ):
            msg = "Non-active factories must declare months_remaining."
            raise ValueError(msg)
        return self


class FactoryPortfolio(BaseModel):
    """Immutable collection of factories partitioned by their lifecycle."""

    model_config = ConfigDict(frozen=True)

    active: tuple[FactoryRecord, ...] = Field(default_factory=tuple)
    under_construction: tuple[FactoryRecord, ...] = Field(default_factory=tuple)
    upgrading: tuple[FactoryRecord, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_alignment(self) -> FactoryPortfolio:
        """Ensure that every record resides in the matching bucket."""
        for record in self.active:
            if record.status is not FactoryStatus.ACTIVE:
                msg = f"Record {record.identifier} is misclassified in active bucket."
                raise ValueError(msg)
        for record in self.under_construction:
            if record.status is not FactoryStatus.UNDER_CONSTRUCTION:
                msg = (
                    f"Record {record.identifier} is misclassified in "
                    "construction bucket."
                )
                raise ValueError(msg)
        for record in self.upgrading:
            if record.status is not FactoryStatus.UPGRADING:
                msg = (
                    f"Record {record.identifier} is misclassified in upgrading bucket."
                )
                raise ValueError(msg)
        return self

    def add(self, record: FactoryRecord) -> FactoryPortfolio:
        """Return a portfolio containing *record* in the appropriate bucket."""
        if record.status is FactoryStatus.ACTIVE:
            return FactoryPortfolio(
                active=(*self.active, record),
                under_construction=self.under_construction,
                upgrading=self.upgrading,
            )
        if record.status is FactoryStatus.UNDER_CONSTRUCTION:
            return FactoryPortfolio(
                active=self.active,
                under_construction=(*self.under_construction, record),
                upgrading=self.upgrading,
            )
        return FactoryPortfolio(
            active=self.active,
            under_construction=self.under_construction,
            upgrading=(*self.upgrading, record),
        )

    def total_active_capacity(self) -> int:
        """Return the number of active factories."""
        return len(self.active)


class LoanAccount(BaseModel):
    """Tracks the terms and remaining balance for a company loan."""

    model_config = ConfigDict(frozen=True)

    identifier: str
    principal: Money
    interest_rate: Decimal = Field(ge=0)
    term_months: PositiveInt
    months_remaining: PositiveInt

    def accrue_interest(self) -> LoanAccount:
        """Accrue one month of interest and return an updated loan snapshot."""
        growth = self.principal.multiply(self.interest_rate)
        return LoanAccount(
            identifier=self.identifier,
            principal=self.principal.add(growth),
            interest_rate=self.interest_rate,
            term_months=self.term_months,
            months_remaining=self.months_remaining,
        )

    def advance_schedule(self) -> LoanAccount:
        """Advance the amortization schedule by one month."""
        if self.months_remaining == 1:
            msg = "Cannot advance a fully matured loan."
            raise ValueError(msg)
        return LoanAccount(
            identifier=self.identifier,
            principal=self.principal,
            interest_rate=self.interest_rate,
            term_months=self.term_months,
            months_remaining=self.months_remaining - 1,
        )

    def scheduled_payment(self) -> Money:
        """Return the scheduled payment amount for the upcoming month."""
        divisor = Decimal(self.months_remaining)
        amount = (self.principal.amount / divisor).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return Money(amount=amount, currency=self.principal.currency)

    def apply_payment(self, payment: Money) -> LoanAccount | None:
        """Apply *payment* towards the principal, returning the updated account."""
        if payment.currency != self.principal.currency:
            msg = f"Currency mismatch: {self.principal.currency} vs {payment.currency}."
            raise ValueError(msg)
        updated_principal_amount = self.principal.amount - payment.amount
        if updated_principal_amount <= 0 or self.months_remaining == 1:
            return None
        updated_principal = Money(
            amount=max(updated_principal_amount, Decimal(0)),
            currency=self.principal.currency,
        )
        return LoanAccount(
            identifier=self.identifier,
            principal=updated_principal,
            interest_rate=self.interest_rate,
            term_months=self.term_months,
            months_remaining=self.months_remaining - 1,
        )


class CompanyState(BaseModel):
    """Aggregate container capturing all mutable company attributes."""

    model_config = ConfigDict(frozen=True)

    company_id: str
    cash: Money
    inventory: InventoryLedger = Field(default_factory=InventoryLedger)
    factories: FactoryPortfolio = Field(default_factory=FactoryPortfolio)
    loans: tuple[LoanAccount, ...] = Field(default_factory=tuple)

    def credit_cash(self, amount: Money) -> CompanyState:
        """Increase cash by *amount* and return a new state instance."""
        return self.model_copy(update={"cash": self.cash.add(amount)})

    def debit_cash(self, amount: Money) -> CompanyState:
        """Decrease cash by *amount* and return a new state instance."""
        return self.model_copy(update={"cash": self.cash.subtract(amount)})

    def adjust_inventory(self, changes: Mapping[ResourceType, int]) -> CompanyState:
        """Return a new state with inventory deltas applied."""
        updated_inventory = self.inventory.apply_many(changes)
        return self.model_copy(update={"inventory": updated_inventory})

    def add_factory(self, record: FactoryRecord) -> CompanyState:
        """Return a new state with *record* tracked in the portfolio."""
        return self.model_copy(update={"factories": self.factories.add(record)})

    def register_loan(self, loan: LoanAccount) -> CompanyState:
        """Return a new state with *loan* appended to outstanding accounts."""
        return self.model_copy(update={"loans": (*self.loans, loan)})

    def replace_loans(self, loans: tuple[LoanAccount, ...]) -> CompanyState:
        """Return a state with the loan portfolio replaced by *loans*."""
        return self.model_copy(update={"loans": loans})

    def replace_factories(self, portfolio: FactoryPortfolio) -> CompanyState:
        """Return a state with factories swapped for *portfolio*."""
        return self.model_copy(update={"factories": portfolio})

    def with_inventory(self, ledger: InventoryLedger) -> CompanyState:
        """Return a state with inventory replaced by *ledger*."""
        return self.model_copy(update={"inventory": ledger})


__all__ = [
    "CompanyState",
    "FactoryPortfolio",
    "FactoryRecord",
    "FactoryStatus",
    "InventoryLedger",
    "LoanAccount",
]
