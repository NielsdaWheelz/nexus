"""SQLAlchemy Base registry for all ORM models.

This is the central registry where all models must be imported for Alembic autogenerate to work.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Uses SQLAlchemy 2.0 declarative base with proper registry.
    """

    pass


# Ensure all models are imported so Alembic can discover them
# This is done in __init__.py to avoid circular imports
