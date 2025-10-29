"""Fabricat backend package wiring and entrypoints."""

from fabricat_backend.main import run_dev, run_prod
from fabricat_backend.settings import BackendSettings, get_settings, settings

main = run_dev

__all__ = [
    "BackendSettings",
    "get_settings",
    "main",
    "run_dev",
    "run_prod",
    "settings",
]
