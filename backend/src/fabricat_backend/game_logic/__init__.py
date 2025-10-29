"""Core rules and mechanics that drive Fabricat gameplay."""

from fabricat_backend.game_logic.configuration import (
    EconomyConfiguration,
    EconomyDefaults,
    LobbyOverrides,
    build_lobby_configuration,
    get_default_economy_configuration,
)
from fabricat_backend.game_logic.engine import MonthContext, MonthEngine, MonthResult
from fabricat_backend.game_logic.handlers import (
    ConstructionPhaseHandlerImpl,
    EndOfMonthPhaseHandlerImpl,
    ExpensesPhaseHandlerImpl,
    FinishedGoodsSalePhaseHandlerImpl,
    LoanManagementPhaseHandlerImpl,
    MarketAnnouncementPhaseHandlerImpl,
    ProductionPhaseHandlerImpl,
    RawMaterialPurchasePhaseHandlerImpl,
)
from fabricat_backend.game_logic.orchestration import (
    SessionNotInitializedError,
    SessionOrchestrator,
)
from fabricat_backend.game_logic.persistence import (
    GameStateSnapshot,
    GameStateStore,
    InMemoryGameStateStore,
    InMemoryMonthLogStore,
    MonthLogStore,
)
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
    "ConstructionPhaseHandlerImpl",
    "EconomyConfiguration",
    "EconomyDefaults",
    "EndOfMonthPhaseHandlerImpl",
    "ExpensesPhaseHandlerImpl",
    "FactoryPortfolio",
    "FactoryRecord",
    "FactoryStatus",
    "FinishedGoodsSalePhaseHandlerImpl",
    "GameStateSnapshot",
    "GameStateStore",
    "InMemoryGameStateStore",
    "InMemoryMonthLogStore",
    "InventoryLedger",
    "LoanAccount",
    "LoanManagementPhaseHandlerImpl",
    "LobbyOverrides",
    "MarketAnnouncementPhaseHandlerImpl",
    "MonthContext",
    "MonthEngine",
    "MonthLogStore",
    "MonthResult",
    "PhaseHandlers",
    "PhaseInputBase",
    "PhaseResultBase",
    "ProductionPhaseHandlerImpl",
    "RawMaterialPurchasePhaseHandlerImpl",
    "SessionNotInitializedError",
    "SessionOrchestrator",
    "build_lobby_configuration",
    "get_default_economy_configuration",
]
