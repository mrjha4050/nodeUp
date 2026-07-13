"""Shared fixtures for all tests."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from src.job_aggregator.models.job import (
    CompanyInfo,
    ExperienceLevel,
    Job,
    JobType,
    LocationType,
    SalaryRange,
)
from src.job_aggregator.models.search import ProviderResponse, SearchRequest
from src.job_aggregator.providers.base import JobProvider
from src.job_aggregator.providers.registry import ProviderRegistry


# ------------------------------------------------------------------
# Job factory
# ------------------------------------------------------------------

def make_job(
    id: str = "test_1",
    title: str = "Software Engineer",
    company: str = "Acme Corp",
    location: str = "New York, NY",
    provider: str = "test",
    job_type: JobType = JobType.FULL_TIME,
    experience_level: ExperienceLevel = ExperienceLevel.MID,
    location_type: LocationType = LocationType.ONSITE,
    skills: list[str] | None = None,
) -> Job:
    """Create a Job with sensible defaults for testing."""
    return Job(
        id=id,
        title=title,
        description="A test job description",
        type=job_type,
        experience_level=experience_level,
        location_type=location_type,
        location=location,
        salary_range=SalaryRange(min=100000, max=150000, currency="USD", period="yearly"),
        skills=skills or ["python", "aws"],
        company_info=CompanyInfo(
            name=company,
            website="https://example.com",
            industry="Tech",
            size="51-200",
        ),
        posted_at=datetime.now(tz=timezone.utc),
        application_url="https://example.com/apply",
        raw_data={},
    )


# ------------------------------------------------------------------
# Mock provider
# ------------------------------------------------------------------

class MockProvider(JobProvider):
    """A controllable mock provider for testing."""

    def __init__(
        self,
        name: str = "mock",
        jobs: list[Job] | None = None,
        should_fail: bool = False,
        error_message: str = "Mock provider error",
    ) -> None:
        self._name = name
        self._jobs = jobs or []
        self._should_fail = should_fail
        self._error_message = error_message

    @property
    def provider_name(self) -> str:
        return self._name

    async def search_jobs(self, search_request: SearchRequest) -> ProviderResponse:
        if self._should_fail:
            raise RuntimeError(self._error_message)
        return ProviderResponse(
            provider_name=self._name,
            jobs=self._jobs,
            total_results=len(self._jobs),
            success=True,
        )

    async def get_job_details(self, job_id: str) -> Job | None:
        if self._should_fail:
            raise RuntimeError(self._error_message)
        for job in self._jobs:
            if job.id == job_id:
                return job
        return None

    async def health_check(self) -> bool:
        return not self._should_fail


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

@pytest.fixture
def search_request() -> SearchRequest:
    return SearchRequest(query="python developer")


@pytest.fixture
def sample_jobs() -> list[Job]:
    return [
        make_job(id="mock_1", title="Backend Engineer", company="Acme", location="NYC"),
        make_job(id="mock_2", title="Frontend Engineer", company="Globex", location="LA"),
        make_job(id="mock_3", title="DevOps Engineer", company="Initech", location="SF"),
    ]


@pytest.fixture
def mock_provider(sample_jobs: list[Job]) -> MockProvider:
    return MockProvider(name="mock", jobs=sample_jobs)


@pytest.fixture
def failing_provider() -> MockProvider:
    return MockProvider(name="failing", should_fail=True)


@pytest.fixture
def registry(mock_provider: MockProvider) -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register(mock_provider)
    return reg


# ------------------------------------------------------------------
# SQLite-compatible ORM models for testing
#
# The production tables use Postgres-specific types (UUID, JSONB, ARRAY).
# For tests we use a separate Base with SQLite-compatible types.
# The repositories are patched to use these test models.
# ------------------------------------------------------------------

class TestBase(DeclarativeBase):
    pass


class FakeUserRow(TestBase):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    search_history: Mapped[list["FakeSearchHistoryRow"]] = relationship(back_populates="user")
    saved_jobs: Mapped[list["FakeSavedJobRow"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["FakeAuditLogRow"]] = relationship(back_populates="user")


class FakeSearchHistoryRow(TestBase):
    __tablename__ = "search_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total_results: Mapped[int] = mapped_column(default=0)
    providers_queried: Mapped[str | None] = mapped_column(Text, nullable=True)
    searched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["FakeUserRow"] = relationship(back_populates="search_history")


class FakeSavedJobRow(TestBase):
    __tablename__ = "saved_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_url: Mapped[str] = mapped_column(Text, nullable=False)
    job_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    saved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["FakeUserRow"] = relationship(back_populates="saved_jobs")


class FakeAuditLogRow(TestBase):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["FakeUserRow | None"] = relationship(back_populates="audit_logs")


# ------------------------------------------------------------------
# Database session fixture
# ------------------------------------------------------------------

TEST_USER_ID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture
async def db_session():
    """Create an in-memory SQLite async session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async with engine.begin() as conn:
        await conn.run_sync(TestBase.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False,
    )

    async with session_factory() as session:
        user = FakeUserRow(
            id=TEST_USER_ID,
            email="test@example.com",
            name="Test User",
        )
        session.add(user)
        await session.commit()

        yield session

    await engine.dispose()


@pytest.fixture
def test_user_id() -> str:
    return TEST_USER_ID
