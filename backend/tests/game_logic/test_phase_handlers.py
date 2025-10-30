from __future__ import annotations

from decimal import Decimal

from fabricat_backend.game_logic.configuration import EconomyConfiguration
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
from fabricat_backend.game_logic.phases import (
    ConstructionPhaseInput,
    EndOfMonthPhaseInput,
    ExpensesPhaseInput,
    FinishedGoodsSalePhaseInput,
    LoanManagementPhaseInput,
    MarketAnnouncementPhaseInput,
    MarketAnnouncementPhaseResult,
    ProductionPhaseInput,
    RawMaterialPurchasePhaseInput,
)
from fabricat_backend.game_logic.state import (
    CompanyState,
    FactoryPortfolio,
    FactoryRecord,
    FactoryStatus,
    InventoryLedger,
    LoanAccount,
)
from fabricat_backend.shared.events import DecisionRecord, LoggedEvent, PhaseLog
from fabricat_backend.shared.value_objects import (
    Money,
    PhaseIdentifier,
    ResourceType,
    SeniorityOrder,
)


def build_config(**updates: object) -> EconomyConfiguration:
    """Create a baseline configuration for tests with optional overrides."""

    base = EconomyConfiguration(
        starting_cash=Money(amount=Decimal(100000), currency="USD"),
        raw_material_storage=20,
        finished_goods_storage=20,
        max_active_factories=5,
        base_loan_interest_rate=Decimal("0.10"),
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
        factory_launch_cost=Money(amount=Decimal(100), currency="USD"),
        raw_materials_per_finished_good=2,
        loan_debt_ratio_limit=Decimal(2),
    )
    if not updates:
        return base
    return base.model_copy(update=updates)


def make_inventory(raw: int = 0, finished: int = 0) -> InventoryLedger:
    ledger = InventoryLedger()
    if raw:
        ledger = ledger.apply_delta(ResourceType.RAW_MATERIAL, raw)
    if finished:
        ledger = ledger.apply_delta(ResourceType.FINISHED_GOOD, finished)
    return ledger


def make_company_state(
    company_id: str,
    *,
    cash: Decimal,
    inventory: InventoryLedger | None = None,
    factories: FactoryPortfolio | None = None,
    loans: tuple[LoanAccount, ...] = (),
) -> CompanyState:
    return CompanyState(
        company_id=company_id,
        cash=Money(amount=cash, currency="USD"),
        inventory=inventory or InventoryLedger(),
        factories=factories or FactoryPortfolio(),
        loans=loans,
    )


def make_phase_log(phase: PhaseIdentifier, month_index: int) -> PhaseLog:
    return PhaseLog(phase=phase, month_index=month_index, decisions=(), events=())


def make_market_result(
    *,
    month_index: int,
    metrics: dict[str, int | Decimal],
    company_states: dict[str, CompanyState],
) -> MarketAnnouncementPhaseResult:
    return MarketAnnouncementPhaseResult(
        phase=PhaseIdentifier.MARKET_ANNOUNCEMENT,
        month_index=month_index,
        updated_companies=company_states,
        log=make_phase_log(PhaseIdentifier.MARKET_ANNOUNCEMENT, month_index),
        metrics=metrics,
    )


def _make_active_factories(company_id: str, count: int) -> tuple[FactoryRecord, ...]:
    return tuple(
        FactoryRecord(
            identifier=f"{company_id}-f{index}",
            blueprint_id="basic",
            status=FactoryStatus.ACTIVE,
            months_remaining=None,
        )
        for index in range(1, count + 1)
    )


def test_expenses_phase_handler_applies_penalties_and_marks_bankruptcy() -> None:
    handler = ExpensesPhaseHandlerImpl()
    configuration = build_config(
        base_operating_cost=Money(amount=Decimal(1000), currency="USD"),
        factory_maintenance_cost=Money(amount=Decimal(200), currency="USD"),
        storage_overage_penalty=Money(amount=Decimal(50), currency="USD"),
        raw_material_storage=10,
        finished_goods_storage=5,
    )
    factories = FactoryPortfolio(
        active=(
            FactoryRecord(
                identifier="alpha-f1",
                blueprint_id="basic",
                status=FactoryStatus.ACTIVE,
                months_remaining=None,
            ),
            FactoryRecord(
                identifier="alpha-f2",
                blueprint_id="basic",
                status=FactoryStatus.ACTIVE,
                months_remaining=None,
            ),
        )
    )
    state = make_company_state(
        "alpha",
        cash=Decimal(1500),
        inventory=make_inventory(raw=15, finished=12),
        factories=factories,
    )
    input_data = ExpensesPhaseInput(
        month_index=1,
        configuration=configuration,
        company_states={"alpha": state},
        seniority_order=SeniorityOrder(ranking=("alpha",)),
    )

    result = handler.handle(input_data)

    updated = result.updated_companies["alpha"]
    assert updated.cash.amount == Decimal("-500.00")
    assert result.metrics["bankrupt_company_count"] == 1
    event_types = [event.event_type for event in result.log.events]
    assert "bankruptcy_flag" in event_types


def test_market_announcement_phase_handler_calculates_supply_and_demand() -> None:
    handler = MarketAnnouncementPhaseHandlerImpl()
    configuration = build_config(
        raw_material_base_supply=100,
        finished_goods_base_demand=80,
        factory_capacity_per_month=10,
    )
    company_states = {
        name: make_company_state(
            name,
            cash=Decimal(10000),
            factories=FactoryPortfolio(active=_make_active_factories(name, count)),
        )
        for name, count in {"alpha": 1, "beta": 2, "gamma": 3}.items()
    }
    input_data = MarketAnnouncementPhaseInput(
        month_index=0,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=tuple(company_states)),
    )

    result = handler.handle(input_data)

    assert result.metrics["raw_material_supply"] == 160
    assert result.metrics["finished_goods_demand"] == 140
    assert result.log.events[0].event_type == "market_corridor_announced"


def test_raw_material_purchase_phase_handler_respects_tie_breakers() -> None:
    handler = RawMaterialPurchasePhaseHandlerImpl()
    configuration = build_config(raw_material_base_supply=4)
    company_states = {
        name: make_company_state(name, cash=Decimal(5000)) for name in ("alpha", "beta")
    }
    market_result = make_market_result(
        month_index=1,
        metrics={
            "raw_material_supply": 4,
            "raw_material_price_floor": Decimal(100),
            "raw_material_price_ceiling": Decimal(200),
        },
        company_states=company_states,
    )
    decisions = (
        DecisionRecord(
            month_index=1,
            phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
            company_id="alpha",
            payload={"bids": [{"quantity": 3, "price": "150"}]},
        ),
        DecisionRecord(
            month_index=1,
            phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
            company_id="beta",
            payload={"bids": [{"quantity": 3, "price": "150"}]},
        ),
    )
    input_data = RawMaterialPurchasePhaseInput(
        month_index=1,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=("beta", "alpha")),
        decisions=decisions,
        previous_results=(market_result,),
    )

    result = handler.handle(input_data)

    alpha_inventory = result.updated_companies["alpha"].inventory
    beta_inventory = result.updated_companies["beta"].inventory
    assert alpha_inventory.quantity(ResourceType.RAW_MATERIAL).amount == 1
    assert beta_inventory.quantity(ResourceType.RAW_MATERIAL).amount == 3
    assert result.metrics["total_raw_material_allocated"] == 4
    assert result.metrics["remaining_raw_material_supply"] == 0


def test_raw_material_purchase_phase_handler_handles_insufficient_cash() -> None:
    handler = RawMaterialPurchasePhaseHandlerImpl()
    configuration = build_config(raw_material_base_supply=6, raw_material_storage=10)
    company_states = {
        "alpha": make_company_state("alpha", cash=Decimal(5000)),
        "beta": make_company_state("beta", cash=Decimal(50)),
        "gamma": make_company_state(
            "gamma",
            cash=Decimal(5000),
            inventory=make_inventory(raw=9),
            factories=FactoryPortfolio(),
        ),
    }
    market_result = make_market_result(
        month_index=2,
        metrics={
            "raw_material_supply": 6,
            "raw_material_price_floor": Decimal(100),
            "raw_material_price_ceiling": Decimal(200),
        },
        company_states=company_states,
    )
    decisions = (
        DecisionRecord(
            month_index=2,
            phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
            company_id="alpha",
            payload={"bids": [{"quantity": 4, "price": "150"}]},
        ),
        DecisionRecord(
            month_index=2,
            phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
            company_id="beta",
            payload={"bids": [{"quantity": 4, "price": "150"}]},
        ),
        DecisionRecord(
            month_index=2,
            phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
            company_id="gamma",
            payload={"bids": [{"quantity": 3, "price": "120"}]},
        ),
    )
    input_data = RawMaterialPurchasePhaseInput(
        month_index=2,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=("alpha", "beta", "gamma")),
        decisions=decisions,
        previous_results=(market_result,),
    )

    result = handler.handle(input_data)

    beta_events = [
        event.event_type for event in result.log.events if event.company_id == "beta"
    ]
    assert "raw_material_bid_insufficient_cash" in beta_events
    gamma_inventory = result.updated_companies["gamma"].inventory
    assert gamma_inventory.quantity(ResourceType.RAW_MATERIAL).amount == 10
    assert result.metrics["remaining_raw_material_supply"] == 1


def test_production_phase_handler_limits_by_capacity_and_resources() -> None:
    handler = ProductionPhaseHandlerImpl()
    configuration = build_config(
        factory_capacity_per_month=5,
        raw_materials_per_finished_good=2,
        factory_launch_cost=Money(amount=Decimal(100), currency="USD"),
    )
    factories = FactoryPortfolio(
        active=(
            FactoryRecord(
                identifier="alpha-f1",
                blueprint_id="basic",
                status=FactoryStatus.ACTIVE,
                months_remaining=None,
            ),
        )
    )
    state = make_company_state(
        "alpha",
        cash=Decimal(1000),
        inventory=make_inventory(raw=6),
        factories=factories,
    )
    decisions = (
        DecisionRecord(
            month_index=3,
            phase=PhaseIdentifier.PRODUCTION,
            company_id="alpha",
            payload={"orders": [{"quantity": 5}]},
        ),
    )
    input_data = ProductionPhaseInput(
        month_index=3,
        configuration=configuration,
        company_states={"alpha": state},
        seniority_order=SeniorityOrder(ranking=("alpha",)),
        decisions=decisions,
    )

    result = handler.handle(input_data)

    updated = result.updated_companies["alpha"]
    assert updated.inventory.quantity(ResourceType.RAW_MATERIAL).amount == 0
    assert updated.inventory.quantity(ResourceType.FINISHED_GOOD).amount == 3
    assert updated.cash.amount == Decimal("900.00")
    event_types = [event.event_type for event in result.log.events]
    assert "production_shortfall" in event_types


def test_finished_goods_sale_phase_handler_respects_price_tie_breakers() -> None:
    handler = FinishedGoodsSalePhaseHandlerImpl()
    configuration = build_config()
    company_states = {
        "alpha": make_company_state(
            "alpha", cash=Decimal(1000), inventory=make_inventory(finished=4)
        ),
        "beta": make_company_state(
            "beta", cash=Decimal(1000), inventory=make_inventory(finished=4)
        ),
    }
    market_result = make_market_result(
        month_index=4,
        metrics={
            "finished_goods_demand": 4,
            "finished_goods_price_floor": Decimal(100),
            "finished_goods_price_ceiling": Decimal(200),
        },
        company_states=company_states,
    )
    decisions = (
        DecisionRecord(
            month_index=4,
            phase=PhaseIdentifier.FINISHED_GOODS_SALE,
            company_id="alpha",
            payload={"offers": [{"quantity": 3, "price": "150"}]},
        ),
        DecisionRecord(
            month_index=4,
            phase=PhaseIdentifier.FINISHED_GOODS_SALE,
            company_id="beta",
            payload={"offers": [{"quantity": 3, "price": "150"}]},
        ),
    )
    input_data = FinishedGoodsSalePhaseInput(
        month_index=4,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=("beta", "alpha")),
        decisions=decisions,
        previous_results=(market_result,),
    )

    result = handler.handle(input_data)

    alpha_state = result.updated_companies["alpha"]
    beta_state = result.updated_companies["beta"]
    assert alpha_state.inventory.quantity(ResourceType.FINISHED_GOOD).amount == 3
    assert beta_state.inventory.quantity(ResourceType.FINISHED_GOOD).amount == 1
    assert alpha_state.cash.amount == Decimal("1150.00")
    assert beta_state.cash.amount == Decimal("1450.00")
    alpha_events = [
        event.event_type for event in result.log.events if event.company_id == "alpha"
    ]
    assert "sale_shortfall" in alpha_events


def test_loan_management_phase_handler_processes_defaults_and_requests() -> None:
    handler = LoanManagementPhaseHandlerImpl()
    configuration = build_config(
        starting_cash=Money(amount=Decimal(5000), currency="USD"),
        loan_debt_ratio_limit=Decimal(1),
    )
    alpha_loans = (
        LoanAccount(
            identifier="alpha-1",
            principal=Money(amount=Decimal(1000), currency="USD"),
            interest_rate=Decimal("0.10"),
            term_months=2,
            months_remaining=1,
        ),
    )
    beta_loans = (
        LoanAccount(
            identifier="beta-1",
            principal=Money(amount=Decimal(4000), currency="USD"),
            interest_rate=Decimal("0.20"),
            term_months=4,
            months_remaining=4,
        ),
    )
    company_states = {
        "alpha": make_company_state("alpha", cash=Decimal(3000), loans=alpha_loans),
        "beta": make_company_state("beta", cash=Decimal(100), loans=beta_loans),
    }
    decisions = (
        DecisionRecord(
            month_index=5,
            phase=PhaseIdentifier.LOAN_MANAGEMENT,
            company_id="alpha",
            payload={
                "requests": [
                    {
                        "identifier": "alpha-new",
                        "amount": "2000",
                        "term_months": 4,
                        "interest_rate": "0.15",
                    }
                ]
            },
        ),
        DecisionRecord(
            month_index=5,
            phase=PhaseIdentifier.LOAN_MANAGEMENT,
            company_id="beta",
            payload={
                "requests": [
                    {
                        "identifier": "beta-new",
                        "amount": "3000",
                        "term_months": 6,
                        "interest_rate": "0.18",
                    }
                ]
            },
        ),
    )
    input_data = LoanManagementPhaseInput(
        month_index=5,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=("alpha", "beta")),
        decisions=decisions,
    )

    result = handler.handle(input_data)

    alpha_state = result.updated_companies["alpha"]
    beta_state = result.updated_companies["beta"]
    assert len(alpha_state.loans) == 1
    assert alpha_state.loans[0].principal.amount == Decimal("2000.00")
    assert alpha_state.cash.amount == Decimal("3900.00")
    assert beta_state.loans[0].principal.amount == Decimal("4800.00")
    assert beta_state.cash.amount == Decimal("100.00")
    event_types = [event.event_type for event in result.log.events]
    assert event_types.count("loan_default") == 1
    assert "loan_request_rejected" in event_types
    assert "loan_issued" in event_types


def test_construction_phase_handler_advances_projects_and_applies_submissions() -> None:
    handler = ConstructionPhaseHandlerImpl()
    configuration = build_config()
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
                months_remaining=1,
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
                identifier="beta-upgrade",
                blueprint_id="basic",
                status=FactoryStatus.UPGRADING,
                months_remaining=1,
            ),
        ),
    )
    company_states = {
        "alpha": make_company_state(
            "alpha",
            cash=Decimal(5000),
            factories=alpha_factories,
        ),
        "beta": make_company_state(
            "beta",
            cash=Decimal(1000),
            factories=beta_factories,
        ),
    }
    decisions = (
        DecisionRecord(
            month_index=6,
            phase=PhaseIdentifier.CONSTRUCTION,
            company_id="alpha",
            payload={
                "projects": [
                    {
                        "kind": "construction",
                        "identifier": "alpha-new",
                        "blueprint_id": "advanced",
                        "months": 3,
                        "cost": "1500",
                    }
                ]
            },
        ),
        DecisionRecord(
            month_index=6,
            phase=PhaseIdentifier.CONSTRUCTION,
            company_id="beta",
            payload={
                "projects": [
                    {
                        "kind": "upgrade",
                        "identifier": "beta-upgrade2",
                        "target_factory_id": "beta-active",
                        "blueprint_id": "basic",
                        "months": 2,
                        "cost": "400",
                    },
                    {
                        "kind": "construction",
                        "identifier": "beta-new",
                        "blueprint_id": "advanced",
                        "months": 2,
                        "cost": "800",
                    },
                ]
            },
        ),
    )
    input_data = ConstructionPhaseInput(
        month_index=6,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=("alpha", "beta")),
        decisions=decisions,
    )

    result = handler.handle(input_data)

    alpha_state = result.updated_companies["alpha"]
    beta_state = result.updated_companies["beta"]
    assert alpha_state.cash.amount == Decimal("3500.00")
    assert {record.identifier for record in alpha_state.factories.active} == {
        "alpha-active",
        "alpha-build",
    }
    assert len(alpha_state.factories.under_construction) == 1
    alpha_project = alpha_state.factories.under_construction[0]
    assert alpha_project.identifier == "alpha-new"
    assert alpha_project.months_remaining == 3

    assert beta_state.cash.amount == Decimal("600.00")
    assert {record.identifier for record in beta_state.factories.active} == {
        "beta-upgrade"
    }
    assert len(beta_state.factories.upgrading) == 1
    beta_upgrade = beta_state.factories.upgrading[0]
    assert beta_upgrade.identifier == "beta-active"
    assert beta_upgrade.months_remaining == 2
    beta_events = [
        event.event_type for event in result.log.events if event.company_id == "beta"
    ]
    assert "project_rejected_insufficient_cash" in beta_events
    assert "upgrade_started" in beta_events


def test_end_of_month_phase_handler_removes_bankrupt_and_rotates_seniority() -> None:
    handler = EndOfMonthPhaseHandlerImpl()
    configuration = build_config()
    company_states = {
        "alpha": make_company_state("alpha", cash=Decimal(-100)),
        "beta": make_company_state(
            "beta", cash=Decimal(5000), inventory=make_inventory(raw=2, finished=1)
        ),
    }
    previous_events = (
        LoggedEvent(
            month_index=7,
            phase=PhaseIdentifier.EXPENSES,
            event_type="bankruptcy_flag",
            company_id="alpha",
        ),
    )
    market_result = make_market_result(
        month_index=7,
        metrics={
            "raw_material_price_floor": Decimal(100),
            "finished_goods_price_floor": Decimal(200),
        },
        company_states=company_states,
    )
    input_data = EndOfMonthPhaseInput(
        month_index=7,
        configuration=configuration,
        company_states=company_states,
        seniority_order=SeniorityOrder(ranking=("alpha", "beta")),
        previous_results=(market_result,),
        previous_events=previous_events,
    )

    result = handler.handle(input_data)

    assert "alpha" not in result.updated_companies
    assert result.metrics["bankruptcies_resolved"] == 1
    assert result.metrics["active_company_count"] == 1
    event_types = [event.event_type for event in result.log.events]
    assert "company_removed" in event_types
    assert "seniority_rotated" in event_types
