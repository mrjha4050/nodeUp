"""SQLAlchemy 2.0 table definitions.

All tables use the Mapped[] / mapped_column() declarative style.
Domain models (Pydantic) and database models (SQLAlchemy) are kept
separate — repositories handle the conversion between them.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared base for all ORM models."""
    pass


class UserRow(Base):
    """Registered users of the job aggregator.

    Stores identity and preferences. Every search, save, and
    audit event links back to a user via foreign key.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )

    # Relationships
    search_history: Mapped[list["SearchHistoryRow"]] = relationship(back_populates="user")
    saved_jobs: Mapped[list["SavedJobRow"]] = relationship(back_populates="user")
    audit_logs: Mapped[list["AuditLogRow"]] = relationship(back_populates="user")


class SearchHistoryRow(Base):
    """Records every search a user performs.

    Captures the full query parameters and result metadata so
    searches can be replayed, analyzed, or suggested back to
    the user later.
    """

    __tablename__ = "search_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    total_results: Mapped[int] = mapped_column(default=0)
    providers_queried: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Relationships
    user: Mapped["UserRow"] = relationship(back_populates="search_history")

    __table_args__ = (
        Index("ix_search_history_user_id", "user_id"),
        Index("ix_search_history_searched_at", "searched_at"),
    )


class SavedJobRow(Base):
    """Jobs a user has bookmarked for later review.

    Stores a snapshot of the job data at save time (as JSONB)
    so the record remains useful even if the original listing
    expires or the provider goes down.
    """

    __tablename__ = "saved_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
    )
    job_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    application_url: Mapped[str] = mapped_column(Text, nullable=False)
    job_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    saved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Relationships
    user: Mapped["UserRow"] = relationship(back_populates="saved_jobs")

    __table_args__ = (
        Index("ix_saved_jobs_user_id", "user_id"),
        Index("ix_saved_jobs_user_job", "user_id", "job_id", unique=True),
    )


class AuditLogRow(Base):
    """Immutable log of significant user actions.

    Every tool invocation (search, save, delete) creates an
    audit record. Useful for debugging, compliance, and usage
    analytics. Rows are append-only — never updated or deleted.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )

    # Relationships
    user: Mapped["UserRow | None"] = relationship(back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )
