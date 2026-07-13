"""Saved jobs repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.job_aggregator.db.repositories.base import BaseRepository
from src.job_aggregator.db.tables import SavedJobRow


class SavedJobsRepository(BaseRepository[SavedJobRow]):
    """Database operations for the saved_jobs table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SavedJobRow)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SavedJobRow]:
        """Fetch a user's saved jobs, most recently saved first."""
        stmt = (
            select(SavedJobRow)
            .where(SavedJobRow.user_id == user_id)
            .order_by(SavedJobRow.saved_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def is_saved(self, user_id: uuid.UUID, job_id: str) -> bool:
        """Check if a user has already saved a specific job."""
        stmt = (
            select(SavedJobRow)
            .where(SavedJobRow.user_id == user_id, SavedJobRow.job_id == job_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def remove_by_job_id(self, user_id: uuid.UUID, job_id: str) -> bool:
        """Remove a saved job by its job_id. Returns True if a row was deleted."""
        stmt = (
            select(SavedJobRow)
            .where(SavedJobRow.user_id == user_id, SavedJobRow.job_id == job_id)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True
