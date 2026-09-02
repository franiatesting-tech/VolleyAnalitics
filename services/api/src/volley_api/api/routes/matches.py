"""Match + demo-processing-job endpoints. Every query is scoped to
`principal.organization_id` (from the verified JWT, see app/core/auth.py) --
never a client-supplied organization id. This is the one rule reviewed most
carefully by security-privacy-license-reviewer: a missing filter here is a
cross-tenant data leak, not a cosmetic bug.
"""

import asyncio

import structlog
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from volley_domain.models import JobStatus, Match, MatchStatus, ProcessingJob
from volley_domain.schemas import MatchCreate, MatchOut, ProcessingJobOut, SyntheticMatch

from volley_api.core.auth import Principal, get_current_principal, require_org_roles
from volley_api.core.db import get_db
from volley_api.core.tasks import PROCESS_DEMO_MATCH_TASK_NAME, enqueue_process_demo_match

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["matches"])


def _dedup_key(match_id: str) -> str:
    return f"{match_id}:{PROCESS_DEMO_MATCH_TASK_NAME}:v1"


@router.get("/matches", response_model=list[MatchOut])
async def list_matches(
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[Match]:
    result = await db.execute(
        select(Match)
        .where(Match.organization_id == principal.organization_id)
        .order_by(Match.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/matches", response_model=MatchOut, status_code=status.HTTP_201_CREATED)
async def create_match(
    body: MatchCreate,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Match:
    match = Match(
        organization_id=principal.organization_id,
        home_team=body.home_team,
        away_team=body.away_team,
        scheduled_at=body.scheduled_at,
        status=MatchStatus.DRAFT,
        created_by_user_id=principal.user_id,
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match


async def _get_org_scoped_match(match_id: str, principal: Principal, db: AsyncSession) -> Match:
    result = await db.execute(
        select(Match).where(
            Match.id == match_id, Match.organization_id == principal.organization_id
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Match not found")
    return match


@router.get("/matches/{match_id}", response_model=MatchOut)
async def get_match(
    match_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> Match:
    return await _get_org_scoped_match(match_id, principal, db)


@router.delete("/matches/{match_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_match(
    match_id: str,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Permanently deletes a match. Every `MatchSet`/`Rally`/.../`Outcome`
    row and `ProcessingJob` row cascades at the DB level (all already
    `ondelete="CASCADE"` from `matches.id`). Any `Video` linked to this
    match only has that link cleared (`ondelete="SET NULL"` on
    `Video.match_id`) -- deleting a match never deletes the video footage
    itself; use `DELETE /videos/{id}` separately for that.
    """
    match = await _get_org_scoped_match(match_id, principal, db)
    await db.delete(match)
    await db.commit()
    logger.info("match_deleted", match_id=match_id, organization_id=principal.organization_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/matches/{match_id}/demo-process", response_model=ProcessingJobOut)
async def trigger_demo_process(
    match_id: str,
    principal: Principal = Depends(require_org_roles("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    match = await _get_org_scoped_match(match_id, principal, db)
    dedup_key = _dedup_key(match_id)

    existing = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.dedup_key == dedup_key,
            ProcessingJob.organization_id == principal.organization_id,
        )
    )
    job = existing.scalar_one_or_none()

    # A QUEUED row with no celery_task_id means a previous enqueue attempt
    # never actually reached the broker (e.g. Valkey was down) -- that's not
    # "in flight," it's a dead row, and must not permanently block retries.
    dispatched = job is not None and (
        job.status != JobStatus.QUEUED or job.celery_task_id is not None
    )

    if (
        job is not None
        and dispatched
        and job.status
        in (
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.COMPLETED,
        )
    ):
        # Idempotent: already in flight or already done -- never double-enqueue.
        logger.info(
            "demo_process_reused_existing_job", match_id=match_id, job_id=job.id, status=job.status
        )
        return job

    if job is None:
        job = ProcessingJob(
            match_id=match_id,
            organization_id=principal.organization_id,
            task_name=PROCESS_DEMO_MATCH_TASK_NAME,
            dedup_key=dedup_key,
            status=JobStatus.QUEUED,
            progress=0,
        )
        db.add(job)
    else:
        # Previous attempt failed, or never actually dispatched -- retry as
        # a fresh run of the same job row.
        job.status = JobStatus.QUEUED
        job.progress = 0
        job.error = None
        job.attempt += 1

    match.status = MatchStatus.PROCESSING
    await db.commit()
    await db.refresh(job)

    # enqueue_process_demo_match is sync (Celery's client is sync); running
    # it inline would block the event loop for every other in-flight request.
    celery_task_id = await asyncio.to_thread(
        enqueue_process_demo_match, match_id=match_id, dedup_key=dedup_key
    )
    job.celery_task_id = celery_task_id
    await db.commit()
    await db.refresh(job)

    logger.info(
        "demo_process_enqueued", match_id=match_id, job_id=job.id, celery_task_id=celery_task_id
    )
    return job


@router.get("/jobs/{job_id}", response_model=ProcessingJobOut)
async def get_job(
    job_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> ProcessingJob:
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id, ProcessingJob.organization_id == principal.organization_id
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("/matches/{match_id}/result", response_model=SyntheticMatch)
async def get_match_result(
    match_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await _get_org_scoped_match(match_id, principal, db)
    dedup_key = _dedup_key(match_id)
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.dedup_key == dedup_key,
            ProcessingJob.organization_id == principal.organization_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None or job.status != JobStatus.COMPLETED or job.result_data is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No completed result available for this match yet",
        )
    return job.result_data
