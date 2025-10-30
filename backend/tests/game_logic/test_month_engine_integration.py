from __future__ import annotations

from decimal import Decimal

from fabricat_backend.game_logic.configuration import EconomyConfiguration
from fabricat_backend.game_logic.engine import MonthContext, MonthEngine
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
from fabricat_backend.game_logic.phases import PhaseHandlers
from fabricat_backend.game_logic.state import (
    CompanyState,
    FactoryPortfolio,
    FactoryRecord,
    FactoryStatus,
    InventoryLedger,
    LoanAccount,
)
from fabricat_backend.shared.events import DecisionRecord
from fabricat_backend.shared.value_objects import (
    Money,
    PhaseIdentifier,
    ResourceType,
    SeniorityOrder,
)


def _build_configuration() -> EconomyConfiguration:
    return EconomyConfiguration(
        starting_cash=Money(amount=Decimal(20000), currency="USD"),
        raw_material_storage=20,
        finished_goods_storage=20,
        max_active_factories=3,
        base_loan_interest_rate=Decimal("0.05"),
        seniority_seed=None,
        base_operating_cost=Money(amount=Decimal(1000), currency="USD"),
        factory_maintenance_cost=Money(amount=Decimal(250), currency="USD"),
        storage_overage_penalty=Money(amount=Decimal(50), currency="USD"),
        raw_material_base_supply=10,
        raw_material_price_floor=Decimal(100),
        raw_material_price_ceiling=Decimal(200),
        finished_goods_base_demand=8,
        finished_goods_price_floor=Decimal(200),
        finished_goods_price_ceiling=Decimal(400),
        factory_capacity_per_month=5,
        factory_launch_cost=Money(amount=Decimal(500), currency="USD"),
        raw_materials_per_finished_good=2,
        loan_debt_ratio_limit=Decimal(2),
    )


def _inventory(raw: int, finished: int) -> InventoryLedger:
    ledger = InventoryLedger()
    if raw:
        ledger = ledger.apply_delta(ResourceType.RAW_MATERIAL, raw)
    if finished:
        ledger = ledger.apply_delta(ResourceType.FINISHED_GOOD, finished)
    return ledger


def _build_company_states() -> dict[str, CompanyState]:
    alpha_factories = FactoryPortfolio(
        active=(
            FactoryRecord(
                identifier="alpha-active",
                blueprint_id="basic",
                status=FactoryStatus.ACTIVE,
                months_remaining=None,
            ),
        ),
        under_construction=(
            FactoryRecord(
                identifier="alpha-build",
                blueprint_id="basic",
                status=FactoryStatus.UNDER_CONSTRUCTION,
                months_remaining=2,
            ),
        ),
    )
    beta_factories = FactoryPortfolio(
        active=(
            FactoryRecord(
                identifier="beta-active",
                blueprint_id="basic",
                status=FactoryStatus.ACTIVE,
                months_remaining=None,
            ),
        ),
        upgrading=(
            FactoryRecord(
                identifier="beta-aux",
                blueprint_id="basic",
                status=FactoryStatus.UPGRADING,
                months_remaining=1,
            ),
        ),
    )
    return {
        "alpha": CompanyState(
            company_id="alpha",
            cash=Money(amount=Decimal(20000), currency="USD"),
            inventory=_inventory(raw=4, finished=1),
            factories=alpha_factories,
            loans=(),
        ),
        "beta": CompanyState(
            company_id="beta",
            cash=Money(amount=Decimal(15000), currency="USD"),
            inventory=_inventory(raw=2, finished=2),
            factories=beta_factories,
            loans=(
                LoanAccount(
                    identifier="beta-loan",
                    principal=Money(amount=Decimal(5000), currency="USD"),
                    interest_rate=Decimal("0.10"),
                    term_months=5,
                    months_remaining=5,
                ),
            ),
        ),
    }


def _build_phase_handlers() -> PhaseHandlers:
    return PhaseHandlers(
        expenses=ExpensesPhaseHandlerImpl(),
        market_announcement=MarketAnnouncementPhaseHandlerImpl(),
        raw_material_purchase=RawMaterialPurchasePhaseHandlerImpl(),
        production=ProductionPhaseHandlerImpl(),
        finished_goods_sale=FinishedGoodsSalePhaseHandlerImpl(),
        loan_management=LoanManagementPhaseHandlerImpl(),
        construction=ConstructionPhaseHandlerImpl(),
        end_of_month=EndOfMonthPhaseHandlerImpl(),
    )


def _decision(phase: PhaseIdentifier, company_id: str, payload: dict) -> DecisionRecord:
    return DecisionRecord(
        month_index=1,
        phase=phase,
        company_id=company_id,
        payload=payload,
    )


def test_month_engine_executes_full_month_flow() -> None:
    configuration = _build_configuration()
    company_states = _build_company_states()
    handlers = _build_phase_handlers()

    decisions: dict[PhaseIdentifier, tuple[DecisionRecord, ...]] = {
        PhaseIdentifier.RAW_MATERIAL_PURCHASE: (
            _decision(
                PhaseIdentifier.RAW_MATERIAL_PURCHASE,
                "alpha",
                {"bids": [{"quantity": 6, "price": "180"}]},
            ),
            _decision(
                PhaseIdentifier.RAW_MATERIAL_PURCHASE,
                "beta",
                {"bids": [{"quantity": 6, "price": "180"}]},
            ),
        ),
        PhaseIdentifier.PRODUCTION: (
            _decision(
                PhaseIdentifier.PRODUCTION,
                "alpha",
                {"orders": [{"quantity": 5}]},
            ),
            _decision(
                PhaseIdentifier.PRODUCTION,
                "beta",
                {"orders": [{"quantity": 3}]},
            ),
        ),
        PhaseIdentifier.FINISHED_GOODS_SALE: (
            _decision(
                PhaseIdentifier.FINISHED_GOODS_SALE,
                "alpha",
                {"offers": [{"quantity": 4, "price": "350"}]},
            ),
            _decision(
                PhaseIdentifier.FINISHED_GOODS_SALE,
                "beta",
                {"offers": [{"quantity": 5, "price": "300"}]},
            ),
        ),
        PhaseIdentifier.LOAN_MANAGEMENT: (
            _decision(
                PhaseIdentifier.LOAN_MANAGEMENT,
                "alpha",
                {
                    "requests": [
                        {
                            "identifier": "alpha-loan",
                            "amount": "4000",
                            "term_months": 4,
                            "interest_rate": "0.08",
                        }
                    ]
                },
            ),
        ),
        PhaseIdentifier.CONSTRUCTION: (
            _decision(
                PhaseIdentifier.CONSTRUCTION,
                "alpha",
                {
                    "projects": [
                        {
                            "kind": "construction",
                            "identifier": "alpha-new",
                            "blueprint_id": "advanced",
                            "months": 3,
                            "cost": "2000",
                        }
                    ]
                },
            ),
            _decision(
                PhaseIdentifier.CONSTRUCTION,
                "beta",
                {
                    "projects": [
                        {
                            "kind": "upgrade",
                            "identifier": "beta-upgrade",
                            "target_factory_id": "beta-active",
                            "blueprint_id": "basic",
                            "months": 2,
                            "cost": "1500",
                        }
                    ]
                },
            ),
        ),
    }

    context = MonthContext(
        month_index=1,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=("alpha", "beta")),
        decisions=decisions,
    )

    engine = MonthEngine(handlers)
    result = engine.run_month(context)

    assert result.month_index == 1
    assert len(result.phase_results) == len(configuration.phase_sequence.phases)
    assert result.log.phases[-1].phase is PhaseIdentifier.END_OF_MONTH

    alpha_state = result.final_company_states["alpha"]
    beta_state = result.final_company_states["beta"]

    assert alpha_state.cash.amount == Decimal("20570.00")
    assert alpha_state.inventory.quantity(ResourceType.RAW_MATERIAL).amount == 0
    assert alpha_state.inventory.quantity(ResourceType.FINISHED_GOOD).amount == 2
    assert len(alpha_state.loans) == 1
    assert alpha_state.loans[0].principal.amount == Decimal("4000.00")
    assert alpha_state.loans[0].months_remaining == 4

    assert beta_state.cash.amount == Decimal("11070.00")
    assert beta_state.inventory.quantity(ResourceType.RAW_MATERIAL).amount == 2
    assert beta_state.inventory.quantity(ResourceType.FINISHED_GOOD).amount == 0
    assert len(beta_state.loans) == 1
    assert beta_state.loans[0].principal.amount == Decimal("4400.00")
    assert beta_state.loans[0].months_remaining == 4

    end_of_month_events = result.log.phases[-1].events
    rotation_event = next(
        event
        for event in end_of_month_events
        if event.event_type == "seniority_rotated"
    )
    assert tuple(rotation_event.payload["new_order"]) == ("beta", "alpha")

    total_capital = result.phase_results[-1].metrics["total_capital"]
    assert total_capital == Decimal(32240)
