"""Base declarativa compartida por todos los modelos SQLAlchemy 2.x."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Raíz de metadatos de los modelos ORM del producto."""
