"""Declarative base for SQLAlchemy models."""

from sqlalchemy.orm import DeclarativeBase


class BaseSchema(DeclarativeBase):
    """Base class for all SQLAlchemy schemas."""

    pass
