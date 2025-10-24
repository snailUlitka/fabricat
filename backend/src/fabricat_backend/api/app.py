"""Factory for constructing the FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI

from fabricat_backend.api.routers import auth_router, session_router


def create_api() -> FastAPI:
    """Instantiate and configure the FastAPI application."""

    app = FastAPI(title="Fabricat API")
    app.include_router(auth_router)
    app.include_router(session_router)
    return app


app = create_api()
