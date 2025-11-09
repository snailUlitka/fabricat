"""Factory for constructing the FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fabricat_backend.api.routers import auth_router, session_router


def create_api() -> FastAPI:
    """Instantiate and configure the FastAPI application."""
    app = FastAPI(title="Fabricat API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(session_router)
    return app


app = create_api()
