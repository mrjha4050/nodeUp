"""Audit log repository.

Append-only — no update or delete operations.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.job_aggregator.db.repositories.base import BaseRepository
from src.job_aggregator.db.tables import AuditLogRow


class AuditRepository(BaseRepository[AuditLogRow]):
    """Database operations for the audit_logs table."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AuditLogRow)

    async def log_action(
        self,
        action: str,
        user_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict | None = None,
    ) -> AuditLogRow:
        """Create an audit log entry."""
        entry = AuditLogRow(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
        )
        return await self.create(entry)

    async def get_by_user(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLogRow]:
        """Fetch audit logs for a specific user, most recent first."""
        stmt = (
            select(AuditLogRow)
            .where(AuditLogRow.user_id == user_id)
            .order_by(AuditLogRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_action(
        self,
        action: str,
        limit: int = 50,
    ) -> list[AuditLogRow]:
        """Fetch audit logs filtered by action type."""
        stmt = (
            select(AuditLogRow)
            .where(AuditLogRow.action == action)
            .order_by(AuditLogRow.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
