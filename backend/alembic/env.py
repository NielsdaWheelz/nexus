import os
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection

from alembic import context

# Add the app directory to path so we can import models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the Base and models for autogenerate to work
# Import all models so they are registered with Base.metadata
from app.db import (  # noqa: F401
    Annotation,
    ContentChunk,
    Conversation,
    Document,
    Highlight,
    Library,
    LibraryMedia,
    LibraryMembership,
    Link,
    Message,
    MetadataChunk,
    ObjectLibraryVisibility,
    Reader,
    ThoughtChunk,
    User,
)
from app.db.base import Base

# target_metadata is used for autogenerate support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    from app.core.config import get_settings

    settings = get_settings()
    # Convert async URL to sync for migrations if needed
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg"):
        url = url.replace("postgresql+asyncpg", "postgresql+psycopg")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (sync).

    Uses synchronous SQLAlchemy engine for migrations.

    Database selection priority (for running migrations):
    1. DATABASE_URL environment variable (explicit override, highest priority)
    2. DATABASE_URL_TEST environment variable (test environment)
    3. settings.DATABASE_URL (dev/prod default)

    For autogenerate (alembic revision), always uses dev DATABASE_URL to compare schema.
    """
    import os
    import sys

    from sqlalchemy import create_engine

    from app.core.config import get_settings

    settings = get_settings()

    # Detect if we're in autogenerate mode by checking command line args
    # alembic revision is for creating migrations, alembic upgrade is for running them
    is_autogenerate = "revision" in sys.argv

    if is_autogenerate:
        # For autogenerate, always use dev database to compare current schema
        db_url = settings.DATABASE_URL
    else:
        # For running migrations, check environment variables first, then fall back to config
        # This allows both DATABASE_URL and DATABASE_URL_TEST to override settings
        db_url = (
            os.environ.get("DATABASE_URL")
            or os.environ.get("DATABASE_URL_TEST")
            or settings.DATABASE_URL
        )

    # Convert async URL to sync for migrations
    if db_url.startswith("postgresql+asyncpg"):
        db_url = db_url.replace("postgresql+asyncpg", "postgresql+psycopg")

    engine = create_engine(db_url, poolclass=pool.NullPool)

    with engine.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
