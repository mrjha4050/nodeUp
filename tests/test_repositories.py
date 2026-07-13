"""Tests for database repositories using in-memory SQLite.

Uses SQLite-compatible test ORM models from conftest.py.
The repository base class is generic, so we instantiate it
with the test models directly.
"""

import uuid

import pytest

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.job_aggregator.db.repositories.base import BaseRepository

from tests.conftest import (
    TEST_USER_ID,
    FakeAuditLogRow,
    FakeSavedJobRow,
    FakeSearchHistoryRow,
    FakeUserRow,
)


# ------------------------------------------------------------------
# UserRepository (via BaseRepository)
# ------------------------------------------------------------------

class TestUserRepository:

    @pytest.mark.asyncio
    async def test_get_by_id(self, db_session: AsyncSession, test_user_id) -> None:
        repo = BaseRepository(db_session, FakeUserRow)
        user = await repo.get_by_id(test_user_id)
        assert user is not None
        assert user.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_by_email(self, db_session: AsyncSession) -> None:
        stmt = select(FakeUserRow).where(FakeUserRow.email == "test@example.com")
        result = await db_session.execute(stmt)
        user = result.scalar_one_or_none()
        assert user is not None
        assert user.name == "Test User"

    @pytest.mark.asyncio
    async def test_get_by_email_not_found(self, db_session: AsyncSession) -> None:
        stmt = select(FakeUserRow).where(FakeUserRow.email == "nobody@example.com")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_create_user(self, db_session: AsyncSession) -> None:
        repo = BaseRepository(db_session, FakeUserRow)
        new_user = FakeUserRow(email="new@example.com", name="New User")
        created = await repo.create(new_user)
        assert created.id is not None
        assert created.email == "new@example.com"

    @pytest.mark.asyncio
    async def test_get_all(self, db_session: AsyncSession) -> None:
        repo = BaseRepository(db_session, FakeUserRow)
        users = await repo.get_all()
        assert len(users) >= 1

    @pytest.mark.asyncio
    async def test_delete_user(self, db_session: AsyncSession) -> None:
        repo = BaseRepository(db_session, FakeUserRow)
        user = FakeUserRow(email="delete@example.com", name="Delete Me")
        await repo.create(user)

        await repo.delete(user)
        await db_session.flush()

        stmt = select(FakeUserRow).where(FakeUserRow.email == "delete@example.com")
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None


# ------------------------------------------------------------------
# SearchHistory
# ------------------------------------------------------------------

class TestSearchHistoryRepository:

    @pytest.mark.asyncio
    async def test_create_and_query(self, db_session: AsyncSession, test_user_id) -> None:
        repo = BaseRepository(db_session, FakeSearchHistoryRow)
        entry = FakeSearchHistoryRow(
            user_id=test_user_id,
            query="python developer",
            location="NYC",
            total_results=42,
        )
        await repo.create(entry)
        await db_session.flush()

        stmt = select(FakeSearchHistoryRow).where(
            FakeSearchHistoryRow.user_id == test_user_id,
        )
        result = await db_session.execute(stmt)
        rows = list(result.scalars().all())
        assert len(rows) >= 1
        assert rows[0].query == "python developer"

    @pytest.mark.asyncio
    async def test_multiple_entries(self, db_session: AsyncSession, test_user_id) -> None:
        repo = BaseRepository(db_session, FakeSearchHistoryRow)
        for q in ["python", "java", "rust"]:
            await repo.create(FakeSearchHistoryRow(
                user_id=test_user_id,
                query=q,
                total_results=10,
            ))
        await db_session.flush()

        all_entries = await repo.get_all()
        assert len(all_entries) >= 3

    @pytest.mark.asyncio
    async def test_empty_for_unknown_user(self, db_session: AsyncSession) -> None:
        stmt = select(FakeSearchHistoryRow).where(
            FakeSearchHistoryRow.user_id == str(uuid.uuid4()),
        )
        result = await db_session.execute(stmt)
        assert list(result.scalars().all()) == []


# ------------------------------------------------------------------
# SavedJobs
# ------------------------------------------------------------------

class TestSavedJobsRepository:

    async def _save_job(
        self,
        session: AsyncSession,
        user_id: str,
        job_id: str = "linkedin_1",
    ) -> FakeSavedJobRow:
        row = FakeSavedJobRow(
            user_id=user_id,
            job_id=job_id,
            provider="linkedin",
            title="Engineer",
            company="Acme",
            location="NYC",
            application_url="https://example.com/apply",
            job_snapshot={"title": "Engineer"},
        )
        session.add(row)
        await session.flush()
        return row

    @pytest.mark.asyncio
    async def test_save_and_query(self, db_session: AsyncSession, test_user_id) -> None:
        await self._save_job(db_session, test_user_id)

        stmt = select(FakeSavedJobRow).where(FakeSavedJobRow.user_id == test_user_id)
        result = await db_session.execute(stmt)
        rows = list(result.scalars().all())
        assert len(rows) >= 1
        assert rows[0].job_id == "linkedin_1"

    @pytest.mark.asyncio
    async def test_is_saved(self, db_session: AsyncSession, test_user_id) -> None:
        await self._save_job(db_session, test_user_id, job_id="check_1")

        stmt = select(FakeSavedJobRow).where(
            FakeSavedJobRow.user_id == test_user_id,
            FakeSavedJobRow.job_id == "check_1",
        )
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_not_saved(self, db_session: AsyncSession, test_user_id) -> None:
        stmt = select(FakeSavedJobRow).where(
            FakeSavedJobRow.user_id == test_user_id,
            FakeSavedJobRow.job_id == "nonexistent",
        )
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_remove(self, db_session: AsyncSession, test_user_id) -> None:
        row = await self._save_job(db_session, test_user_id, job_id="remove_me")
        await db_session.delete(row)
        await db_session.flush()

        stmt = select(FakeSavedJobRow).where(
            FakeSavedJobRow.user_id == test_user_id,
            FakeSavedJobRow.job_id == "remove_me",
        )
        result = await db_session.execute(stmt)
        assert result.scalar_one_or_none() is None


# ------------------------------------------------------------------
# AuditLogs
# ------------------------------------------------------------------

class TestAuditRepository:

    @pytest.mark.asyncio
    async def test_log_action(self, db_session: AsyncSession, test_user_id) -> None:
        repo = BaseRepository(db_session, FakeAuditLogRow)
        entry = FakeAuditLogRow(
            action="search_jobs",
            user_id=test_user_id,
            resource_type="search",
            details={"query": "python"},
        )
        created = await repo.create(entry)
        assert created.id is not None
        assert created.action == "search_jobs"

    @pytest.mark.asyncio
    async def test_log_without_user(self, db_session: AsyncSession) -> None:
        repo = BaseRepository(db_session, FakeAuditLogRow)
        entry = FakeAuditLogRow(action="system_startup")
        created = await repo.create(entry)
        assert created.user_id is None

    @pytest.mark.asyncio
    async def test_query_by_user(self, db_session: AsyncSession, test_user_id) -> None:
        repo = BaseRepository(db_session, FakeAuditLogRow)
        await repo.create(FakeAuditLogRow(action="a1", user_id=test_user_id))
        await repo.create(FakeAuditLogRow(action="a2", user_id=test_user_id))
        await db_session.flush()

        stmt = select(FakeAuditLogRow).where(FakeAuditLogRow.user_id == test_user_id)
        result = await db_session.execute(stmt)
        rows = list(result.scalars().all())
        assert len(rows) >= 2

    @pytest.mark.asyncio
    async def test_query_by_action(self, db_session: AsyncSession, test_user_id) -> None:
        repo = BaseRepository(db_session, FakeAuditLogRow)
        await repo.create(FakeAuditLogRow(action="unique_action", user_id=test_user_id))
        await db_session.flush()

        stmt = select(FakeAuditLogRow).where(FakeAuditLogRow.action == "unique_action")
        result = await db_session.execute(stmt)
        rows = list(result.scalars().all())
        assert len(rows) >= 1
        assert all(r.action == "unique_action" for r in rows)
