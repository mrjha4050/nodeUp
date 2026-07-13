"""Base repository with shared CRUD patterns.

Concrete repositories inherit from this and get standard
operations for free. They only override or add domain-specific
query methods.
"""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.job_aggregator.db.tables import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Generic async repository providing common database operations."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    async def get_by_id(self, id: uuid.UUID) -> ModelT | None:
        """Fetch a single row by primary key."""
        return await self._session.get(self._model, id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Fetch multiple rows with pagination."""
        stmt = select(self._model).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, entity: ModelT) -> ModelT:
        """Insert a new row."""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: ModelT) -> None:
        """Delete a row."""
        await self._session.delete(entity)
        await self._session.flush()
