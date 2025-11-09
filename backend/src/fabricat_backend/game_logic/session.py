"""Session manager for multiplayer and multi-session games."""

from collections.abc import Callable
from datetime import UTC, datetime
from math import ceil
from random import Random
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from fabricat_backend.game_logic.phases import (
    GamePhase,
    PhaseAnalytics,
    PhaseJournalEntry,
    PhaseReport,
    PlayerPhaseAnalytics,
)


class GameSettings(BaseModel):
    """Comprehensive knob set that shapes a session's economic conditions.

    Values remain constant across the run and define starting assets, cash
    flows, build timings, and the central bank's market behavior so the
    simulation can play out deterministically for every participant.
    """

    # Settings currently mirror README defaults until BackendSettings grows presets.
    rng_seed: int = 42

    start_factory_count: int
    max_months: int

    basic_factory_monthly_expenses: float
    auto_factory_monthly_expenses: float

    raw_material_monthly_expenses: float
    finished_good_monthly_expenses: float

    basic_factory_launch_cost: float
    auto_factory_launch_cost: float

    bank_start_money: float

    loans_monthly_expenses_in_percents: float
    available_loans: list[float]
    loan_terms_in_months: list[int]

    bank_raw_material_sell_volume_range: tuple[int, int]
    bank_finished_good_buy_volume_range: tuple[int, int]

    bank_raw_material_sell_min_price_range: tuple[float, float]
    bank_finished_good_buy_max_price_range: tuple[float, float]

    max_raw_material_storage: int
    max_finished_good_storage: int

    month_for_upgrade: int
    upgrade_cost: float

    month_for_build_basic: int
    build_basic_cost: float

    month_for_build_auto: int
    build_auto_cost: float

    build_basic_payment_share: float
    build_basic_final_payment_offset: int
    build_auto_payment_share: float
    build_auto_final_payment_offset: int

    max_factories: int


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
    next_payment_month: int | None = None
    next_payment_amount: float = 0.0


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


class SeniorityRollLogEntry(BaseModel):
    """Record describing a single tie-break roll attempt."""

    attempt: int
    player_id: int
    value: int


class SenioritySnapshot(BaseModel):
    """Stores the seniority order for a given month."""

    month: int
    order: list[int]


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

    def pay(self, amount: float) -> bool:
        """Attempt to deduct money; bankrupt immediately if funds are insufficient."""
        if amount <= 0:
            return True

        if self.money < amount:
            self.money = 0.0
            self.is_bankrupt = True
            return False

        self.money -= amount
        return True

    def collect_expenses(self) -> None:
        """Apply the monthly upkeep of every owned asset to the cash balance.

        Factories, raw materials, and finished goods each subtract their
        recurring costs, ensuring the player's liquidity reflects all holdings
        before other actions execute in the monthly cycle.
        """
        for factory in self.factories:
            if not self.pay(factory.monthly_expenses):
                return

        for raw_material in self.raw_materials:
            if not self.pay(raw_material.monthly_expenses):
                return

        for finished_good in self.finished_goods:
            if not self.pay(finished_good.monthly_expenses):
                return


class Bank(BaseModel):
    """Central counter-party that backs the economy with liquidity and trades.

    The bank supplies raw materials, purchases finished goods, and serves as
    the sole lender. Its randomized market parameters keep each month
    unpredictable while remaining reproducible through the session RNG seed.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rng: Random

    money: float

    available_loans: list[float]
    loan_nominals: list[float]
    loan_terms_in_months: list[int]

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
    max_months: int

    raw_material_monthly_expenses: float
    finished_good_monthly_expenses: float

    basic_factory_launch_cost: float
    auto_factory_launch_cost: float

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

    max_raw_material_storage: int
    max_finished_good_storage: int
    build_basic_payment_share: float
    build_basic_final_payment_offset: int
    build_auto_payment_share: float
    build_auto_final_payment_offset: int
    max_factories: int


class GameSession:
    """High-level orchestrator that plays out the economic game loop.

    It wires players, the bank, and the evolving game state together, exposing
    lifecycle hooks that represent the major phases of each month in the
    simulation.
    """

    def __init__(
        self,
        players: list[Player],
        settings: GameSettings,
        *,
        rng: Random | None = None,
        seed_seniority: bool = True,
    ) -> None:
        """Initialize players, state, and bank according to the settings.

        The constructor stores the player roster and delegates to `_init_game`
        so the session has a populated state snapshot and bank before any
        gameplay methods run.
        """
        self._players = players
        self._total_players = len(players)
        self._is_finished = False
        self._winner_id: int | None = None
        self._rng = rng or Random(settings.rng_seed)  # noqa: S311
        self._journal: list[PhaseJournalEntry] = []
        self._phase_reports: list[PhaseReport] = []
        self._phase_event_buffer: list[PhaseJournalEntry] = []
        self._active_phase: GamePhase | None = None
        self._active_phase_month: int | None = None
        self._seniority_rolls: list[SeniorityRollLogEntry] = []
        self._seniority_history: list[SenioritySnapshot] = []

        self._init_game(settings)
        self._init_factories(settings)
        if seed_seniority:
            self._seed_seniority_order()
        else:
            snapshot = SenioritySnapshot(
                month=self._state.month,
                order=[
                    player.id_
                    for player in sorted(self._players, key=lambda p: p.priority)
                ],
            )
            self._seniority_history.append(snapshot)

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

    def _seed_seniority_order(self) -> None:
        """Assign initial seniority via 1d6 rolls with tie re-rolls."""
        ordered_players = self._resolve_seniority_rolls(
            players=list(self._players),
            attempt=1,
        )
        for idx, player in enumerate(ordered_players, start=1):
            player.priority = idx

        snapshot = SenioritySnapshot(
            month=self._state.month,
            order=[player.id_ for player in ordered_players],
        )
        self._seniority_history.append(snapshot)

    def _resolve_seniority_rolls(
        self,
        *,
        players: list[Player],
        attempt: int,
    ) -> list[Player]:
        """Recursively resolve seniority via repeated 1d6 rolls."""
        if not players:
            return []

        rolls: list[tuple[Player, int]] = []
        for player in players:
            value = self._rng.randint(1, 6)
            rolls.append((player, value))
            self._seniority_rolls.append(
                SeniorityRollLogEntry(
                    attempt=attempt,
                    player_id=player.id_,
                    value=value,
                )
            )

        rolls.sort(key=lambda item: item[1])
        result: list[Player] = []
        idx = 0
        while idx < len(rolls):
            current_value = rolls[idx][1]
            tied_players = [rolls[idx][0]]
            idx += 1
            while idx < len(rolls) and rolls[idx][1] == current_value:
                tied_players.append(rolls[idx][0])
                idx += 1

            if len(tied_players) == 1:
                result.append(tied_players[0])
                continue

            result.extend(
                self._resolve_seniority_rolls(
                    players=tied_players,
                    attempt=attempt + 1,
                )
            )

        return result

    def _init_game(self, settings: GameSettings) -> None:
        """Construct initial game state and bank infrastructure.

        The method creates the `GameState` based on provided settings and spins
        up the `Bank` using the same configuration. Factory seeding is handled
        separately through `_init_factories` so callers can control when player
        inventories are populated.
        """
        self._state = GameState(
            max_months=settings.max_months,
            raw_material_monthly_expenses=settings.raw_material_monthly_expenses,
            finished_good_monthly_expenses=settings.finished_good_monthly_expenses,
            basic_factory_launch_cost=settings.basic_factory_launch_cost,
            auto_factory_launch_cost=settings.auto_factory_launch_cost,
            loans_monthly_expenses_in_percents=settings.loans_monthly_expenses_in_percents,
            month_for_upgrade=settings.month_for_upgrade,
            upgrade_cost=settings.upgrade_cost,
            month_for_build_basic=settings.month_for_build_basic,
            build_basic_cost=settings.build_basic_cost,
            month_for_build_auto=settings.month_for_build_auto,
            build_auto_cost=settings.build_auto_cost,
            basic_factory_monthly_expenses=settings.basic_factory_monthly_expenses,
            auto_factory_monthly_expenses=settings.auto_factory_monthly_expenses,
            max_raw_material_storage=settings.max_raw_material_storage,
            max_finished_good_storage=settings.max_finished_good_storage,
            build_basic_payment_share=settings.build_basic_payment_share,
            build_basic_final_payment_offset=settings.build_basic_final_payment_offset,
            build_auto_payment_share=settings.build_auto_payment_share,
            build_auto_final_payment_offset=settings.build_auto_final_payment_offset,
            max_factories=settings.max_factories,
        )
        if len(settings.available_loans) != len(settings.loan_terms_in_months):
            msg = "Loan amounts and term configuration mismatch."
            raise ValueError(msg)
        self._bank = Bank(
            rng=Random(settings.rng_seed + 1),  # noqa: S311
            money=settings.bank_start_money,
            available_loans=list(settings.available_loans),
            loan_nominals=list(settings.available_loans),
            loan_terms_in_months=settings.loan_terms_in_months,
            raw_material_sell_volume_range=settings.bank_raw_material_sell_volume_range,
            finished_good_buy_volume_range=settings.bank_finished_good_buy_volume_range,
            raw_material_sell_min_price_range=settings.bank_raw_material_sell_min_price_range,
            finished_good_buy_max_price_range=settings.bank_finished_good_buy_max_price_range,
        )

    def _active_players(self) -> list[Player]:
        """Return non-bankrupt players."""
        return [player for player in self._players if not player.is_bankrupt]

    def _completed_months(self) -> int:
        """Return the number of fully completed months."""
        return max(self._state.month - 1, 0)

    def _determine_winner_id(self, candidates: list[Player]) -> int | None:
        """Pick the player with the highest capital (tie-break by priority/id)."""
        if not candidates:
            return None

        best_player = max(
            candidates,
            key=lambda player: (
                self.calculate_capital(player),
                -player.priority,
                -player.id_,
            ),
        )
        return best_player.id_

    def _evaluate_game_completion(self) -> None:
        """Stop the session once victory conditions trigger."""
        if self._is_finished:
            return

        active_players = self._active_players()

        if self._total_players > 1 and len(active_players) <= 1:
            self._is_finished = True
            self._winner_id = active_players[0].id_ if active_players else None
            return

        if self._completed_months() >= self._state.max_months:
            self._is_finished = True
            self._winner_id = self._determine_winner_id(active_players)

    def calculate_capital(self, player: Player) -> float:
        """Compute the player's capital snapshot."""
        factory_value = 0.0
        outstanding_payments = 0.0

        for factory in player.factories:
            match factory.factory_type:
                case "auto" | "builds_auto":
                    factory_value += self._state.build_auto_cost
                case "basic" | "builds_basic" | "upgrades":
                    factory_value += self._state.build_basic_cost
            outstanding_payments += max(factory.next_payment_amount, 0.0)

        raw_value = len(player.raw_materials) * self._bank.raw_material_sell_min_price
        finished_value = (
            len(player.finished_goods) * self._bank.finished_good_buy_max_price
        )
        loan_debt = sum(
            loan.amount for loan in player.loans if loan.loan_status == "in_progress"
        )

        return (
            player.money
            + factory_value
            + raw_value
            + finished_value
            - loan_debt
            - outstanding_payments
        )

    def _phase_handler_for(self, phase: GamePhase) -> Callable[[], None]:
        """Return the method that corresponds to the requested phase."""
        handlers: dict[GamePhase, Callable[[], None]] = {
            GamePhase.EXPENSES: self.collect_expenses,
            GamePhase.MARKET: self.set_market,
            GamePhase.BUY: self.process_buy_bids,
            GamePhase.PRODUCTION: self.start_production,
            GamePhase.SELL: self.process_sell_bids,
            GamePhase.LOANS: self.process_loans,
            GamePhase.CONSTRUCTION: self.build_or_upgrade,
            GamePhase.END_MONTH: self.end_month,
        }
        try:
            return handlers[phase]
        except KeyError as exc:  # pragma: no cover - guarded by enum usage
            msg = f"Unsupported phase: {phase}"
            raise ValueError(msg) from exc

    def _log_phase_event(
        self,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Append a log entry for the currently running phase."""
        if self._active_phase is None or self._active_phase_month is None:
            return

        entry = PhaseJournalEntry(
            month=self._active_phase_month,
            phase=self._active_phase,
            message=message,
            payload=payload or {},
        )
        self._phase_event_buffer.append(entry)

    def _build_phase_analytics(self) -> PhaseAnalytics:
        """Build aggregated analytics payload for the current roster."""
        players = [
            PlayerPhaseAnalytics(
                player_id=player.id_,
                money=player.money,
                raw_materials=len(player.raw_materials),
                finished_goods=len(player.finished_goods),
                factories=len(player.factories),
                bankrupt=player.is_bankrupt,
                active_loans=sum(
                    1 for loan in player.loans if loan.loan_status == "in_progress"
                ),
            )
            for player in self._players
        ]
        bankrupt_ids = [player.player_id for player in players if player.bankrupt]
        return PhaseAnalytics(players=players, bankrupt_players=bankrupt_ids)

    def snapshot_analytics(self) -> PhaseAnalytics:
        """Return the latest analytics snapshot without running a phase."""
        return self._build_phase_analytics()

    def run_phase(self, phase: GamePhase) -> PhaseReport:
        """Execute the given phase and return a structured report."""
        handler = self._phase_handler_for(phase)
        month = self._state.month
        self._active_phase = phase
        self._active_phase_month = month
        self._phase_event_buffer = []

        handler()

        report = PhaseReport(
            phase=phase,
            month=month,
            completed_at=datetime.now(tz=UTC),
            journal=list(self._phase_event_buffer),
            analytics=self._build_phase_analytics(),
        )
        self._phase_reports.append(report)
        self._journal.extend(self._phase_event_buffer)

        self._phase_event_buffer = []
        self._active_phase = None
        self._active_phase_month = None
        return report

    @property
    def is_finished(self) -> bool:
        """Whether the session already satisfied a victory condition."""
        return self._is_finished

    @property
    def winner(self) -> Player | None:
        """Return the winning player, if determined."""
        if self._winner_id is None:
            return None

        return next((p for p in self._players if p.id_ == self._winner_id), None)

    @property
    def month(self) -> int:
        """Current month number."""
        return self._state.month

    @property
    def action_journal(self) -> list[PhaseJournalEntry]:
        """Return a copy of the accumulated action journal."""
        return list(self._journal)

    @property
    def phase_reports(self) -> list[PhaseReport]:
        """Return all published phase reports."""
        return list(self._phase_reports)

    @property
    def seniority_history(self) -> list[SenioritySnapshot]:
        """Return the recorded seniority order per month."""
        return list(self._seniority_history)

    @property
    def tie_break_log(self) -> list[SeniorityRollLogEntry]:
        """Return the raw dice rolls used to resolve seniority ties."""
        return list(self._seniority_rolls)

    @staticmethod
    def _sort_players_buy(player: Player) -> tuple[float, int]:
        """Return a composite key for ordering buy bids.

        Higher bid prices go first, and ties fall back to player priority so
        the most privileged player gets first access when supply is scarce.
        """
        bid = player.buy_bid
        if bid is None:
            return float("inf"), player.priority

        # Higher bid price should go first, then the smallest priority value.
        return -bid.price, player.priority

    @staticmethod
    def _sort_players_sell(player: Player) -> tuple[float, int]:
        """Return a composite key for ordering sell bids.

        Lower asking prices are considered first, then by priority to resolve
        collisions when the bank cannot purchase every unit on offer.
        """
        bid = player.sell_bid
        if bid is None:
            return float("inf"), player.priority

        return bid.price, player.priority

    def collect_expenses(self) -> None:
        """Apply operating costs to every player.

        Delegates to each player's `collect_expenses` so all ongoing costs are
        deducted before market interactions begin for the month.
        """
        if self._is_finished:
            return

        for player in self._players:
            if player.is_bankrupt:
                continue

            cash_before = player.money
            player.collect_expenses()
            self._log_phase_event(
                "expenses_deducted",
                {
                    "player_id": player.id_,
                    "cash_before": cash_before,
                    "cash_after": player.money,
                    "bankrupt": player.is_bankrupt,
                },
            )

        self._evaluate_game_completion()

    def set_market(self) -> None:
        """Refresh the bank's market conditions for the new month.

        The bank samples new ranges for supply, demand, and price, creating a
        fresh environment for the upcoming buy and sell phases.
        """
        if self._is_finished:
            return

        self._bank.set_market()
        self._log_phase_event(
            "market_announced",
            {
                "raw_material_volume": self._bank.raw_material_sell_volume,
                "finished_good_volume": self._bank.finished_good_buy_volume,
                "raw_material_min_price": self._bank.raw_material_sell_min_price,
                "finished_good_max_price": self._bank.finished_good_buy_max_price,
            },
        )

    def process_buy_bids(self) -> None:
        """Execute buy orders against the bank's raw material supply.

        Players are processed by the sort order provided in `_sort_players_buy`,
        prioritizing higher bid prices before falling back to turn priority.
        Every successful purchase transfers money to the bank and grants the
        player a fresh `RawMaterial` entry subject to ongoing expenses.
        """
        if self._is_finished:
            return

        for player in sorted(self._players, key=GameSession._sort_players_buy):
            if player.is_bankrupt or player.buy_bid is None:
                continue

            bid = player.buy_bid
            if bid.quantity <= 0:
                continue

            if bid.price < self._bank.raw_material_sell_min_price:
                continue

            purchased = 0

            while (
                purchased < bid.quantity
                and self._bank.raw_material_sell_volume > 0
                and len(player.raw_materials) < self._state.max_raw_material_storage
                and player.money >= bid.price
            ):
                self._bank.raw_material_sell_volume -= 1
                self._bank.money += bid.price

                player.money -= bid.price
                player.raw_materials.append(
                    RawMaterial(
                        monthly_expenses=self._state.raw_material_monthly_expenses,
                    )
                )
                purchased += 1

            if purchased > 0:
                self._log_phase_event(
                    "buy_bid_fulfilled",
                    {
                        "player_id": player.id_,
                        "units": purchased,
                        "price": bid.price,
                        "remaining_supply": self._bank.raw_material_sell_volume,
                    },
                )

    @staticmethod
    def _resolve_production_runs(  # noqa: PLR0913
        *,
        requested_units: int,
        factory_count: int,
        units_per_factory: int,
        available_rm: int,
        available_fg_space: int,
        available_money: float,
        launch_cost: float,
    ) -> tuple[int, int, float]:
        """Return produced units, runs performed, and total launch cost."""
        if (
            requested_units <= 0
            or factory_count <= 0
            or available_rm <= 0
            or available_fg_space <= 0
        ):
            return 0, 0, 0.0

        max_units = min(
            requested_units,
            factory_count * units_per_factory,
            available_rm,
            available_fg_space,
        )

        if max_units <= 0:
            return 0, 0, 0.0

        runs_needed = ceil(max_units / units_per_factory)
        if launch_cost <= 0:
            affordable_runs = runs_needed
        else:
            affordable_runs = min(
                runs_needed,
                int(available_money // launch_cost),
            )

        if affordable_runs <= 0:
            return 0, 0, 0.0

        produced_units = min(max_units, affordable_runs * units_per_factory)
        runs_performed = ceil(produced_units / units_per_factory)
        cost = runs_performed * launch_cost
        return produced_units, runs_performed, cost

    def start_production(self) -> None:
        """Consume raw materials to produce finished goods within capacity.

        The method calculates the total output based on each player's mix of
        factory types, respects requested production calls, and converts the
        necessary raw materials into finished goods.
        """
        if self._is_finished:
            return

        for player in self._players:
            if player.is_bankrupt:
                continue

            available_rm = len(player.raw_materials)
            available_fg_space = self._state.max_finished_good_storage - len(
                player.finished_goods
            )

            if available_rm <= 0 or available_fg_space <= 0:
                continue

            basic_factories = sum(
                1
                for factory in player.factories
                if factory.factory_type in {"basic", "upgrades"}
            )
            auto_factories = sum(
                1 for factory in player.factories if factory.factory_type == "auto"
            )

            basic_units, _, basic_cost = self._resolve_production_runs(
                requested_units=player.production_call_for_basic,
                factory_count=basic_factories,
                units_per_factory=self._state.basic_factory_production,
                available_rm=available_rm,
                available_fg_space=available_fg_space,
                available_money=player.money,
                launch_cost=self._state.basic_factory_launch_cost,
            )

            if basic_units > 0 and player.pay(basic_cost):
                available_rm -= basic_units
                available_fg_space -= basic_units
                player.production_call_for_basic = max(
                    player.production_call_for_basic - basic_units,
                    0,
                )
            else:
                basic_units = 0

            auto_units, _, auto_cost = self._resolve_production_runs(
                requested_units=player.production_call_for_auto,
                factory_count=auto_factories,
                units_per_factory=self._state.auto_factory_production,
                available_rm=available_rm,
                available_fg_space=available_fg_space,
                available_money=player.money,
                launch_cost=self._state.auto_factory_launch_cost,
            )

            if auto_units > 0 and player.pay(auto_cost):
                available_rm -= auto_units
                available_fg_space -= auto_units
                player.production_call_for_auto = max(
                    player.production_call_for_auto - auto_units,
                    0,
                )
            else:
                auto_units = 0

            total_units = basic_units + auto_units
            if total_units <= 0:
                continue

            del player.raw_materials[-total_units:]
            player.finished_goods.extend(
                FinishedGood(
                    monthly_expenses=self._state.finished_good_monthly_expenses,
                )
                for _ in range(total_units)
            )
            self._log_phase_event(
                "production_launched",
                {
                    "player_id": player.id_,
                    "produced_units": total_units,
                    "launch_cost": basic_cost + auto_cost,
                    "raw_materials_after": len(player.raw_materials),
                    "finished_goods_after": len(player.finished_goods),
                },
            )

        self._evaluate_game_completion()

    def process_sell_bids(self) -> None:
        """Settle sale orders with the bank based on available demand.

        Using `_sort_players_sell`, the method iterates through sellers and
        honors their offers while the bank still has demand volume, moving cash
        back to the player in exchange for finished goods.
        """
        if self._is_finished:
            return

        for player in sorted(self._players, key=GameSession._sort_players_sell):
            if player.is_bankrupt or player.sell_bid is None:
                continue

            bid = player.sell_bid
            if bid.quantity <= 0:
                continue

            if bid.price > self._bank.finished_good_buy_max_price:
                continue

            sold = 0

            while (
                sold < bid.quantity
                and self._bank.finished_good_buy_volume > 0
                and player.finished_goods
            ):
                self._bank.finished_good_buy_volume -= 1
                self._bank.money -= bid.price

                player.money += bid.price
                player.finished_goods.pop()
                sold += 1

            if sold > 0:
                self._log_phase_event(
                    "sell_bid_cleared",
                    {
                        "player_id": player.id_,
                        "units": sold,
                        "price": bid.price,
                        "remaining_demand": self._bank.finished_good_buy_volume,
                    },
                )

    def process_loans(self) -> None:  # noqa: C901, PLR0912
        """Update loan balances, collect repayments, and fund new calls.

        Players are examined from highest to lowest priority. Interest is
        deducted based on outstanding loan amounts, matured loans are settled
        automatically, and new loan requests are funded when the bank has
        available slots.
        """
        if self._is_finished:
            return

        for player in sorted(self._players, key=lambda p: p.priority):
            if player.is_bankrupt:
                continue

            interest_paid = 0.0
            principal_paid = 0.0
            loans_issued: list[float] = []

            if all(loan.loan_status == "idle" for loan in player.loans):
                continue

            for loan in player.loans:
                if loan.loan_status != "in_progress":
                    continue

                interest = loan.amount * self._state.loans_monthly_expenses_in_percents
                if interest <= 0:
                    continue

                if not player.pay(interest):
                    break

                self._bank.money += interest
                interest_paid += interest

            if player.is_bankrupt:
                if interest_paid > 0:
                    self._log_phase_event(
                        "loan_activity",
                        {
                            "player_id": player.id_,
                            "interest_paid": interest_paid,
                            "principal_paid": principal_paid,
                            "loans_issued": loans_issued,
                            "bankrupt": player.is_bankrupt,
                        },
                    )
                continue

            for idx, loan in enumerate(player.loans):
                if (
                    loan.loan_status != "in_progress"
                    or loan.return_month != self._state.month
                ):
                    continue

                if not player.pay(loan.amount):
                    break

                self._bank.money += loan.amount
                principal_paid += loan.amount
                loan.amount = 0.0
                loan.return_month = 0
                loan.loan_status = "idle"
                self._bank.available_loans[idx] = self._bank.loan_nominals[idx]

            if player.is_bankrupt:
                self._log_phase_event(
                    "loan_activity",
                    {
                        "player_id": player.id_,
                        "interest_paid": interest_paid,
                        "principal_paid": principal_paid,
                        "loans_issued": loans_issued,
                        "bankrupt": player.is_bankrupt,
                    },
                )
                continue

            for idx, loan in enumerate(player.loans):
                if loan.loan_status != "call":
                    continue

                available_amount = self._bank.available_loans[idx]
                if available_amount <= 0 or self._bank.money < available_amount:
                    continue

                self._bank.available_loans[idx] = 0.0
                loan.amount = available_amount
                loan.return_month = (
                    self._state.month + self._bank.loan_terms_in_months[idx]
                )
                loan.loan_status = "in_progress"
                player.money += available_amount
                self._bank.money -= available_amount
                loans_issued.append(available_amount)

            if (
                interest_paid > 0
                or principal_paid > 0
                or loans_issued
                or player.is_bankrupt
            ):
                self._log_phase_event(
                    "loan_activity",
                    {
                        "player_id": player.id_,
                        "interest_paid": interest_paid,
                        "principal_paid": principal_paid,
                        "loans_issued": loans_issued,
                        "bankrupt": player.is_bankrupt,
                    },
                )

        self._evaluate_game_completion()

    def build_or_upgrade(self) -> None:  # noqa: C901, PLR0912, PLR0915
        """Advance construction projects and kick off requested builds.

        Existing projects are checked for completion, adjusting factory states
        and charging remaining costs; new build or upgrade calls are then
        initiated, including the immediate partial payments required.
        """
        if self._is_finished:
            return

        for player in self._players:
            if player.is_bankrupt:
                continue

            for factory in list(player.factories):
                if (
                    factory.next_payment_month is not None
                    and factory.next_payment_amount > 0
                    and self._state.month >= factory.next_payment_month
                ):
                    amount_due = factory.next_payment_amount
                    if player.pay(amount_due):
                        factory.next_payment_month = None
                        factory.next_payment_amount = 0.0
                        self._log_phase_event(
                            "construction_payment",
                            {
                                "player_id": player.id_,
                                "amount": amount_due,
                                "factory_type": factory.factory_type,
                            },
                        )
                    else:
                        break

                if player.is_bankrupt:
                    break

                match factory.factory_type:
                    case "builds_basic":
                        if factory.end_build_month == self._state.month:
                            factory.factory_type = "basic"
                            factory.monthly_expenses = (
                                self._state.basic_factory_monthly_expenses
                            )
                            factory.end_build_month = None
                            factory.next_payment_month = None
                            factory.next_payment_amount = 0.0
                            self._log_phase_event(
                                "construction_completed",
                                {
                                    "player_id": player.id_,
                                    "result": "basic",
                                },
                            )
                    case "builds_auto":
                        if factory.end_build_month == self._state.month:
                            factory.factory_type = "auto"
                            factory.monthly_expenses = (
                                self._state.auto_factory_monthly_expenses
                            )
                            factory.end_build_month = None
                            factory.next_payment_month = None
                            factory.next_payment_amount = 0.0
                            self._log_phase_event(
                                "construction_completed",
                                {
                                    "player_id": player.id_,
                                    "result": "auto",
                                },
                            )
                    case "upgrades":
                        if factory.end_upgrade_month == self._state.month:
                            factory.factory_type = "auto"
                            factory.monthly_expenses = (
                                self._state.auto_factory_monthly_expenses
                            )
                            factory.end_upgrade_month = None
                            self._log_phase_event(
                                "construction_completed",
                                {
                                    "player_id": player.id_,
                                    "result": "upgrade",
                                },
                            )
                    case _:
                        continue

            if player.is_bankrupt:
                continue

            call = player.build_or_upgrade_call
            player.build_or_upgrade_call = "idle"

            match call:
                case "idle":
                    continue
                case "build_basic":
                    if len(player.factories) >= self._state.max_factories:
                        continue

                    initial_payment = (
                        self._state.build_basic_cost
                        * self._state.build_basic_payment_share
                    )

                    if player.money < initial_payment:
                        continue

                    if not player.pay(initial_payment):
                        continue

                    factory = Factory(
                        factory_type="builds_basic",
                        monthly_expenses=self._state.basic_factory_monthly_expenses,
                        end_build_month=self._state.month
                        + self._state.month_for_build_basic,
                    )

                    remaining_payment = max(
                        self._state.build_basic_cost - initial_payment,
                        0.0,
                    )

                    if remaining_payment > 0:
                        due_month = max(
                            self._state.month + 1,
                            factory.end_build_month
                            - self._state.build_basic_final_payment_offset,
                        )
                        factory.next_payment_month = due_month
                        factory.next_payment_amount = remaining_payment

                    player.factories.append(factory)
                    self._log_phase_event(
                        "construction_started",
                        {
                            "player_id": player.id_,
                            "project": "build_basic",
                            "initial_payment": initial_payment,
                            "delivery_month": factory.end_build_month,
                        },
                    )
                case "build_auto":
                    if len(player.factories) >= self._state.max_factories:
                        continue

                    initial_payment = (
                        self._state.build_auto_cost
                        * self._state.build_auto_payment_share
                    )

                    if player.money < initial_payment:
                        continue

                    if not player.pay(initial_payment):
                        continue

                    factory = Factory(
                        factory_type="builds_auto",
                        monthly_expenses=self._state.auto_factory_monthly_expenses,
                        end_build_month=self._state.month
                        + self._state.month_for_build_auto,
                    )

                    remaining_payment = max(
                        self._state.build_auto_cost - initial_payment,
                        0.0,
                    )

                    if remaining_payment > 0:
                        due_month = max(
                            self._state.month + 1,
                            factory.end_build_month
                            - self._state.build_auto_final_payment_offset,
                        )
                        factory.next_payment_month = due_month
                        factory.next_payment_amount = remaining_payment

                    player.factories.append(factory)
                    self._log_phase_event(
                        "construction_started",
                        {
                            "player_id": player.id_,
                            "project": "build_auto",
                            "initial_payment": initial_payment,
                            "delivery_month": factory.end_build_month,
                        },
                    )
                case "upgrade":
                    factory = next(
                        (f for f in player.factories if f.factory_type == "basic"),
                        None,
                    )

                    if factory is None:
                        continue

                    if player.money < self._state.upgrade_cost:
                        continue

                    if not player.pay(self._state.upgrade_cost):
                        continue

                    factory.factory_type = "upgrades"
                    factory.end_upgrade_month = (
                        self._state.month + self._state.month_for_upgrade
                    )
                    self._log_phase_event(
                        "construction_started",
                        {
                            "player_id": player.id_,
                            "project": "upgrade",
                            "cost": self._state.upgrade_cost,
                            "delivery_month": factory.end_upgrade_month,
                        },
                    )
                case _:
                    continue

        self._evaluate_game_completion()

    def end_month(self) -> None:
        """Finalize month-end bookkeeping, including bankruptcy checks.

        Players who dipped below zero cash are marked bankrupt, and the
        priority order rotates so turn order reshuffles for the next month.
        """
        if self._is_finished:
            return

        for player in self._players:
            if player.money < 0:
                player.is_bankrupt = True

            player.priority -= 1

            if player.priority <= 0:
                player.priority = len(self._players)

        next_order = [
            player.id_ for player in sorted(self._players, key=lambda pl: pl.priority)
        ]
        bankrupt_ids = [player.id_ for player in self._players if player.is_bankrupt]
        self._log_phase_event(
            "month_closed",
            {
                "bankrupt_players": bankrupt_ids,
                "seniority_order": next_order,
            },
        )
        self._seniority_history.append(
            SenioritySnapshot(
                month=self._state.month + 1,
                order=next_order,
            )
        )

        self._state.month += 1
        self._evaluate_game_completion()
