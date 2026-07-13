"""Async database session management.

Provides a session factory and a context manager for getting
sessions. All database access goes through get_session().
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.job_aggregator.config import get_settings
from src.job_aggregator.core import get_logger
from src.job_aggregator.db.tables import Base

logger = get_logger(__name__)

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """Initialize the async engine and session factory.

    Call once at server startup. Creates tables if they don't exist
    (use Alembic for production migrations).
    """
    global _engine, _session_factory

    settings = get_settings()
    database_url = settings.database_url

    _engine = create_async_engine(
        database_url,
        echo=settings.app_env.value == "development",
        pool_size=5,
        max_overflow=10,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_initialized", url=database_url.split("@")[-1])


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session, rolling back on error."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Dispose of the engine connection pool."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_closed")
