"""Core rules and mechanics that drive Fabricat gameplay."""

from fabricat_backend.game_logic.configuration import (
    EconomyConfiguration,
    EconomyDefaults,
    LobbyOverrides,
    build_lobby_configuration,
    get_default_economy_configuration,
)
from fabricat_backend.game_logic.engine import MonthContext, MonthEngine, MonthResult
from fabricat_backend.game_logic.phases import (
    PhaseHandlers,
    PhaseInputBase,
    PhaseResultBase,
)
from fabricat_backend.game_logic.state import (
    CompanyState,
    FactoryPortfolio,
    FactoryRecord,
    FactoryStatus,
    InventoryLedger,
    LoanAccount,
)

__all__ = [
    "CompanyState",
    "EconomyConfiguration",
    "EconomyDefaults",
    "FactoryPortfolio",
    "FactoryRecord",
    "FactoryStatus",
    "InventoryLedger",
    "LoanAccount",
    "LobbyOverrides",
    "MonthContext",
    "MonthEngine",
    "MonthResult",
    "PhaseHandlers",
    "PhaseInputBase",
    "PhaseResultBase",
    "build_lobby_configuration",
    "get_default_economy_configuration",
]
