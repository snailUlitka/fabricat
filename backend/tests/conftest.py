"""Test configuration and fixtures for the backend test suite."""

from __future__ import annotations

import pytest

from fabricat_backend.settings import get_settings


@pytest.fixture(autouse=True)
def _mock_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure settings are loaded with predictable values during tests."""
    monkeypatch.setenv("AUTH_SECRET_KEY", "test-secret-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
