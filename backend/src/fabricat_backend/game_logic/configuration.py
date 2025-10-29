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

    def to_config(self) -> EconomyConfiguration:
        """Convert defaults into an immutable configuration object."""
        return EconomyConfiguration(
            starting_cash=Money(amount=self.starting_cash, currency="USD"),
            raw_material_storage=self.raw_material_storage,
            finished_goods_storage=self.finished_goods_storage,
            max_active_factories=self.max_active_factories,
            base_loan_interest_rate=self.base_loan_interest_rate,
            seniority_seed=self.seniority_seed,
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
        return EconomyConfiguration(
            starting_cash=starting_cash,
            raw_material_storage=raw_storage,
            finished_goods_storage=finished_storage,
            max_active_factories=max_factories,
            base_loan_interest_rate=interest_rate,
            seniority_seed=seniority_seed,
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
