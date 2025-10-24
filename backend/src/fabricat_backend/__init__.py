"""Fabricat backend package wiring and entrypoints."""

from fabricat_backend.main import run_dev, run_prod

main = run_dev

__all__ = ["main", "run_dev", "run_prod"]
