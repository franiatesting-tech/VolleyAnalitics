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

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from volley_domain.models import Match
from volley_domain.ontology import Action, Outcome, Rally
from volley_domain.ontology import MatchSet as MatchSetRow
from volley_domain.schemas import ActionOut, MatchSetOut, MatchStatisticsOut, RallyOut
from volley_domain.stats.engine import compute_match_statistics
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
                )
            )
        stats = compute_match_statistics(rally_records, action_records)

    return MatchStatisticsOut(
        formula_version=stats.formula_version,
        serve={k: vars(v) for k, v in stats.serve.items()},
        reception={k: vars(v) for k, v in stats.reception.items()},
        attack={k: vars(v) for k, v in stats.attack.items()},
        block={k: vars(v) for k, v in stats.block.items()},
        dig={k: vars(v) for k, v in stats.dig.items()},
        sideout_breakpoint={k: vars(v) for k, v in stats.sideout_breakpoint.items()},
        setter_distribution={k: vars(v) for k, v in stats.setter_distribution.items()},
        rally_duration=vars(stats.rally_duration),
    )
