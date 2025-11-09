"""Tests for the game session core logic."""

from collections.abc import Iterable
from random import Random

import pytest

from fabricat_backend.game_logic.phases import GamePhase
from fabricat_backend.game_logic.session import (
    Bid,
    Factory,
    FinishedGood,
    GameSession,
    GameSettings,
    Loan,
    Player,
    RawMaterial,
)


def make_settings(**overrides: object) -> GameSettings:
    """Build a GameSettings instance with sensible defaults for tests."""

    base: dict[str, object] = {
        "start_factory_count": 0,
        "max_months": 12,
        "basic_factory_monthly_expenses": 1_000.0,
        "auto_factory_monthly_expenses": 1_500.0,
        "raw_material_monthly_expenses": 300.0,
        "finished_good_monthly_expenses": 500.0,
        "basic_factory_launch_cost": 2_000.0,
        "auto_factory_launch_cost": 3_000.0,
        "bank_start_money": 100_000.0,
        "loans_monthly_expenses_in_percents": 0.01,
        "available_loans": [5_000.0, 10_000.0],
        "loan_terms_in_months": [2, 3],
        "bank_raw_material_sell_volume_range": (5, 5),
        "bank_finished_good_buy_volume_range": (5, 5),
        "bank_raw_material_sell_min_price_range": (200.0, 200.0),
        "bank_finished_good_buy_max_price_range": (500.0, 500.0),
        "month_for_upgrade": 2,
        "upgrade_cost": 7_000.0,
        "month_for_build_basic": 2,
        "build_basic_cost": 5_000.0,
        "month_for_build_auto": 3,
        "build_auto_cost": 10_000.0,
        "build_basic_payment_share": 0.5,
        "build_basic_final_payment_offset": 1,
        "build_auto_payment_share": 0.5,
        "build_auto_final_payment_offset": 1,
        "max_raw_material_storage": 10,
        "max_finished_good_storage": 10,
        "max_factories": 6,
    }

    base.update(overrides)
    return GameSettings(**base)


def make_player(
    *,
    player_id: int,
    money: float = 10_000.0,
    priority: int = 1,
) -> Player:
    """Factory for Player objects with default optional fields."""
    return Player(id_=player_id, money=money, priority=priority)


def add_raw_materials(player: Player, count: int) -> None:
    player.raw_materials.extend(
        RawMaterial(monthly_expenses=300.0) for _ in range(count)
    )


def add_finished_goods(player: Player, count: int) -> None:
    player.finished_goods.extend(
        FinishedGood(monthly_expenses=500.0) for _ in range(count)
    )


def add_factories(player: Player, types: Iterable[str]) -> None:
    for factory_type in types:
        monthly = 1_500.0 if factory_type in {"auto", "builds_auto"} else 1_000.0
        player.factories.append(
            Factory(factory_type=factory_type, monthly_expenses=monthly)
        )


def test_buy_bids_sorted_by_price_then_priority_and_respect_limits() -> None:
    players = [
        make_player(player_id=1, money=1_000.0, priority=2),
        make_player(player_id=2, money=1_000.0, priority=1),
        make_player(player_id=3, money=1_000.0, priority=3),
    ]
    settings = make_settings()
    session = GameSession(
        players=players,
        settings=settings,
        seed_seniority=False,
    )
    session.set_market()

    players[0].buy_bid = Bid(quantity=2, price=250.0)
    players[1].buy_bid = Bid(quantity=2, price=250.0)
    players[2].buy_bid = Bid(quantity=2, price=150.0)  # below monthly minimum

    session.process_buy_bids()

    assert len(players[1].raw_materials) == 2  # higher priority wins tie
    assert players[1].money == pytest.approx(500.0)

    assert len(players[0].raw_materials) == 2  # remaining volume filled at same price
    assert players[0].money == pytest.approx(500.0)

    assert len(players[2].raw_materials) == 0  # price below corridor ignored
    assert players[2].money == pytest.approx(1_000.0)


def test_start_production_respects_costs_and_upgrade_factories() -> None:
    player = make_player(player_id=1, money=20_000.0, priority=1)
    add_factories(player, ["basic", "upgrades", "auto"])
    add_raw_materials(player, 5)
    player.production_call_for_basic = 3
    player.production_call_for_auto = 3

    session = GameSession(
        players=[player],
        settings=make_settings(),
        seed_seniority=False,
    )
    session.start_production()

    assert len(player.raw_materials) == 1
    assert len(player.finished_goods) == 4
    assert player.money == pytest.approx(13_000.0)  # 2*2k + 1*3k costs
    assert player.production_call_for_basic == 1
    assert player.production_call_for_auto == 1


def test_process_loans_issues_interest_and_repayment() -> None:
    player = make_player(player_id=1, money=5_000.0, priority=1)
    player.loans[0].loan_status = "call"
    session = GameSession(
        players=[player],
        settings=make_settings(),
        seed_seniority=False,
    )

    session.process_loans()

    loan = player.loans[0]
    assert loan.loan_status == "in_progress"
    assert loan.amount == pytest.approx(5_000.0)
    assert loan.return_month == session._state.month + 2
    assert player.money == pytest.approx(10_000.0)
    bank_money_after_issue = session._bank.money

    session._state.month = 2
    session.process_loans()

    assert player.money == pytest.approx(9_950.0)
    assert session._bank.money == pytest.approx(bank_money_after_issue + 50.0)

    session._state.month = loan.return_month
    player.money += 5_000.0  # simulate income to cover repayment
    session.process_loans()

    assert loan.loan_status == "idle"
    assert loan.amount == pytest.approx(0.0)
    assert session._bank.available_loans[0] == session._bank.loan_nominals[0]


def test_build_basic_factory_tracks_second_payment_and_limit() -> None:
    settings = make_settings(max_factories=1, month_for_build_basic=2)
    player = make_player(player_id=1, money=10_000.0, priority=1)
    player.build_or_upgrade_call = "build_basic"
    session = GameSession(
        players=[player],
        settings=settings,
        seed_seniority=False,
    )

    session.build_or_upgrade()

    assert len(player.factories) == 1
    factory = player.factories[0]
    assert factory.factory_type == "builds_basic"
    assert player.money == pytest.approx(7_500.0)
    assert factory.next_payment_month == session._state.month + 1
    assert factory.next_payment_amount == pytest.approx(2_500.0)

    player.build_or_upgrade_call = "build_basic"
    session.build_or_upgrade()
    assert len(player.factories) == 1  # limit enforced

    session._state.month = factory.next_payment_month
    session.build_or_upgrade()
    assert player.money == pytest.approx(5_000.0)
    assert factory.next_payment_amount == 0.0

    session._state.month = factory.end_build_month
    session.build_or_upgrade()
    assert factory.factory_type == "basic"
    assert factory.end_build_month is None


def test_game_finishes_by_month_limit_and_selects_highest_capital() -> None:
    settings = make_settings(max_months=1)
    p1 = make_player(player_id=1, money=5_000.0, priority=1)
    p2 = make_player(player_id=2, money=8_000.0, priority=2)
    add_factories(p1, ["basic"])
    add_raw_materials(p1, 1)
    add_finished_goods(p1, 1)

    add_factories(p2, ["auto"])
    p2.loans[0] = Loan(amount=4_000.0, loan_status="in_progress", return_month=5)

    session = GameSession(
        players=[p1, p2],
        settings=settings,
        seed_seniority=False,
    )
    session._bank.raw_material_sell_min_price = 200.0
    session._bank.finished_good_buy_max_price = 500.0

    session.end_month()

    assert session.is_finished
    assert session.winner is p2


def test_game_finishes_when_only_one_player_survives() -> None:
    settings = make_settings(max_months=5)
    survivor = make_player(player_id=1, money=5_000.0, priority=1)
    bankrupt = make_player(player_id=2, money=500.0, priority=2)
    bankrupt.factories.append(Factory(factory_type="basic", monthly_expenses=1_000.0))

    session = GameSession(
        players=[survivor, bankrupt],
        settings=settings,
        seed_seniority=False,
    )
    session.collect_expenses()

    assert session.is_finished
    assert session.winner is survivor


def test_run_phase_returns_report_with_journal_entries() -> None:
    player = make_player(player_id=1, money=5_000.0, priority=1)
    session = GameSession(
        players=[player],
        settings=make_settings(),
        seed_seniority=False,
    )

    report = session.run_phase(GamePhase.MARKET)

    assert report.phase is GamePhase.MARKET
    assert report.journal
    assert report.analytics.players[0].player_id == player.id_


def test_seniority_history_tracks_rotations() -> None:
    players = [
        make_player(player_id=1, money=5_000.0, priority=1),
        make_player(player_id=2, money=5_000.0, priority=2),
    ]
    session = GameSession(
        players=players,
        settings=make_settings(),
        rng=Random(7),  # noqa: S311
    )

    assert session.seniority_history[0].month == 1
    assert len(session.tie_break_log) >= len(players)

    session.run_phase(GamePhase.END_MONTH)

    assert session.seniority_history[-1].month == 2
