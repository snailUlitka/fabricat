"""Deterministic random helpers used across the game logic."""

from __future__ import annotations

from collections.abc import Iterable, Sequence  # noqa: TC003
from random import Random
from typing import TypeVar

from fabricat_backend.shared.value_objects import SeniorityOrder

_T = TypeVar("_T")


class DeterministicRandomService:
    """Thin wrapper around :class:`random.Random` providing deterministic utilities."""

    def __init__(self, seed: int | None = None) -> None:
        self._seed = seed
        self._random = Random(seed)  # noqa: S311

    @property
    def seed(self) -> int | None:
        """Return the base seed for the service."""
        return self._seed

    def reseed(self, seed: int | None) -> None:
        """Reset the random generator to a new seed."""
        self._seed = seed
        self._random = Random(seed)  # noqa: S311

    def choice(self, population: Sequence[_T]) -> _T:
        """Return a deterministic choice from *population*."""
        if not population:
            msg = "Cannot choose from an empty population."
            raise ValueError(msg)
        return population[self._random.randrange(len(population))]

    def shuffle(self, items: Iterable[_T]) -> tuple[_T, ...]:
        """Return a shuffled tuple of *items* using the service RNG."""
        mutable = list(items)
        self._random.shuffle(mutable)
        return tuple(mutable)

    def roll_seniority(
        self, order: SeniorityOrder, seed_override: int | None = None
    ) -> SeniorityOrder:
        """Return a shuffled seniority order using deterministic randomness."""
        ranking = list(order.ranking)
        if seed_override is not None:
            local_random = Random(seed_override)  # noqa: S311
            local_random.shuffle(ranking)
        else:
            self._random.shuffle(ranking)
        return SeniorityOrder(ranking=tuple(ranking))


__all__ = ["DeterministicRandomService"]
