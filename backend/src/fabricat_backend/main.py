"""Fabricat API entrypoint."""

from __future__ import annotations

import uvicorn

from fabricat_backend.api import create_api

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000

app = create_api()


def _run_uvicorn(*, reload: bool) -> None:
    """Start uvicorn with a consistent configuration."""

    uvicorn.run(
        "fabricat_backend.main:app",
        host=DEFAULT_HOST,
        port=DEFAULT_PORT,
        reload=reload,
    )


def run_dev() -> None:
    """Run the development ASGI server with auto-reload."""

    _run_uvicorn(reload=True)


def run_prod() -> None:
    """Run the production ASGI server without auto-reload."""

    _run_uvicorn(reload=False)
