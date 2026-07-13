"""Search history repository."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.job_aggregator.db.repositories.base import BaseRepository
from src.job_aggregator.db.tables import SearchHistoryRow


class SearchHistoryRepository(BaseRepository[SearchHistoryRow]):
    """Database operations for the search_history table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SearchHistoryRow)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> list[SearchHistoryRow]:
        """Fetch a user's search history, most recent first."""
        stmt = (
            select(SearchHistoryRow)
            .where(SearchHistoryRow.user_id == user_id)
            .order_by(SearchHistoryRow.searched_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_queries(
        self,
        user_id: uuid.UUID,
        limit: int = 5,
    ) -> list[str]:
        """Return the N most recent distinct query strings for a user."""
        stmt = (
            select(SearchHistoryRow.query)
            .where(SearchHistoryRow.user_id == user_id)
            .distinct()
            .order_by(SearchHistoryRow.searched_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
