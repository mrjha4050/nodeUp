"""User repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.job_aggregator.db.repositories.base import BaseRepository
from src.job_aggregator.db.tables import UserRow


class UserRepository(BaseRepository[UserRow]):
    """Database operations for the users table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserRow)

    async def get_by_email(self, email: str) -> UserRow | None:
        """Look up a user by their email address."""
        stmt = select(UserRow).where(UserRow.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
