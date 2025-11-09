"""Tests for phase timer utilities."""

import asyncio

from fabricat_backend.game_logic.phases import GamePhase, PhaseTimer


def test_phase_timer_counts_down_quickly() -> None:
    timer = PhaseTimer(default_duration_seconds=3, tick_resolution_seconds=0.0)

    async def collect() -> list[int]:
        return [
            tick.remaining_seconds
            async for tick in timer.ticks(phase=GamePhase.BUY, duration_seconds=2)
        ]

    ticks = asyncio.run(collect())
    assert ticks == [2, 1, 0]


def test_phase_timer_can_cancel_midway() -> None:
    timer = PhaseTimer(default_duration_seconds=5, tick_resolution_seconds=0.0)
    ticks: list[int] = []

    async def collect() -> None:
        async for tick in timer.ticks(phase=GamePhase.SELL, duration_seconds=5):
            ticks.append(tick.remaining_seconds)
            if tick.remaining_seconds == 3:
                timer.cancel()

    asyncio.run(collect())
    assert ticks == [5, 4, 3]
