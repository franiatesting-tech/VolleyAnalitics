"""Read endpoints for the real volleyball ontology (docs/domain/ONTOLOGY.md)
-- sets, rallies, actions, and computed statistics. Distinct from
matches.py's Phase 1 demo-flow endpoints (GET /matches/{id}/result, which
still reads the JSON blob -- see ADR-004 for why both coexist for now).

Org-scoping: MatchSet/Rally/Action carry no organization_id column of their
own (see ONTOLOGY.md) -- every query here resolves scope by joining back to
Match.organization_id, exactly once, near the top of each route. This is
the same rule matches.py's module docstring states; repeated here because
it's the single most security-critical property of every route in this file.
"""

from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from volley_domain.court import Zone
from volley_domain.models import Match
from volley_domain.ontology import (
    Action,
    Outcome,
    PipelineRun,
    PipelineRunStatus,
    Rally,
    RallyAnalysisResult,
)
from volley_domain.ontology import MatchSet as MatchSetRow
from volley_domain.schemas import (
    ActionOut,
    AttackStatsOut,
    BlockStatsOut,
    DigStatsOut,
    MatchSetOut,
    MatchStatisticsOut,
    RallyAnalysisResultOut,
    RallyDurationStatsOut,
    RallyOut,
    ReceptionStatsOut,
    ServeStatsOut,
    SetterDistributionEntryOut,
    SideoutBreakpointStatsOut,
    StatCategory,
    StatEvidenceEventOut,
    StatEvidenceOut,
)
from volley_domain.stats.engine import FORMULA_VERSION, compute_match_statistics
from volley_domain.stats.evidence import matches_stat_category
from volley_domain.stats.records import ActionRecord
from volley_domain.stats.records import RallyRecord as StatsRallyRecord

from volley_api.core.auth import Principal, get_current_principal
from volley_api.core.db import get_db

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["ontology"])


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


@router.get("/matches/{match_id}/sets", response_model=list[MatchSetOut])
async def list_sets(
    match_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[MatchSetRow]:
    await _get_org_scoped_match(match_id, principal, db)
    result = await db.execute(
        select(MatchSetRow).where(MatchSetRow.match_id == match_id).order_by(MatchSetRow.index)
    )
    return list(result.scalars().all())


@router.get("/matches/{match_id}/rallies", response_model=list[RallyOut])
async def list_rallies(
    match_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[Rally]:
    await _get_org_scoped_match(match_id, principal, db)
    result = await db.execute(
        select(Rally)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .where(MatchSetRow.match_id == match_id)
        .order_by(MatchSetRow.index, Rally.index_in_set)
    )
    return list(result.scalars().all())


async def _get_org_scoped_rally(rally_id: str, principal: Principal, db: AsyncSession) -> Rally:
    result = await db.execute(
        select(Rally)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .join(Match, MatchSetRow.match_id == Match.id)
        .where(Rally.id == rally_id, Match.organization_id == principal.organization_id)
    )
    rally = result.scalar_one_or_none()
    if rally is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rally not found")
    return rally


@router.get("/rallies/{rally_id}/actions", response_model=list[ActionOut])
async def list_rally_actions(
    rally_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> list[Action]:
    await _get_org_scoped_rally(rally_id, principal, db)
    result = await db.execute(
        select(Action)
        .where(Action.rally_id == rally_id)
        .order_by(Action.video_t_start)
        .options(selectinload(Action.outcome))
    )
    return list(result.scalars().all())


@router.get("/rallies/{rally_id}/analysis", response_model=RallyAnalysisResultOut)
async def get_rally_analysis(
    rally_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> RallyAnalysisResult:
    """Return the newest completed, internally consistent analysis bundle.

    The result row carries ``organization_id`` specifically so the tenant
    boundary is enforced directly in the query. Joining the PipelineRun and
    requiring COMPLETED prevents partially published worker output from
    becoming visible in replay clients.
    """

    await _get_org_scoped_rally(rally_id, principal, db)
    result = await db.execute(
        select(RallyAnalysisResult)
        .join(PipelineRun, RallyAnalysisResult.pipeline_run_id == PipelineRun.id)
        .where(
            RallyAnalysisResult.rally_id == rally_id,
            RallyAnalysisResult.organization_id == principal.organization_id,
            PipelineRun.status == PipelineRunStatus.COMPLETED,
        )
        .order_by(RallyAnalysisResult.created_at.desc(), RallyAnalysisResult.id.desc())
        .limit(1)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed professional analysis is available for this rally",
        )
    return analysis


@router.get("/matches/{match_id}/statistics", response_model=MatchStatisticsOut)
async def get_match_statistics(
    match_id: str,
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> MatchStatisticsOut:
    """Computes statistics fresh from the Event Log every call -- per
    ONTOLOGY.md, DerivedMetric is never persisted as a mutable number."""
    await _get_org_scoped_match(match_id, principal, db)

    rallies_result = await db.execute(
        select(Rally)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .where(MatchSetRow.match_id == match_id)
    )
    rally_rows = list(rallies_result.scalars().all())
    rally_records = [
        StatsRallyRecord(
            id=r.id,
            serving_team_id=r.serving_team_id,
            point_winner_team_id=r.point_winner_team_id,
            duration_seconds=r.duration_seconds,
        )
        for r in rally_rows
    ]

    rally_ids = [r.id for r in rally_rows]
    if not rally_ids:
        stats = compute_match_statistics([], [])
    else:
        actions_result = await db.execute(
            select(Action, Outcome)
            .outerjoin(Outcome, Outcome.action_id == Action.id)
            .where(Action.rally_id.in_(rally_ids))
            .order_by(Action.video_t_start)
        )
        action_records = []
        for phase_seq, (action, outcome) in enumerate(actions_result.all()):
            action_records.append(
                ActionRecord(
                    id=action.id,
                    rally_id=action.rally_id,
                    sequence=phase_seq,
                    action_type=action.action_type,
                    actor_team_id=action.actor_team_id,
                    actor_roster_id=action.actor_roster_id,
                    outcome=outcome.result if outcome else None,
                    court_x=action.court_x,
                    court_y=action.court_y,
                    quality_rating=action.quality_rating,
                    outcome_detail=outcome.detail if outcome else None,
                )
            )
        stats = compute_match_statistics(rally_records, action_records)

    return MatchStatisticsOut(
        formula_version=stats.formula_version,
        serve={k: ServeStatsOut(**vars(v)) for k, v in stats.serve.items()},
        reception={k: ReceptionStatsOut(**vars(v)) for k, v in stats.reception.items()},
        attack={k: AttackStatsOut(**vars(v)) for k, v in stats.attack.items()},
        block={k: BlockStatsOut(**vars(v)) for k, v in stats.block.items()},
        dig={k: DigStatsOut(**vars(v)) for k, v in stats.dig.items()},
        sideout_breakpoint={
            k: SideoutBreakpointStatsOut(**vars(v)) for k, v in stats.sideout_breakpoint.items()
        },
        setter_distribution={
            k: SetterDistributionEntryOut(**vars(v)) for k, v in stats.setter_distribution.items()
        },
        rally_duration=RallyDurationStatsOut(**vars(stats.rally_duration)),
    )


@router.get("/matches/{match_id}/statistics/evidence", response_model=StatEvidenceOut)
async def get_stat_evidence(
    match_id: str,
    category: StatCategory,
    team_id: str,
    zone: int | None = Query(default=None, ge=1, le=6),
    limit: int = Query(default=200, ge=1, le=500),
    principal: Principal = Depends(get_current_principal),
    db: AsyncSession = Depends(get_db),
) -> StatEvidenceOut:
    """Return the exact Event Log rows behind one displayed statistic.

    This replaces the browser's former one-request-per-rally fan-out with a
    single org-scoped query and a canonical server-side predicate shared by
    all consumers. The response is deliberately bounded and reports when it
    has been truncated.
    """

    await _get_org_scoped_match(match_id, principal, db)
    zone_value = cast(Zone | None, zone)
    result = await db.execute(
        select(Action, Outcome, Rally.index_in_set, MatchSetRow.index)
        .join(Rally, Action.rally_id == Rally.id)
        .join(MatchSetRow, Rally.set_id == MatchSetRow.id)
        .outerjoin(Outcome, Outcome.action_id == Action.id)
        .where(MatchSetRow.match_id == match_id)
        .order_by(MatchSetRow.index, Rally.index_in_set, Action.video_t_start)
    )

    matching_events: list[StatEvidenceEventOut] = []
    for sequence, (action, outcome, rally_index, set_index) in enumerate(result.all()):
        record = ActionRecord(
            id=action.id,
            rally_id=action.rally_id,
            sequence=sequence,
            action_type=action.action_type,
            actor_team_id=action.actor_team_id,
            actor_roster_id=action.actor_roster_id,
            outcome=outcome.result if outcome else None,
            court_x=action.court_x,
            court_y=action.court_y,
            quality_rating=action.quality_rating,
        )
        if not matches_stat_category(record, category, team_id, zone_value):
            continue
        matching_events.append(
            StatEvidenceEventOut(
                action_id=action.id,
                rally_id=action.rally_id,
                set_index=set_index,
                rally_index_in_set=rally_index,
                action_type=action.action_type,
                actor_team_id=action.actor_team_id,
                video_t_start=action.video_t_start,
                video_t_end=action.video_t_end,
                court_x=action.court_x,
                court_y=action.court_y,
                quality_rating=action.quality_rating,
                outcome=outcome.result if outcome else None,
            )
        )

    total = len(matching_events)
    events = matching_events[:limit]
    return StatEvidenceOut(
        formula_version=FORMULA_VERSION,
        category=category,
        team_id=team_id,
        zone=zone_value,
        total_events=total,
        returned_events=len(events),
        is_truncated=total > len(events),
        events=events,
    )
