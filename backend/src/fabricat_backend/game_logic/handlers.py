"""Concrete implementations for the month phase handlers."""

from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from math import ceil
from typing import TYPE_CHECKING

from pydantic import BaseModel
from pydantic.config import ConfigDict

from fabricat_backend.game_logic.phases import (
    ConstructionPhaseInput,
    ConstructionPhaseResult,
    EndOfMonthPhaseInput,
    EndOfMonthPhaseResult,
    ExpensesPhaseInput,
    ExpensesPhaseResult,
    FinishedGoodsSalePhaseInput,
    FinishedGoodsSalePhaseResult,
    LoanManagementPhaseInput,
    LoanManagementPhaseResult,
    MarketAnnouncementPhaseInput,
    MarketAnnouncementPhaseResult,
    PhaseResultBase,
    ProductionPhaseInput,
    ProductionPhaseResult,
    RawMaterialPurchasePhaseInput,
    RawMaterialPurchasePhaseResult,
)
from fabricat_backend.game_logic.state import (
    CompanyState,
    FactoryPortfolio,
    FactoryRecord,
    FactoryStatus,
    LoanAccount,
)
from fabricat_backend.shared.events import DecisionRecord, LoggedEvent, PhaseLog

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from fabricat_backend.game_logic.configuration import EconomyConfiguration
from fabricat_backend.shared.value_objects import (
    Money,
    PhaseIdentifier,
    ResourceType,
)


def _build_phase_log(
    phase: PhaseIdentifier,
    month_index: int,
    decisions: Iterable[DecisionRecord],
    events: Iterable[LoggedEvent],
) -> PhaseLog:
    return PhaseLog(
        phase=phase,
        month_index=month_index,
        decisions=tuple(decisions),
        events=tuple(events),
    )


def _find_phase_result(
    previous_results: Iterable[PhaseResultBase], phase: PhaseIdentifier
) -> PhaseResultBase | None:
    for result in previous_results:
        if result.phase is phase:
            return result
    return None


def _metric_as_int(
    metrics: Mapping[str, float | int | Decimal], key: str, default: int
) -> int:
    value = metrics.get(key)
    if value is None:
        return default
    return int(Decimal(str(value)))


def _metric_as_decimal(
    metrics: Mapping[str, float | int | Decimal],
    key: str,
    default: Decimal,
) -> Decimal:
    value = metrics.get(key)
    if value is None:
        return default
    return Decimal(str(value))


class PhaseHandlerModel(BaseModel):
    """Base class for concrete phase handlers using Pydantic for validation."""

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ExpensesPhaseHandlerImpl(PhaseHandlerModel):
    """Deduct recurring company expenses and flag bankruptcies."""

    def handle(self, input_data: ExpensesPhaseInput) -> ExpensesPhaseResult:
        """Execute the expenses phase for all companies."""
        configuration = input_data.configuration
        events: list[LoggedEvent] = []
        updated_states: dict[str, CompanyState] = {}
        bankrupt_companies: set[str] = set()
        aggregate_expenses = Decimal(0)

        for company_id, state in input_data.company_states.items():
            currency = state.cash.currency
            total_expense = Money.zero(currency)
            base_expense = configuration.base_operating_cost
            total_expense = total_expense.add(base_expense)

            active_factories = len(state.factories.active)
            maintenance = configuration.factory_maintenance_cost.multiply(
                active_factories
            )
            total_expense = total_expense.add(maintenance)

            rm_quantity = state.inventory.quantity(ResourceType.RAW_MATERIAL).amount
            rm_overage = max(0, rm_quantity - configuration.raw_material_storage)
            if rm_overage:
                penalty = configuration.storage_overage_penalty.multiply(rm_overage)
                total_expense = total_expense.add(penalty)
            else:
                penalty = None

            fg_quantity = state.inventory.quantity(ResourceType.FINISHED_GOOD).amount
            fg_overage = max(0, fg_quantity - configuration.finished_goods_storage)
            if fg_overage:
                fg_penalty = configuration.storage_overage_penalty.multiply(fg_overage)
                total_expense = total_expense.add(fg_penalty)
            else:
                fg_penalty = None

            aggregate_expenses += total_expense.amount
            updated_state = state.debit_cash(total_expense)
            updated_states[company_id] = updated_state

            events.append(
                LoggedEvent(
                    month_index=input_data.month_index,
                    phase=PhaseIdentifier.EXPENSES,
                    event_type="expenses_applied",
                    company_id=company_id,
                    payload={
                        "base": str(base_expense.amount),
                        "maintenance": str(maintenance.amount),
                        "raw_material_overage": str(penalty.amount) if penalty else "0",
                        "finished_goods_overage": str(fg_penalty.amount)
                        if fg_penalty
                        else "0",
                        "total_expense": str(total_expense.amount),
                    },
                )
            )

            if updated_state.cash.amount < 0:
                bankrupt_companies.add(company_id)
                events.append(
                    LoggedEvent(
                        month_index=input_data.month_index,
                        phase=PhaseIdentifier.EXPENSES,
                        event_type="bankruptcy_flag",
                        company_id=company_id,
                        message=(
                            "Company cash balance dropped below zero after expenses."
                        ),
                        payload={"deficit": str(updated_state.cash.amount)},
                    )
                )

        phase_log = _build_phase_log(
            PhaseIdentifier.EXPENSES,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = (
            f"Processed expenses for {len(updated_states)} companies; "
            f"aggregate debit {aggregate_expenses:,.2f}."
        )
        return ExpensesPhaseResult(
            phase=PhaseIdentifier.EXPENSES,
            month_index=input_data.month_index,
            updated_companies=updated_states,
            log=phase_log,
            summary=summary,
            metrics={
                "bankrupt_company_count": len(bankrupt_companies),
                "aggregate_expense": aggregate_expenses,
            },
        )


class MarketAnnouncementPhaseHandlerImpl(PhaseHandlerModel):
    """Generate market corridors for raw materials and finished goods."""

    def handle(
        self, input_data: MarketAnnouncementPhaseInput
    ) -> MarketAnnouncementPhaseResult:
        """Publish market corridor information for the current month."""
        configuration = input_data.configuration
        total_active_factories = sum(
            state.factories.total_active_capacity()
            for state in input_data.company_states.values()
        )
        supply = (
            configuration.raw_material_base_supply
            + total_active_factories * configuration.factory_capacity_per_month
        )
        demand = (
            configuration.finished_goods_base_demand
            + total_active_factories * configuration.factory_capacity_per_month
        )

        events = [
            LoggedEvent(
                month_index=input_data.month_index,
                phase=PhaseIdentifier.MARKET_ANNOUNCEMENT,
                event_type="market_corridor_announced",
                payload={
                    "raw_material_supply": supply,
                    "raw_material_price_floor": str(
                        configuration.raw_material_price_floor
                    ),
                    "raw_material_price_ceiling": str(
                        configuration.raw_material_price_ceiling
                    ),
                    "finished_goods_demand": demand,
                    "finished_goods_price_floor": str(
                        configuration.finished_goods_price_floor
                    ),
                    "finished_goods_price_ceiling": str(
                        configuration.finished_goods_price_ceiling
                    ),
                },
            )
        ]
        phase_log = _build_phase_log(
            PhaseIdentifier.MARKET_ANNOUNCEMENT,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = (
            "Announced market corridors for raw materials and finished goods based on "
            f"{total_active_factories} active factories."
        )
        return MarketAnnouncementPhaseResult(
            phase=PhaseIdentifier.MARKET_ANNOUNCEMENT,
            month_index=input_data.month_index,
            updated_companies=dict(input_data.company_states),
            log=phase_log,
            summary=summary,
            metrics={
                "raw_material_supply": supply,
                "raw_material_price_floor": configuration.raw_material_price_floor,
                "raw_material_price_ceiling": configuration.raw_material_price_ceiling,
                "finished_goods_demand": demand,
                "finished_goods_price_floor": configuration.finished_goods_price_floor,
                "finished_goods_price_ceiling": (
                    configuration.finished_goods_price_ceiling
                ),
            },
        )


class RawMaterialPurchasePhaseHandlerImpl(PhaseHandlerModel):
    """Resolve hidden raw material bids respecting cash and seniority."""

    def handle(
        self, input_data: RawMaterialPurchasePhaseInput
    ) -> RawMaterialPurchasePhaseResult:
        """Allocate raw materials across competing bids."""
        configuration = input_data.configuration
        previous_market = _find_phase_result(
            input_data.previous_results, PhaseIdentifier.MARKET_ANNOUNCEMENT
        )
        market_metrics = previous_market.metrics if previous_market else {}
        remaining_supply = _metric_as_int(
            market_metrics,
            "raw_material_supply",
            configuration.raw_material_base_supply,
        )
        price_floor = _metric_as_decimal(
            market_metrics,
            "raw_material_price_floor",
            configuration.raw_material_price_floor,
        )
        price_ceiling = _metric_as_decimal(
            market_metrics,
            "raw_material_price_ceiling",
            configuration.raw_material_price_ceiling,
        )

        ranking = {
            identifier: index
            for index, identifier in enumerate(input_data.seniority_order.ranking)
        }
        bids = self._collect_valid_bids(
            decisions=input_data.decisions,
            price_floor=price_floor,
            price_ceiling=price_ceiling,
        )
        bids.sort(
            key=lambda entry: (
                -entry[2],
                ranking.get(entry[0], len(ranking)),
            )
        )
        (
            updated_states,
            events,
            remaining_supply,
            total_allocated,
        ) = self._apply_bids(
            bids=bids,
            configuration=configuration,
            remaining_supply=remaining_supply,
            month_index=input_data.month_index,
            states=dict(input_data.company_states),
        )

        phase_log = _build_phase_log(
            PhaseIdentifier.RAW_MATERIAL_PURCHASE,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = (
            f"Allocated {total_allocated} raw material units; "
            f"remaining supply {remaining_supply}."
        )
        return RawMaterialPurchasePhaseResult(
            phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
            month_index=input_data.month_index,
            updated_companies=updated_states,
            log=phase_log,
            summary=summary,
            metrics={
                "total_raw_material_allocated": total_allocated,
                "remaining_raw_material_supply": remaining_supply,
            },
        )

    @staticmethod
    def _collect_valid_bids(
        *,
        decisions: Iterable[DecisionRecord],
        price_floor: Decimal,
        price_ceiling: Decimal,
    ) -> list[tuple[str, int, Decimal]]:
        bids: list[tuple[str, int, Decimal]] = []
        for record in decisions:
            payload = record.payload or {}
            for bid in payload.get("bids", []):
                quantity = int(bid.get("quantity", 0))
                price = Decimal(str(bid.get("price", "0")))
                if quantity <= 0 or price < price_floor or price > price_ceiling:
                    continue
                bids.append((record.company_id, quantity, price))
        return bids

    def _apply_bids(
        self,
        *,
        bids: list[tuple[str, int, Decimal]],
        configuration: EconomyConfiguration,
        remaining_supply: int,
        month_index: int,
        states: dict[str, CompanyState],
    ) -> tuple[dict[str, CompanyState], list[LoggedEvent], int, int]:
        events: list[LoggedEvent] = []
        total_allocated = 0
        for company_id, requested_quantity, price in bids:
            if remaining_supply <= 0:
                break
            state = states[company_id]
            storage_capacity = configuration.raw_material_storage
            current_quantity = state.inventory.quantity(
                ResourceType.RAW_MATERIAL
            ).amount
            available_space = max(0, storage_capacity - current_quantity)
            if available_space <= 0:
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
                        event_type="raw_material_bid_skipped",
                        company_id=company_id,
                        message="No storage capacity available for raw materials.",
                        payload={"requested_quantity": requested_quantity},
                    )
                )
                continue

            allocation = min(requested_quantity, remaining_supply, available_space)
            if allocation <= 0:
                continue

            max_affordable = int(
                (state.cash.amount / price).to_integral_value(rounding=ROUND_DOWN)
            )
            allocation = min(allocation, max_affordable)
            if allocation <= 0:
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
                        event_type="raw_material_bid_insufficient_cash",
                        company_id=company_id,
                        message="Company lacks cash to cover requested raw materials.",
                        payload={
                            "requested_quantity": requested_quantity,
                            "price": str(price),
                        },
                    )
                )
                continue

            total_cost_amount = (price * allocation).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            total_cost = Money(amount=total_cost_amount, currency=state.cash.currency)
            state_after_cash = state.debit_cash(total_cost)
            updated_inventory = state_after_cash.inventory.apply_delta(
                ResourceType.RAW_MATERIAL, allocation
            )
            updated_state = state_after_cash.with_inventory(updated_inventory)
            states[company_id] = updated_state
            remaining_supply -= allocation
            total_allocated += allocation

            events.append(
                LoggedEvent(
                    month_index=month_index,
                    phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
                    event_type="raw_material_allocation",
                    company_id=company_id,
                    payload={
                        "allocated_quantity": allocation,
                        "unit_price": str(price),
                        "total_cost": str(total_cost.amount),
                        "remaining_supply": remaining_supply,
                    },
                )
            )

            if allocation < requested_quantity:
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.RAW_MATERIAL_PURCHASE,
                        event_type="raw_material_shortfall",
                        company_id=company_id,
                        message=(
                            "Requested quantity exceeded available supply or capacity."
                        ),
                        payload={
                            "requested_quantity": requested_quantity,
                            "fulfilled_quantity": allocation,
                        },
                    )
                )

        return states, events, remaining_supply, total_allocated


class ProductionPhaseHandlerImpl(PhaseHandlerModel):
    """Convert raw materials into finished goods within capacity limits."""

    def handle(self, input_data: ProductionPhaseInput) -> ProductionPhaseResult:
        """Resolve production orders for the month."""
        configuration = input_data.configuration
        orders_by_company: dict[str, list[dict]] = {}
        for decision in input_data.decisions:
            payload = decision.payload or {}
            orders_by_company.setdefault(decision.company_id, []).extend(
                payload.get("orders", [])
            )

        events: list[LoggedEvent] = []
        updated_states: dict[str, CompanyState] = dict(input_data.company_states)
        total_finished_goods = 0

        for company_id, state in input_data.company_states.items():
            orders = orders_by_company.get(company_id, [])
            requested_quantity = sum(
                max(0, int(order.get("quantity", 0))) for order in orders
            )
            active_factories = state.factories.total_active_capacity()
            max_capacity = active_factories * configuration.factory_capacity_per_month
            available_raw_materials = state.inventory.quantity(
                ResourceType.RAW_MATERIAL
            ).amount
            max_from_raw = (
                available_raw_materials // configuration.raw_materials_per_finished_good
            )
            producible_quantity = min(requested_quantity, max_capacity, max_from_raw)

            if producible_quantity <= 0:
                if requested_quantity > 0:
                    events.append(
                        LoggedEvent(
                            month_index=input_data.month_index,
                            phase=PhaseIdentifier.PRODUCTION,
                            event_type="production_unfulfilled",
                            company_id=company_id,
                            message=(
                                "Insufficient capacity or raw materials to fulfill "
                                "orders."
                            ),
                            payload={
                                "requested_quantity": requested_quantity,
                                "available_raw_materials": available_raw_materials,
                            },
                        )
                    )
                continue

            factories_required = (
                min(
                    active_factories,
                    ceil(
                        producible_quantity
                        / max(1, configuration.factory_capacity_per_month)
                    ),
                )
                if active_factories
                else 0
            )
            launch_cost = configuration.factory_launch_cost.multiply(factories_required)
            raw_materials_consumed = (
                producible_quantity * configuration.raw_materials_per_finished_good
            )

            state_after_inventory = updated_states[company_id].adjust_inventory(
                {
                    ResourceType.RAW_MATERIAL: -raw_materials_consumed,
                    ResourceType.FINISHED_GOOD: producible_quantity,
                }
            )
            if launch_cost.amount > 0:
                state_after_inventory = state_after_inventory.debit_cash(launch_cost)
            updated_states[company_id] = state_after_inventory
            total_finished_goods += producible_quantity

            events.append(
                LoggedEvent(
                    month_index=input_data.month_index,
                    phase=PhaseIdentifier.PRODUCTION,
                    event_type="production_completed",
                    company_id=company_id,
                    payload={
                        "produced_quantity": producible_quantity,
                        "factories_used": factories_required,
                        "launch_cost": str(launch_cost.amount),
                        "raw_materials_consumed": raw_materials_consumed,
                    },
                )
            )

            if producible_quantity < requested_quantity:
                events.append(
                    LoggedEvent(
                        month_index=input_data.month_index,
                        phase=PhaseIdentifier.PRODUCTION,
                        event_type="production_shortfall",
                        company_id=company_id,
                        payload={
                            "requested_quantity": requested_quantity,
                            "fulfilled_quantity": producible_quantity,
                        },
                    )
                )

        phase_log = _build_phase_log(
            PhaseIdentifier.PRODUCTION,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = (
            f"Produced {total_finished_goods} finished goods across all companies."
        )
        return ProductionPhaseResult(
            phase=PhaseIdentifier.PRODUCTION,
            month_index=input_data.month_index,
            updated_companies=updated_states,
            log=phase_log,
            summary=summary,
            metrics={"total_finished_goods_produced": total_finished_goods},
        )


class FinishedGoodsSalePhaseHandlerImpl(PhaseHandlerModel):
    """Resolve finished goods offers using price ceilings and seniority."""

    def handle(
        self, input_data: FinishedGoodsSalePhaseInput
    ) -> FinishedGoodsSalePhaseResult:
        """Clear finished goods offers against market demand."""
        configuration = input_data.configuration
        previous_market = _find_phase_result(
            input_data.previous_results, PhaseIdentifier.MARKET_ANNOUNCEMENT
        )
        market_metrics = previous_market.metrics if previous_market else {}
        remaining_demand = _metric_as_int(
            market_metrics,
            "finished_goods_demand",
            configuration.finished_goods_base_demand,
        )
        price_floor = _metric_as_decimal(
            market_metrics,
            "finished_goods_price_floor",
            configuration.finished_goods_price_floor,
        )
        price_ceiling = _metric_as_decimal(
            market_metrics,
            "finished_goods_price_ceiling",
            configuration.finished_goods_price_ceiling,
        )

        ranking = {
            identifier: index
            for index, identifier in enumerate(input_data.seniority_order.ranking)
        }
        offers: list[tuple[str, int, Decimal]] = []
        for record in input_data.decisions:
            payload = record.payload or {}
            for offer in payload.get("offers", []):
                quantity = int(offer.get("quantity", 0))
                price = Decimal(str(offer.get("price", "0")))
                if quantity <= 0:
                    continue
                if price < price_floor or price > price_ceiling:
                    continue
                offers.append((record.company_id, quantity, price))

        offers.sort(
            key=lambda entry: (
                -entry[2],
                ranking.get(entry[0], len(ranking)),
            )
        )

        events: list[LoggedEvent] = []
        updated_states: dict[str, CompanyState] = dict(input_data.company_states)
        total_sold = 0

        for company_id, requested_quantity, price in offers:
            if remaining_demand <= 0:
                break
            state = updated_states[company_id]
            inventory_quantity = state.inventory.quantity(
                ResourceType.FINISHED_GOOD
            ).amount
            allocation = min(requested_quantity, remaining_demand, inventory_quantity)
            if allocation <= 0:
                events.append(
                    LoggedEvent(
                        month_index=input_data.month_index,
                        phase=PhaseIdentifier.FINISHED_GOODS_SALE,
                        event_type="sale_offer_unfulfilled",
                        company_id=company_id,
                        message="No finished goods available to satisfy offer.",
                        payload={"requested_quantity": requested_quantity},
                    )
                )
                continue

            revenue_amount = (price * allocation).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            revenue = Money(amount=revenue_amount, currency=state.cash.currency)
            state_after_inventory = state.adjust_inventory(
                {ResourceType.FINISHED_GOOD: -allocation}
            )
            updated_state = state_after_inventory.credit_cash(revenue)
            updated_states[company_id] = updated_state
            remaining_demand -= allocation
            total_sold += allocation

            events.append(
                LoggedEvent(
                    month_index=input_data.month_index,
                    phase=PhaseIdentifier.FINISHED_GOODS_SALE,
                    event_type="finished_goods_sale",
                    company_id=company_id,
                    payload={
                        "quantity_sold": allocation,
                        "unit_price": str(price),
                        "revenue": str(revenue.amount),
                        "remaining_demand": remaining_demand,
                    },
                )
            )

            if allocation < requested_quantity:
                events.append(
                    LoggedEvent(
                        month_index=input_data.month_index,
                        phase=PhaseIdentifier.FINISHED_GOODS_SALE,
                        event_type="sale_shortfall",
                        company_id=company_id,
                        payload={
                            "requested_quantity": requested_quantity,
                            "fulfilled_quantity": allocation,
                        },
                    )
                )

        phase_log = _build_phase_log(
            PhaseIdentifier.FINISHED_GOODS_SALE,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = f"Cleared {total_sold} finished goods units from player offers."
        return FinishedGoodsSalePhaseResult(
            phase=PhaseIdentifier.FINISHED_GOODS_SALE,
            month_index=input_data.month_index,
            updated_companies=updated_states,
            log=phase_log,
            summary=summary,
            metrics={
                "finished_goods_sold": total_sold,
                "remaining_market_demand": remaining_demand,
            },
        )


class LoanManagementPhaseHandlerImpl(PhaseHandlerModel):
    """Accrue interest, process repayments, and evaluate new loan requests."""

    def handle(self, input_data: LoanManagementPhaseInput) -> LoanManagementPhaseResult:
        """Maintain loan portfolios and review new requests."""
        configuration = input_data.configuration
        requests_by_company: dict[str, list[dict]] = {}
        for decision in input_data.decisions:
            payload = decision.payload or {}
            requests_by_company.setdefault(decision.company_id, []).extend(
                payload.get("requests", [])
            )

        events: list[LoggedEvent] = []
        updated_states: dict[str, CompanyState] = {}
        defaults_recorded = 0

        for company_id, state in input_data.company_states.items():
            cash_balance = state.cash
            updated_loans: list[LoanAccount] = []

            for loan in state.loans:
                accrued = loan.accrue_interest()
                payment_due = accrued.scheduled_payment()
                if cash_balance.amount < payment_due.amount:
                    defaults_recorded += 1
                    events.append(
                        LoggedEvent(
                            month_index=input_data.month_index,
                            phase=PhaseIdentifier.LOAN_MANAGEMENT,
                            event_type="loan_default",
                            company_id=company_id,
                            message="Company could not meet scheduled loan repayment.",
                            payload={
                                "loan_id": loan.identifier,
                                "payment_due": str(payment_due.amount),
                                "cash_available": str(cash_balance.amount),
                            },
                        )
                    )
                    updated_loans.append(accrued)
                    continue

                cash_balance = cash_balance.subtract(payment_due)
                next_account = accrued.apply_payment(payment_due)
                if next_account is not None:
                    updated_loans.append(next_account)
                else:
                    events.append(
                        LoggedEvent(
                            month_index=input_data.month_index,
                            phase=PhaseIdentifier.LOAN_MANAGEMENT,
                            event_type="loan_closed",
                            company_id=company_id,
                            payload={"loan_id": loan.identifier},
                        )
                    )

            debt_limit = (
                configuration.starting_cash.amount * configuration.loan_debt_ratio_limit
            )
            current_debt = sum(loan.principal.amount for loan in updated_loans)
            for request in requests_by_company.get(company_id, []):
                amount = Decimal(str(request.get("amount", "0")))
                if amount <= 0:
                    continue
                term_months = int(request.get("term_months", 12))
                interest_rate = Decimal(
                    str(
                        request.get(
                            "interest_rate", configuration.base_loan_interest_rate
                        )
                    )
                )
                identifier = request.get(
                    "identifier", f"{company_id}-loan-{len(updated_loans) + 1}"
                )
                projected_debt = current_debt + amount
                if projected_debt > debt_limit:
                    events.append(
                        LoggedEvent(
                            month_index=input_data.month_index,
                            phase=PhaseIdentifier.LOAN_MANAGEMENT,
                            event_type="loan_request_rejected",
                            company_id=company_id,
                            message="Loan request exceeds debt limit.",
                            payload={
                                "identifier": identifier,
                                "requested_amount": str(amount),
                                "debt_limit": str(debt_limit),
                            },
                        )
                    )
                    continue

                principal = Money(
                    amount=amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    currency=cash_balance.currency,
                )
                new_loan = LoanAccount(
                    identifier=identifier,
                    principal=principal,
                    interest_rate=interest_rate,
                    term_months=term_months,
                    months_remaining=term_months,
                )
                updated_loans.append(new_loan)
                current_debt += amount
                cash_balance = cash_balance.add(principal)
                events.append(
                    LoggedEvent(
                        month_index=input_data.month_index,
                        phase=PhaseIdentifier.LOAN_MANAGEMENT,
                        event_type="loan_issued",
                        company_id=company_id,
                        payload={
                            "identifier": identifier,
                            "amount": str(principal.amount),
                            "interest_rate": str(interest_rate),
                            "term_months": term_months,
                        },
                    )
                )

            updated_state = state.model_copy(
                update={"cash": cash_balance, "loans": tuple(updated_loans)}
            )
            updated_states[company_id] = updated_state

        phase_log = _build_phase_log(
            PhaseIdentifier.LOAN_MANAGEMENT,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = (
            f"Processed loan portfolios; {defaults_recorded} defaults recorded and "
            f"{len(events)} loan events logged."
        )
        return LoanManagementPhaseResult(
            phase=PhaseIdentifier.LOAN_MANAGEMENT,
            month_index=input_data.month_index,
            updated_companies=updated_states,
            log=phase_log,
            summary=summary,
            metrics={"loan_defaults": defaults_recorded},
        )


class ConstructionPhaseHandlerImpl(PhaseHandlerModel):
    """Advance factory construction timelines and register new projects."""

    def handle(self, input_data: ConstructionPhaseInput) -> ConstructionPhaseResult:
        """Update construction progress and apply submitted projects."""
        projects_by_company: dict[str, list[dict]] = {}
        for decision in input_data.decisions:
            payload = decision.payload or {}
            projects_by_company.setdefault(decision.company_id, []).extend(
                payload.get("projects", [])
            )

        events: list[LoggedEvent] = []
        updated_states: dict[str, CompanyState] = {}

        for company_id, state in input_data.company_states.items():
            (
                new_active,
                new_construction,
                new_upgrading,
                advance_events,
            ) = self._advance_existing_projects(
                state=state,
                month_index=input_data.month_index,
            )
            events.extend(advance_events)
            buckets = {
                "active": new_active,
                "construction": new_construction,
                "upgrading": new_upgrading,
            }
            cash_balance, buckets, project_events = self._apply_new_projects(
                company_id=company_id,
                projects=projects_by_company.get(company_id, []),
                month_index=input_data.month_index,
                cash_balance=state.cash,
                buckets=buckets,
            )
            events.extend(project_events)

            final_active = buckets["active"]
            final_construction = buckets["construction"]
            final_upgrading = buckets["upgrading"]

            updated_portfolio = FactoryPortfolio(
                active=tuple(final_active),
                under_construction=tuple(final_construction),
                upgrading=tuple(final_upgrading),
            )
            updated_state = state.model_copy(
                update={"cash": cash_balance, "factories": updated_portfolio}
            )
            updated_states[company_id] = updated_state

        phase_log = _build_phase_log(
            PhaseIdentifier.CONSTRUCTION,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = "Processed construction pipelines and applied project submissions."
        return ConstructionPhaseResult(
            phase=PhaseIdentifier.CONSTRUCTION,
            month_index=input_data.month_index,
            updated_companies=updated_states,
            log=phase_log,
            summary=summary,
            metrics={},
        )

    def _advance_existing_projects(
        self,
        *,
        state: CompanyState,
        month_index: int,
    ) -> tuple[
        list[FactoryRecord],
        list[FactoryRecord],
        list[FactoryRecord],
        list[LoggedEvent],
    ]:
        new_active = list(state.factories.active)
        new_construction: list[FactoryRecord] = []
        new_upgrading: list[FactoryRecord] = []
        events: list[LoggedEvent] = []

        for record in state.factories.under_construction:
            if record.months_remaining == 1:
                completed = record.model_copy(
                    update={"status": FactoryStatus.ACTIVE, "months_remaining": None}
                )
                new_active.append(completed)
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.CONSTRUCTION,
                        event_type="construction_completed",
                        company_id=state.company_id,
                        payload={"factory_id": record.identifier},
                    )
                )
            else:
                new_construction.append(
                    record.model_copy(
                        update={"months_remaining": record.months_remaining - 1}
                    )
                )

        for record in state.factories.upgrading:
            if record.months_remaining == 1:
                restored = record.model_copy(
                    update={"status": FactoryStatus.ACTIVE, "months_remaining": None}
                )
                new_active.append(restored)
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.CONSTRUCTION,
                        event_type="upgrade_completed",
                        company_id=state.company_id,
                        payload={"factory_id": record.identifier},
                    )
                )
            else:
                new_upgrading.append(
                    record.model_copy(
                        update={"months_remaining": record.months_remaining - 1}
                    )
                )

        return new_active, new_construction, new_upgrading, events

    def _apply_new_projects(
        self,
        *,
        company_id: str,
        projects: list[dict],
        month_index: int,
        cash_balance: Money,
        buckets: dict[str, list[FactoryRecord]],
    ) -> tuple[Money, dict[str, list[FactoryRecord]], list[LoggedEvent]]:
        events: list[LoggedEvent] = []
        for project in projects:
            kind = (project.get("kind") or "construction").lower()
            identifier = project.get("identifier")
            blueprint_id = project.get("blueprint_id")
            months = int(project.get("months", 0))
            cost_amount = Decimal(str(project.get("cost", "0")))
            if not identifier or not blueprint_id or months <= 0 or cost_amount < 0:
                continue

            cost = Money(
                amount=cost_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                currency=cash_balance.currency,
            )
            if cash_balance.amount < cost.amount:
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.CONSTRUCTION,
                        event_type="project_rejected_insufficient_cash",
                        company_id=company_id,
                        payload={"identifier": identifier, "cost": str(cost.amount)},
                    )
                )
                continue

            cash_balance = cash_balance.subtract(cost)
            if kind in {"upgrade", "upgrading"}:
                target_id = project.get("target_factory_id", identifier)
                active_bucket = buckets["active"]
                existing = None
                for idx, record in enumerate(active_bucket):
                    if record.identifier == target_id:
                        existing = active_bucket.pop(idx)
                        break
                if existing is None:
                    events.append(
                        LoggedEvent(
                            month_index=month_index,
                            phase=PhaseIdentifier.CONSTRUCTION,
                            event_type="upgrade_target_missing",
                            company_id=company_id,
                            payload={"target_factory_id": target_id},
                        )
                    )
                    cash_balance = cash_balance.add(cost)
                    continue

                upgrading_record = existing.model_copy(
                    update={
                        "status": FactoryStatus.UPGRADING,
                        "months_remaining": months,
                    }
                )
                buckets["upgrading"].append(upgrading_record)
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.CONSTRUCTION,
                        event_type="upgrade_started",
                        company_id=company_id,
                        payload={
                            "factory_id": target_id,
                            "months": months,
                            "cost": str(cost.amount),
                        },
                    )
                )
            else:
                record = FactoryRecord(
                    identifier=identifier,
                    blueprint_id=blueprint_id,
                    status=FactoryStatus.UNDER_CONSTRUCTION,
                    months_remaining=months,
                )
                buckets["construction"].append(record)
                events.append(
                    LoggedEvent(
                        month_index=month_index,
                        phase=PhaseIdentifier.CONSTRUCTION,
                        event_type="construction_started",
                        company_id=company_id,
                        payload={
                            "factory_id": identifier,
                            "months": months,
                            "cost": str(cost.amount),
                        },
                    )
                )

        return cash_balance, buckets, events


class EndOfMonthPhaseHandlerImpl(PhaseHandlerModel):
    """Resolve bankruptcies and rotate seniority order."""

    def handle(self, input_data: EndOfMonthPhaseInput) -> EndOfMonthPhaseResult:
        """Finalize month-end state and update aggregate metrics."""
        configuration = input_data.configuration
        previous_market = _find_phase_result(
            input_data.previous_results, PhaseIdentifier.MARKET_ANNOUNCEMENT
        )
        market_metrics = previous_market.metrics if previous_market else {}
        raw_material_floor = _metric_as_decimal(
            market_metrics,
            "raw_material_price_floor",
            configuration.raw_material_price_floor,
        )
        finished_goods_floor = _metric_as_decimal(
            market_metrics,
            "finished_goods_price_floor",
            configuration.finished_goods_price_floor,
        )

        bankrupt_companies = {
            event.company_id
            for event in input_data.previous_events
            if event.phase is PhaseIdentifier.EXPENSES
            and event.event_type == "bankruptcy_flag"
            and event.company_id is not None
        }

        remaining_states: dict[str, CompanyState] = {
            company_id: state
            for company_id, state in input_data.company_states.items()
            if company_id not in bankrupt_companies
        }

        events: list[LoggedEvent] = []
        events.extend(
            LoggedEvent(
                month_index=input_data.month_index,
                phase=PhaseIdentifier.END_OF_MONTH,
                event_type="company_removed",
                company_id=company_id,
                message="Company removed from the session due to bankruptcy.",
            )
            for company_id in bankrupt_companies
        )

        total_capital = Decimal(0)
        for company_id, state in remaining_states.items():
            raw_quantity = state.inventory.quantity(ResourceType.RAW_MATERIAL).amount
            finished_quantity = state.inventory.quantity(
                ResourceType.FINISHED_GOOD
            ).amount
            capital = (
                state.cash.amount
                + raw_material_floor * raw_quantity
                + finished_goods_floor * finished_quantity
            )
            total_capital += capital
            events.append(
                LoggedEvent(
                    month_index=input_data.month_index,
                    phase=PhaseIdentifier.END_OF_MONTH,
                    event_type="capital_recomputed",
                    company_id=company_id,
                    payload={"capital": str(capital)},
                )
            )

        rotated_order = input_data.seniority_order.rotate()
        events.append(
            LoggedEvent(
                month_index=input_data.month_index,
                phase=PhaseIdentifier.END_OF_MONTH,
                event_type="seniority_rotated",
                payload={"new_order": rotated_order.ranking},
            )
        )

        phase_log = _build_phase_log(
            PhaseIdentifier.END_OF_MONTH,
            input_data.month_index,
            input_data.decisions,
            events,
        )
        summary = (
            f"Removed {len(bankrupt_companies)} bankrupt companies and "
            "rotated seniority order."
        )
        return EndOfMonthPhaseResult(
            phase=PhaseIdentifier.END_OF_MONTH,
            month_index=input_data.month_index,
            updated_companies=remaining_states,
            log=phase_log,
            summary=summary,
            metrics={
                "active_company_count": len(remaining_states),
                "bankruptcies_resolved": len(bankrupt_companies),
                "total_capital": total_capital,
            },
        )


__all__ = [
    "ConstructionPhaseHandlerImpl",
    "EndOfMonthPhaseHandlerImpl",
    "ExpensesPhaseHandlerImpl",
    "FinishedGoodsSalePhaseHandlerImpl",
    "LoanManagementPhaseHandlerImpl",
    "MarketAnnouncementPhaseHandlerImpl",
    "ProductionPhaseHandlerImpl",
    "RawMaterialPurchasePhaseHandlerImpl",
]
