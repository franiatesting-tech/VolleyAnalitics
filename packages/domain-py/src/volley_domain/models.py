"""SQLAlchemy 2 models owned by Alembic (services/api/migrations).

These are Phase-1 skeleton tables only: enough to list matches, trigger the
demo processing job, and track its progress/result. The full volleyball
ontology (Organization/Competition/Team/Player/Roster/Match/Set/Rally/...)
lands in Phase 2 per ROADMAP.md -- do not expand this file ahead of that.

`organization_id` is a plain indexed string, deliberately with NO foreign key
to Better Auth's `organization` table: Better Auth owns that table and this
package's migrations must never reach into it (see CLAUDE.md's auth
ownership rule). The value is trusted only because it comes from a
server-verified JWT claim, never from client input -- see
services/api/src/volley_api/core/auth.py.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from volley_domain.base import Base, new_id, utcnow

_uuid_str = new_id
_utcnow = utcnow


class MatchStatus(enum.StrEnum):
    DRAFT = "draft"
    DEMO_READY = "demo_ready"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Match(Base):
    """Phase 1 table, extended in Phase 2 (docs/domain/ONTOLOGY.md) with
    optional links into the real ontology. `home_team`/`away_team` free-text
    columns are kept as a display fallback: a coach uploading a video
    shouldn't be blocked on first creating formal Team/Competition/Season
    records, so the *_id columns below are nullable, not a replacement."""

    __tablename__ = "matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    home_team: Mapped[str] = mapped_column(String(255), nullable=False)
    away_team: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus, native_enum=False, length=32), default=MatchStatus.DRAFT, nullable=False
    )
    created_by_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    competition_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("competitions.id", ondelete="SET NULL"), nullable=True
    )
    season_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True
    )
    home_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    away_team_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    venue: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow, onupdate=_utcnow
    )


class ProcessingJob(Base):
    """Durable job-progress record. Postgres is the source of truth for job
    state (per ADR-001 -- Valkey/Celery's own result backend is disposable
    cache, never authoritative). `dedup_key` enforces "no duplicate results":
    re-triggering demo processing for the same match reuses the existing
    completed job instead of creating a second one.
    """

    __tablename__ = "processing_jobs"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_processing_jobs_dedup_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    match_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("matches.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organization_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # Set once a real PipelineRun exists for this job (see ontology.py) --
    # nullable because the Phase 1 synthetic demo path predates real
    # pipeline runs; the Phase 2 synthetic generator populates it.
    pipeline_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True
    )
    task_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, native_enum=False, length=32), default=JobStatus.QUEUED, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow, onupdate=_utcnow
    )
