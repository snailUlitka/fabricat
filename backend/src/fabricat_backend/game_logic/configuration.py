"""Economic configuration objects for game sessions and lobbies."""

from __future__ import annotations

from decimal import Decimal
from functools import cache

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

from fabricat_backend.shared.value_objects import Money, PhaseIdentifier, PhaseSequence


class EconomyDefaults(BaseSettings):
    """Load default economic parameters from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FABRICAT_ECONOMY_",
        extra="ignore",
    )

    starting_cash: Decimal = Field(default=Decimal(1_500_000), ge=0)
    raw_material_storage: int = Field(default=120, ge=0)
    finished_goods_storage: int = Field(default=120, ge=0)
    max_active_factories: int = Field(default=6, ge=1)
    base_loan_interest_rate: Decimal = Field(default=Decimal("0.08"), ge=0)
    seniority_seed: int | None = Field(default=None)
    base_operating_cost: Decimal = Field(default=Decimal(20_000), ge=0)
    factory_maintenance_cost: Decimal = Field(default=Decimal(5_000), ge=0)
    storage_overage_penalty: Decimal = Field(default=Decimal(1_000), ge=0)
    raw_material_base_supply: int = Field(default=240, ge=0)
    raw_material_price_floor: Decimal = Field(default=Decimal(5000), ge=0)
    raw_material_price_ceiling: Decimal = Field(default=Decimal(15000), ge=0)
    finished_goods_base_demand: int = Field(default=220, ge=0)
    finished_goods_price_floor: Decimal = Field(default=Decimal(9000), ge=0)
    finished_goods_price_ceiling: Decimal = Field(default=Decimal(20000), ge=0)
    factory_capacity_per_month: int = Field(default=20, ge=0)
    factory_launch_cost: Decimal = Field(default=Decimal(2_500), ge=0)
    raw_materials_per_finished_good: int = Field(default=1, ge=1)
    loan_debt_ratio_limit: Decimal = Field(default=Decimal("3.0"), ge=0)

    def to_config(self) -> EconomyConfiguration:
        """Convert defaults into an immutable configuration object."""
        return EconomyConfiguration(
            starting_cash=Money(amount=self.starting_cash, currency="USD"),
            raw_material_storage=self.raw_material_storage,
            finished_goods_storage=self.finished_goods_storage,
            max_active_factories=self.max_active_factories,
            base_loan_interest_rate=self.base_loan_interest_rate,
            seniority_seed=self.seniority_seed,
            base_operating_cost=Money(amount=self.base_operating_cost, currency="USD"),
            factory_maintenance_cost=Money(
                amount=self.factory_maintenance_cost,
                currency="USD",
            ),
            storage_overage_penalty=Money(
                amount=self.storage_overage_penalty,
                currency="USD",
            ),
            raw_material_base_supply=self.raw_material_base_supply,
            raw_material_price_floor=self.raw_material_price_floor,
            raw_material_price_ceiling=self.raw_material_price_ceiling,
            finished_goods_base_demand=self.finished_goods_base_demand,
            finished_goods_price_floor=self.finished_goods_price_floor,
            finished_goods_price_ceiling=self.finished_goods_price_ceiling,
            factory_capacity_per_month=self.factory_capacity_per_month,
            factory_launch_cost=Money(
                amount=self.factory_launch_cost,
                currency="USD",
            ),
            raw_materials_per_finished_good=self.raw_materials_per_finished_good,
            loan_debt_ratio_limit=self.loan_debt_ratio_limit,
        )


class LobbyOverrides(BaseModel):
    """Optional lobby-specific overrides for economic settings."""

    model_config = ConfigDict(frozen=True)

    starting_cash: Money | None = None
    raw_material_storage: int | None = Field(default=None, ge=0)
    finished_goods_storage: int | None = Field(default=None, ge=0)
    max_active_factories: int | None = Field(default=None, ge=1)
    base_loan_interest_rate: Decimal | None = Field(default=None, ge=0)
    seniority_seed: int | None = None
    base_operating_cost: Money | None = None
    factory_maintenance_cost: Money | None = None
    storage_overage_penalty: Money | None = None
    raw_material_base_supply: int | None = Field(default=None, ge=0)
    raw_material_price_floor: Decimal | None = Field(default=None, ge=0)
    raw_material_price_ceiling: Decimal | None = Field(default=None, ge=0)
    finished_goods_base_demand: int | None = Field(default=None, ge=0)
    finished_goods_price_floor: Decimal | None = Field(default=None, ge=0)
    finished_goods_price_ceiling: Decimal | None = Field(default=None, ge=0)
    factory_capacity_per_month: int | None = Field(default=None, ge=0)
    factory_launch_cost: Money | None = None
    raw_materials_per_finished_good: int | None = Field(default=None, ge=1)
    loan_debt_ratio_limit: Decimal | None = Field(default=None, ge=0)

    def apply(self, config: EconomyConfiguration) -> EconomyConfiguration:
        """Return a copy of *config* with overrides applied."""
        starting_cash = self.starting_cash or config.starting_cash
        raw_storage = (
            self.raw_material_storage
            if self.raw_material_storage is not None
            else config.raw_material_storage
        )
        finished_storage = (
            self.finished_goods_storage
            if self.finished_goods_storage is not None
            else config.finished_goods_storage
        )
        max_factories = (
            self.max_active_factories
            if self.max_active_factories is not None
            else config.max_active_factories
        )
        interest_rate = (
            self.base_loan_interest_rate
            if self.base_loan_interest_rate is not None
            else config.base_loan_interest_rate
        )
        seniority_seed = (
            self.seniority_seed
            if self.seniority_seed is not None
            else config.seniority_seed
        )
        base_operating_cost = self.base_operating_cost or config.base_operating_cost
        factory_maintenance_cost = (
            self.factory_maintenance_cost
            if self.factory_maintenance_cost is not None
            else config.factory_maintenance_cost
        )
        storage_overage_penalty = (
            self.storage_overage_penalty
            if self.storage_overage_penalty is not None
            else config.storage_overage_penalty
        )
        raw_material_base_supply = (
            self.raw_material_base_supply
            if self.raw_material_base_supply is not None
            else config.raw_material_base_supply
        )
        raw_material_price_floor = (
            self.raw_material_price_floor
            if self.raw_material_price_floor is not None
            else config.raw_material_price_floor
        )
        raw_material_price_ceiling = (
            self.raw_material_price_ceiling
            if self.raw_material_price_ceiling is not None
            else config.raw_material_price_ceiling
        )
        finished_goods_base_demand = (
            self.finished_goods_base_demand
            if self.finished_goods_base_demand is not None
            else config.finished_goods_base_demand
        )
        finished_goods_price_floor = (
            self.finished_goods_price_floor
            if self.finished_goods_price_floor is not None
            else config.finished_goods_price_floor
        )
        finished_goods_price_ceiling = (
            self.finished_goods_price_ceiling
            if self.finished_goods_price_ceiling is not None
            else config.finished_goods_price_ceiling
        )
        factory_capacity_per_month = (
            self.factory_capacity_per_month
            if self.factory_capacity_per_month is not None
            else config.factory_capacity_per_month
        )
        factory_launch_cost = (
            self.factory_launch_cost
            if self.factory_launch_cost is not None
            else config.factory_launch_cost
        )
        raw_materials_per_finished_good = (
            self.raw_materials_per_finished_good
            if self.raw_materials_per_finished_good is not None
            else config.raw_materials_per_finished_good
        )
        loan_debt_ratio_limit = (
            self.loan_debt_ratio_limit
            if self.loan_debt_ratio_limit is not None
            else config.loan_debt_ratio_limit
        )
        return EconomyConfiguration(
            starting_cash=starting_cash,
            raw_material_storage=raw_storage,
            finished_goods_storage=finished_storage,
            max_active_factories=max_factories,
            base_loan_interest_rate=interest_rate,
            seniority_seed=seniority_seed,
            base_operating_cost=base_operating_cost,
            factory_maintenance_cost=factory_maintenance_cost,
            storage_overage_penalty=storage_overage_penalty,
            raw_material_base_supply=raw_material_base_supply,
            raw_material_price_floor=raw_material_price_floor,
            raw_material_price_ceiling=raw_material_price_ceiling,
            finished_goods_base_demand=finished_goods_base_demand,
            finished_goods_price_floor=finished_goods_price_floor,
            finished_goods_price_ceiling=finished_goods_price_ceiling,
            factory_capacity_per_month=factory_capacity_per_month,
            factory_launch_cost=factory_launch_cost,
            raw_materials_per_finished_good=raw_materials_per_finished_good,
            loan_debt_ratio_limit=loan_debt_ratio_limit,
        )


class EconomyConfiguration(BaseModel):
    """Immutable representation of the economic parameters for a session."""

    model_config = ConfigDict(frozen=True)

    starting_cash: Money
    raw_material_storage: int = Field(ge=0)
    finished_goods_storage: int = Field(ge=0)
    max_active_factories: int = Field(ge=1)
    base_loan_interest_rate: Decimal = Field(ge=0)
    seniority_seed: int | None = None
    base_operating_cost: Money
    factory_maintenance_cost: Money
    storage_overage_penalty: Money
    raw_material_base_supply: int = Field(ge=0)
    raw_material_price_floor: Decimal = Field(ge=0)
    raw_material_price_ceiling: Decimal = Field(ge=0)
    finished_goods_base_demand: int = Field(ge=0)
    finished_goods_price_floor: Decimal = Field(ge=0)
    finished_goods_price_ceiling: Decimal = Field(ge=0)
    factory_capacity_per_month: int = Field(ge=0)
    factory_launch_cost: Money
    raw_materials_per_finished_good: int = Field(ge=1)
    loan_debt_ratio_limit: Decimal = Field(ge=0)
    phase_sequence: PhaseSequence = Field(
        default_factory=lambda: PhaseSequence(
            phases=(
                PhaseIdentifier.EXPENSES,
                PhaseIdentifier.MARKET_ANNOUNCEMENT,
                PhaseIdentifier.RAW_MATERIAL_PURCHASE,
                PhaseIdentifier.PRODUCTION,
                PhaseIdentifier.FINISHED_GOODS_SALE,
                PhaseIdentifier.LOAN_MANAGEMENT,
                PhaseIdentifier.CONSTRUCTION,
                PhaseIdentifier.END_OF_MONTH,
            )
        )
    )

    def for_lobby(
        self, overrides: LobbyOverrides | None = None
    ) -> EconomyConfiguration:
        """Create a lobby-specific configuration by applying overrides if provided."""
        if overrides is None:
            return self
        return overrides.apply(self)


@cache
def get_default_economy_configuration() -> EconomyConfiguration:
    """Return the cached default economic configuration."""
    return EconomyDefaults().to_config()


def build_lobby_configuration(
    overrides: LobbyOverrides | None = None,
) -> EconomyConfiguration:
    """Construct a configuration for a lobby, applying optional overrides."""
    defaults = get_default_economy_configuration()
    if overrides is None:
        return defaults
    return overrides.apply(defaults)


__all__ = [
    "EconomyConfiguration",
    "EconomyDefaults",
    "LobbyOverrides",
    "build_lobby_configuration",
    "get_default_economy_configuration",
]
