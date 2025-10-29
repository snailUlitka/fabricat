"""Fabricat API entrypoint."""

from __future__ import annotations

import uvicorn

from fabricat_backend.api import create_api
from fabricat_backend.settings import get_settings

app = create_api()


def _run_uvicorn(*, reload: bool) -> None:
    """Start uvicorn with a consistent configuration."""
    config = get_settings()
    uvicorn.run(
        "fabricat_backend.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=reload,
    )


def run_dev() -> None:
    """Run the development ASGI server with auto-reload."""
    _run_uvicorn(reload=True)


def run_prod() -> None:
    """Run the production ASGI server without auto-reload."""
    _run_uvicorn(reload=False)
