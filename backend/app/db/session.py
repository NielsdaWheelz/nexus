"""Database session and engine configuration.

Provides minimal SQLAlchemy engine and session maker setup for both sync and async usage.
Further service/DAO wiring will be added in later PRs.
"""

from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

# Lazy-loaded engine instances (created on first use)
_sync_engine: Optional[Engine] = None
_async_engine: Optional[AsyncEngine] = None
_sync_session_maker: Optional[sessionmaker[Session]] = None
_async_session_maker: Optional[sessionmaker[AsyncSession]] = None


def get_sync_engine() -> Engine:
    """Get or create synchronous SQLAlchemy engine.

    Returns:
        Configured SQLAlchemy engine for synchronous use.
    """
    global _sync_engine
    if _sync_engine is None:
        settings = get_settings()
        # Convert async URL to sync URL if needed
        db_url = settings.DATABASE_URL
        if db_url.startswith("postgresql+psycopg"):
            # Already a sync URL
            pass
        elif db_url.startswith("postgresql+asyncpg"):
            # Convert async to sync
            db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg")

        _sync_engine = create_engine(
            db_url,
            echo=settings.DEBUG,
            # Use NullPool for serverless/testing, QueuePool for long-running
            poolclass=None,  # Default QueuePool
        )
    return _sync_engine


def get_async_engine() -> AsyncEngine:
    """Get or create asynchronous SQLAlchemy engine.

    Returns:
        Configured async SQLAlchemy engine.
    """
    global _async_engine
    if _async_engine is None:
        settings = get_settings()
        db_url = settings.DATABASE_URL
        if not db_url.startswith("postgresql+asyncpg"):
            # Convert sync to async
            if db_url.startswith("postgresql+psycopg"):
                db_url = db_url.replace("postgresql+psycopg", "postgresql+asyncpg")
            else:
                # Assume it's a basic postgres URL
                db_url = "postgresql+asyncpg" + db_url[len("postgresql") :]

        _async_engine = create_async_engine(
            db_url,
            echo=settings.DEBUG,
            future=True,
        )
    return _async_engine


def get_sync_session_maker() -> sessionmaker[Session]:
    """Get or create synchronous session maker.

    Returns:
        Session maker for synchronous database operations.
    """
    global _sync_session_maker
    if _sync_session_maker is None:
        engine = get_sync_engine()
        _sync_session_maker = sessionmaker(
            bind=engine,
            class_=Session,
            expire_on_commit=False,
        )
    return _sync_session_maker


def get_async_session_maker() -> sessionmaker[AsyncSession]:
    """Get or create asynchronous session maker.

    Returns:
        Session maker for asynchronous database operations.
    """
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_async_engine()
        _async_session_maker = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


def get_session() -> Session:
    """Get a synchronous database session.

    Returns:
        Active database session for synchronous operations.
    """
    session_maker = get_sync_session_maker()
    return session_maker()
