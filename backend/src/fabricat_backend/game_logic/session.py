"""Session manager for multiplayer and multi-session games."""

from typing import Literal
from pydantic import BaseModel, Field
from random import Random


class GameSettings(BaseModel):
    """Comprehensive knob set that shapes a session's economic conditions.

    Values remain constant across the run and define starting assets, cash
    flows, build timings, and the central bank's market behavior so the
    simulation can play out deterministically for every participant.
    """

    # TODO: Get settings from BackendSettings, which stores default values
    rng_seed: int = 42

    start_factory_count: int

    basic_factory_monthly_expenses: float
    auto_factory_monthly_expenses: float

    raw_material_monthly_expenses: float
    finished_good_monthly_expenses: float

    bank_start_money: float

    loans_monthly_expenses_in_percents: float
    available_loans: list[float]

    bank_raw_material_sell_volume_range: tuple[int, int]
    bank_finished_good_buy_volume_range: tuple[int, int]

    bank_raw_material_sell_min_price_range: tuple[float, float]
    bank_finished_good_buy_max_price_range: tuple[float, float]

    month_for_upgrade: int
    upgrade_cost: float

    month_for_build_basic: int
    build_basic_cost: float

    month_for_build_auto: int
    build_auto_cost: float


class RawMaterial(BaseModel):
    """Unprocessed inventory unit carrying a recurring storage expense.

    The monthly expense discourages stockpiling indefinitely and becomes a
    primary input for production when factories convert these units into
    finished goods.
    """

    monthly_expenses: float


class FinishedGood(BaseModel):
    """Manufactured product that can be sold to the market or to opponents.

    Even completed goods continue to accrue upkeep, creating pressure on
    players to balance inventory levels with market demand.
    """

    monthly_expenses: float


FactoryType = Literal["basic", "auto", "builds_basic", "builds_auto", "upgrades"]


class Factory(BaseModel):
    """Player-owned facility that can produce goods or undergo transitions.

    The factory tracks both its operational status (basic or automated) and the
    transient states required to build or upgrade the facility. Monthly
    expenses include maintenance during construction to incentivize deliberate
    expansion decisions.
    """

    factory_type: FactoryType
    monthly_expenses: float

    end_build_month: int | None = None
    end_upgrade_month: int | None = None


class Bid(BaseModel):
    """Offer to trade a fixed quantity at a targeted price per unit.

    Buy bids move raw materials from the bank to players, while sell bids push
    finished goods back to the bank; both respect priority ordering when the
    market cannot satisfy everyone simultaneously.
    """

    quantity: int
    price: float


LoanStatus = Literal["call", "in_progress", "idle"]


class Loan(BaseModel):
    """Bank loan slot that tracks issued funds and repayment expectations.

    Each player receives a fixed number of slots; once a slot is in progress it
    accrues interest monthly until the scheduled `return_month` when principal
    is automatically deducted from the player's balance.
    """

    amount: float = 0.0
    return_month: int = 0
    loan_status: LoanStatus = "idle"


class Player(BaseModel):
    """Participant that owns assets, executes strategies, and spends cash.

    Players interact with the bank through bids and loans, manage a roster of
    factories, and orchestrate production plans. The priority field determines
    how they are ordered in competitive resolution steps, creating a dynamic
    turn order that rotates as the game advances.
    """

    id_: int

    money: float
    is_bankrupt: bool = False

    buy_bid: Bid | None = None
    sell_bid: Bid | None = None

    production_call_for_basic: int = 0
    production_call_for_auto: int = 0

    priority: int = Field(
        ...,
        ge=1,
        le=4,
        description="In game priority for tie situations.",
    )

    factories: list[Factory] = Field(default_factory=list)

    build_or_upgrade_call: Literal["idle", "build_basic", "build_auto", "upgrade"] = (
        "idle"
    )

    raw_materials: list[RawMaterial] = Field(default_factory=list)
    finished_goods: list[FinishedGood] = Field(default_factory=list)

    loans: list[Loan] = Field(default_factory=lambda: [Loan(), Loan()])

    def collect_expenses(self) -> None:
        """Apply the monthly upkeep of every owned asset to the cash balance.

        Factories, raw materials, and finished goods each subtract their
        recurring costs, ensuring the player's liquidity reflects all holdings
        before other actions execute in the monthly cycle.
        """

        for factory in self.factories:
            self.money -= factory.monthly_expenses

        for raw_material in self.raw_materials:
            self.money -= raw_material.monthly_expenses

        for finished_good in self.finished_goods:
            self.money -= finished_good.monthly_expenses


class Bank(BaseModel):
    """Central counter-party that backs the economy with liquidity and trades.

    The bank supplies raw materials, purchases finished goods, and serves as
    the sole lender. Its randomized market parameters keep each month
    unpredictable while remaining reproducible through the session RNG seed.
    """

    rng: Random

    money: float

    available_loans: list[float]

    raw_material_sell_volume: int = 0
    finished_good_buy_volume: int = 0

    raw_material_sell_min_price: float = 0.0
    finished_good_buy_max_price: float = 0.0

    raw_material_sell_volume_range: tuple[int, int]
    finished_good_buy_volume_range: tuple[int, int]

    raw_material_sell_min_price_range: tuple[float, float]
    finished_good_buy_max_price_range: tuple[float, float]

    def set_market(self) -> None:
        """Sample supply, demand, and prices for the upcoming month.

        The method draws fresh values from the configured ranges so subsequent
        bidding rounds operate against an updated market, giving players new
        incentives each month.
        """

        self.raw_material_sell_volume = self.rng.randint(
            self.raw_material_sell_volume_range[0],
            self.raw_material_sell_volume_range[1],
        )

        self.finished_good_buy_volume = self.rng.randint(
            self.finished_good_buy_volume_range[0],
            self.finished_good_buy_volume_range[1],
        )

        self.raw_material_sell_min_price = self.rng.uniform(
            self.raw_material_sell_min_price_range[0],
            self.raw_material_sell_min_price_range[1],
        )

        self.finished_good_buy_max_price = self.rng.uniform(
            self.finished_good_buy_max_price_range[0],
            self.finished_good_buy_max_price_range[1],
        )


class GameState(BaseModel):
    """Dynamic rule snapshot that evolves as turns progress.

    Unlike the immutable game settings, this model captures mutable parameters
    such as the current month counter and production efficiencies that may
    shift as players build or upgrade factories.
    """

    month: int = 1

    raw_material_monthly_expenses: float
    finished_good_monthly_expenses: float

    basic_factory_production: int = 1
    auto_factory_production: int = 2

    basic_factory_monthly_expenses: float
    auto_factory_monthly_expenses: float

    loans_monthly_expenses_in_percents: float

    month_for_upgrade: int
    upgrade_cost: float

    month_for_build_basic: int
    build_basic_cost: float

    month_for_build_auto: int
    build_auto_cost: float


class GameSession:
    """High-level orchestrator that plays out the economic game loop.

    It wires players, the bank, and the evolving game state together, exposing
    lifecycle hooks that represent the major phases of each month in the
    simulation.
    """

    def __init__(self, players: list[Player], settings: GameSettings) -> None:
        """Initialize players, state, and bank according to the settings.

        The constructor stores the player roster and delegates to `_init_game`
        so the session has a populated state snapshot and bank before any
        gameplay methods run.
        """
        self._players = players

        self._init_game(settings)
        self._init_factories(settings)

    def _init_factories(self, settings: GameSettings) -> None:
        """Grant each player their starting complement of basic factories.

        This helper is also used when seeding the session to guarantee every
        competitor begins with the same productive capacity.
        """
        for player in self._players:
            for _ in range(settings.start_factory_count):
                player.factories.append(
                    Factory(
                        factory_type="basic",
                        monthly_expenses=settings.basic_factory_monthly_expenses,
                    )
                )

    def _init_game(self, settings: GameSettings) -> None:
        """Construct initial game state and bank infrastructure.

        The method creates the `GameState` based on provided settings and spins
        up the `Bank` using the same configuration. Factory seeding is handled
        separately through `_init_factories` so callers can control when player
        inventories are populated.
        """
        self._state = GameState(
            raw_material_monthly_expenses=settings.raw_material_monthly_expenses,
            finished_good_monthly_expenses=settings.finished_good_monthly_expenses,
            loans_monthly_expenses_in_percents=settings.loans_monthly_expenses_in_percents,
            month_for_upgrade=settings.month_for_upgrade,
            upgrade_cost=settings.upgrade_cost,
            month_for_build_basic=settings.month_for_build_basic,
            build_basic_cost=settings.build_basic_cost,
            month_for_build_auto=settings.month_for_build_auto,
            build_auto_cost=settings.build_auto_cost,
            basic_factory_monthly_expenses=settings.basic_factory_monthly_expenses,
            auto_factory_monthly_expenses=settings.auto_factory_monthly_expenses,
        )
        self._bank = Bank(
            rng=Random(settings.rng_seed),  # noqa: S311
            money=settings.bank_start_money,
            available_loans=settings.available_loans,
            raw_material_sell_volume_range=settings.bank_raw_material_sell_volume_range,
            finished_good_buy_volume_range=settings.bank_finished_good_buy_volume_range,
            raw_material_sell_min_price_range=settings.bank_raw_material_sell_min_price_range,
            finished_good_buy_max_price_range=settings.bank_finished_good_buy_max_price_range,
        )

    @staticmethod
    def _sort_players_buy(player: Player) -> tuple[float, int]:
        """Return a composite key for ordering buy bids.

        Lower bid prices sort toward the front, and ties fall back to player
        priority so the most privileged player gets first access when supply is
        scarce.
        """
        bid = player.buy_bid
        return bid.price if bid else -1, -player.priority

    @staticmethod
    def _sort_players_sell(player: Player) -> tuple[float, int]:
        """Return a composite key for ordering sell bids.

        Lower asking prices are considered first, then by priority to resolve
        collisions when the bank cannot purchase every unit on offer.
        """
        bid = player.sell_bid
        return bid.price if bid else -1, -player.priority

    def collect_expenses(self) -> None:
        """Apply operating costs to every player.

        Delegates to each player's `collect_expenses` so all ongoing costs are
        deducted before market interactions begin for the month.
        """
        for player in self._players:
            player.collect_expenses()

    def set_market(self) -> None:
        """Refresh the bank's market conditions for the new month.

        The bank samples new ranges for supply, demand, and price, creating a
        fresh environment for the upcoming buy and sell phases.
        """
        self._bank.set_market()

    def process_buy_bids(self) -> None:
        """Execute buy orders against the bank's raw material supply.

        Players are processed by the sort order provided in `_sort_players_buy`,
        prioritizing cheaper bids before falling back to turn priority. Every
        successful purchase transfers money to the bank and grants the player
        a fresh `RawMaterial` entry subject to ongoing expenses.
        """
        for player in sorted(self._players, key=GameSession._sort_players_buy):
            if player.buy_bid is None:
                continue

            bid = player.buy_bid

            for _ in range(bid.quantity):
                if self._bank.raw_material_sell_volume > 0:
                    self._bank.raw_material_sell_volume -= 1
                    self._bank.money += bid.price

                    player.money -= bid.price
                    player.raw_materials.append(
                        RawMaterial(
                            monthly_expenses=self._state.raw_material_monthly_expenses,
                        )
                    )

    def start_production(self) -> None:
        """Consume raw materials to produce finished goods within capacity.

        The method calculates the total output based on each player's mix of
        factory types, respects requested production calls, and converts the
        necessary raw materials into finished goods.
        """
        for player in self._players:
            basic_count = sum(
                self._state.basic_factory_production
                for f in player.factories
                if f.factory_type == "basic"
            )
            auto_count = sum(
                self._state.auto_factory_production
                for f in player.factories
                if f.factory_type == "auto"
            )

            success_call_basic = min(
                basic_count,
                player.production_call_for_basic,
            )

            success_call_auto = min(
                auto_count,
                player.production_call_for_auto,
            )

            player.production_call_for_basic -= success_call_basic
            player.production_call_for_auto -= success_call_auto

            for _ in range(success_call_basic + success_call_auto):
                player.raw_materials.pop()
                player.finished_goods.append(
                    FinishedGood(
                        monthly_expenses=self._state.finished_good_monthly_expenses,
                    )
                )

    def process_sell_bids(self) -> None:
        """Settle sale orders with the bank based on available demand.

        Using `_sort_players_sell`, the method iterates through sellers and
        honors their offers while the bank still has demand volume, moving cash
        back to the player in exchange for finished goods.
        """
        for player in sorted(self._players, key=GameSession._sort_players_sell):
            if player.sell_bid is None:
                continue

            bid = player.sell_bid

            for _ in range(bid.quantity):
                if self._bank.finished_good_buy_volume > 0:
                    self._bank.finished_good_buy_volume -= 1
                    self._bank.money -= bid.price

                    player.money += bid.price
                    player.finished_goods.pop()

    def process_loans(self) -> None:
        """Update loan balances, collect repayments, and fund new calls.

        Players are examined from highest to lowest priority. Interest is
        deducted based on outstanding loan amounts, matured loans are settled
        automatically, and new loan requests are funded when the bank has
        available slots.
        """
        for player in sorted(self._players, key=lambda p: -p.priority):
            if all(loan.loan_status == "idle" for loan in player.loans):
                continue

            total_amount = sum(
                loan.amount
                for loan in player.loans
                if loan.loan_status == "in_progress"
            )

            player.money -= (
                total_amount * self._state.loans_monthly_expenses_in_percents
            )

            to_return = sum(
                loan.amount
                for loan in player.loans
                if loan.loan_status == "in_progress"
                and loan.return_month == self._state.month
            )

            player.money -= to_return

            for idx, loan in enumerate(player.loans):
                if loan.loan_status != "call" or self._bank.available_loans[idx] <= 0:
                    continue

                loan.amount += self._bank.available_loans[idx]
                player.money += self._bank.available_loans[idx]

                self._bank.available_loans[idx] = 0.0
                loan.loan_status = "in_progress"

    def build_or_upgrade(self) -> None:
        """Advance construction projects and kick off requested builds.

        Existing projects are checked for completion, adjusting factory states
        and charging remaining costs; new build or upgrade calls are then
        initiated, including the immediate partial payments required.
        """
        for player in self._players:
            for factory in player.factories:
                match factory.factory_type:
                    case "builds_basic":
                        if factory.end_build_month == self._state.month:
                            player.money -= self._state.build_basic_cost * 0.5
                            factory.factory_type = "basic"
                    case "builds_auto":
                        if factory.end_build_month == self._state.month:
                            player.money -= self._state.build_auto_cost * 0.5
                            factory.factory_type = "auto"
                    case "upgrades":
                        if factory.end_upgrade_month == self._state.month:
                            factory.factory_type = "auto"
                            factory.monthly_expenses = (
                                self._state.auto_factory_monthly_expenses
                            )
                    case _:
                        continue

            match player.build_or_upgrade_call:
                case "idle":
                    continue
                case "build_basic":
                    factory = Factory(
                        factory_type="builds_basic",
                        monthly_expenses=self._state.basic_factory_monthly_expenses,
                        end_build_month=self._state.month
                        + self._state.month_for_build_basic,
                    )
                    player.money -= self._state.build_basic_cost * 0.5
                case "build_auto":
                    factory = Factory(
                        factory_type="builds_auto",
                        monthly_expenses=self._state.auto_factory_monthly_expenses,
                        end_build_month=self._state.month
                        + self._state.month_for_build_auto,
                    )
                    player.money -= self._state.build_auto_cost * 0.5
                case "upgrade":
                    factory = next(
                        (f for f in player.factories if f.factory_type == "basic"),
                        None,
                    )

                    if factory is None:
                        continue

                    factory.factory_type = "upgrades"
                    factory.end_upgrade_month = (
                        self._state.month + self._state.month_for_upgrade
                    )
                    player.money -= self._state.upgrade_cost

    def end_month(self) -> None:
        """Finalize month-end bookkeeping, including bankruptcy checks.

        Players who have run out of cash are marked bankrupt, and the priority
        order rotates so turn order reshuffles for the next month.
        """
        for player in self._players:
            if player.money <= 0:
                player.is_bankrupt = True

            player.priority -= 1

            if player.priority <= 0:
                player.priority = len(self._players)
