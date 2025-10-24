"""Shared enumerations used across the backend."""

from enum import StrEnum


class AvatarIcon(StrEnum):
    """Predefined avatar identifiers available to players."""

    ASTRONAUT = "astronaut"
    BOTANIST = "botanist"
    CAPTAIN = "captain"
    DIVER = "diver"
    ENGINEER = "engineer"
    GEOLOGIST = "geologist"
    HACKER = "hacker"
    INVENTOR = "inventor"
    PILOT = "pilot"
    SCIENTIST = "scientist"
