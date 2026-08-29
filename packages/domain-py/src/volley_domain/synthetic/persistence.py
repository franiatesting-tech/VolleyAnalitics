"""Persists a generated SyntheticMatch into the real ontology (Team/Roster/
MatchSet/Rally/Phase/Action/Outcome/PipelineRun/ModelRun) instead of the
Phase 1 JSON-blob pattern -- this is what pays down the tech debt entry
"Synthetic match data stored as a single JSON blob" in TECH_DEBT.md.

Deliberately separate from generator.py (which stays a pure function with
no DB dependency, per its own docstring) -- this module is the persistence
layer on top, so the pure generator remains independently testable and
reusable (e.g. for a future preview-without-saving feature) without pulling
in SQLAlchemy.
"""

import hashlib
from datetime import date

from sqlalchemy.orm import Session

from volley_domain.ontology import (
    Action,
    ModelRun,
    ModelRunStage,
    Outcome,
    Phase,
    PhaseType,
    PipelineRun,
    PipelineRunStatus,
    Player,
    Rally,
    Roster,
    RosterPosition,
    Season,
    Team,
)
from volley_domain.ontology import MatchSet as MatchSetRow
from volley_domain.schemas import SyntheticAction, SyntheticMatch


def _config_hash(synthetic: SyntheticMatch) -> str:
    return hashlib.sha256(f"synthetic:seed={synthetic.seed}".encode()).hexdigest()


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (full_name, "")


def _phase_groups(actions: list[SyntheticAction]) -> list[list[SyntheticAction]]:
    """Groups consecutive actions by actor team into possession segments --
    a new Phase starts whenever the acting team changes, matching
    ONTOLOGY.md's "Phase groups Actions by which team currently has the
    ball" definition. The synthetic generator's own team-swap logic
    (serve -> reception -> attack/dig alternation) already produces exactly
    these boundaries; this just detects them after the fact rather than
    requiring the generator to tag them itself."""
    groups: list[list[SyntheticAction]] = []
    for action in actions:
        if groups and groups[-1][-1].actor_team == action.actor_team:
            groups[-1].append(action)
        else:
            groups.append([action])
    return groups


def _phase_type_for_group(group: list[SyntheticAction], is_first_group: bool) -> PhaseType:
    if is_first_group and group[0].type == "serve":
        return PhaseType.SERVE
    if group[0].type == "reception":
        return PhaseType.RECEPTION
    return PhaseType.TRANSITION


def persist_synthetic_match(
    db: Session,
    *,
    organization_id: str,
    match_id: str,
    synthetic: SyntheticMatch,
) -> PipelineRun:
    """Writes a full SyntheticMatch into the ontology tables, linked to the
    given (already-existing) Match row -- MatchSet.match_id is a real,
    NOT NULL foreign key, so a Match must exist before calling this rather
    than being created/linked afterward. Caller is responsible for
    `db.commit()` (this function only adds/flushes, per the same pattern as
    volley_domain.corrections)."""
    season = Season(
        organization_id=organization_id,
        name="Synthetic Demo Season",
        start_date=date(synthetic.generated_at.year, 1, 1),
    )
    db.add(season)
    db.flush()

    home_team = Team(organization_id=organization_id, name=synthetic.home_roster.team_name)
    away_team = Team(organization_id=organization_id, name=synthetic.away_roster.team_name)
    db.add_all([home_team, away_team])
    db.flush()

    team_row_by_side = {"home": home_team, "away": away_team}
    roster_row_by_player_id: dict[str, Roster] = {}

    for side, roster in (("home", synthetic.home_roster), ("away", synthetic.away_roster)):
        team_row = team_row_by_side[side]
        for player in roster.players:
            first_name, last_name = _split_name(player.name)
            player_row = Player(
                organization_id=organization_id, first_name=first_name, last_name=last_name
            )
            db.add(player_row)
            db.flush()
            roster_row = Roster(
                team_id=team_row.id,
                player_id=player_row.id,
                season_id=season.id,
                jersey_number=player.jersey_number,
                position=RosterPosition(player.position),
                is_libero=(player.position == "L"),
            )
            db.add(roster_row)
            db.flush()
            roster_row_by_player_id[player.id] = roster_row

    pipeline_run = PipelineRun(
        video_id=None,  # synthetic data has no source video -- see PipelineRun's docstring
        pipeline_version="synthetic-v1",
        config_hash=_config_hash(synthetic),
        status=PipelineRunStatus.COMPLETED,
    )
    db.add(pipeline_run)
    db.flush()

    model_run = ModelRun(
        pipeline_run_id=pipeline_run.id,
        stage=ModelRunStage.SYNTHETIC,
        model_version="synthetic-generator-v1",
    )
    db.add(model_run)
    db.flush()

    for synthetic_set in synthetic.sets:
        winner_team_row = team_row_by_side[synthetic_set.score.winner]
        set_row = MatchSetRow(
            match_id=match_id,
            index=synthetic_set.index,
            home_points=synthetic_set.score.home_points,
            away_points=synthetic_set.score.away_points,
            winner_team_id=winner_team_row.id,
        )
        db.add(set_row)
        db.flush()

        for synthetic_rally in synthetic_set.rallies:
            serving_team_row = team_row_by_side[synthetic_rally.serving_team]
            point_winner_row = team_row_by_side[synthetic_rally.point_winner]
            rally_row = Rally(
                set_id=set_row.id,
                index_in_set=synthetic_rally.index_in_set,
                serving_team_id=serving_team_row.id,
                point_winner_team_id=point_winner_row.id,
                duration_seconds=synthetic_rally.duration_seconds,
                video_t_start=synthetic_rally.match_t_start,
                video_t_end=synthetic_rally.match_t_end,
            )
            db.add(rally_row)
            db.flush()

            phase_groups = _phase_groups(synthetic_rally.actions)
            for group_index, group in enumerate(phase_groups):
                phase_row = Phase(
                    rally_id=rally_row.id,
                    index_in_rally=group_index,
                    phase_type=_phase_type_for_group(group, group_index == 0),
                    team_in_possession_id=team_row_by_side[group[0].actor_team].id,
                )
                db.add(phase_row)
                db.flush()

                for action_index, synthetic_action in enumerate(group):
                    actor_team_row = team_row_by_side[synthetic_action.actor_team]
                    actor_roster_row = roster_row_by_player_id.get(synthetic_action.actor_player_id)
                    action_row = Action(
                        phase_id=phase_row.id,
                        rally_id=rally_row.id,
                        index_in_phase=action_index,
                        action_type=synthetic_action.type,
                        actor_roster_id=actor_roster_row.id if actor_roster_row else None,
                        actor_team_id=actor_team_row.id,
                        # SyntheticAction.t_start/t_end are rally-relative
                        # (see generator.py's _build_action_chain docstring);
                        # Action.video_t_* must be match-absolute, so add the
                        # rally's own match-clock offset here. An earlier
                        # version wrote the rally-relative value directly,
                        # so every rally in a multi-set match claimed the
                        # same ~0-12s window -- caught by independent
                        # architecture review.
                        video_t_start=synthetic_rally.match_t_start + synthetic_action.t_start,
                        video_t_end=synthetic_rally.match_t_start + synthetic_action.t_end,
                        court_x=synthetic_action.court_x,
                        court_y=synthetic_action.court_y,
                        confidence=synthetic_action.confidence,
                        model_run_id=model_run.id,
                    )
                    db.add(action_row)
                    db.flush()

                    outcome_row = Outcome(action_id=action_row.id, result=synthetic_action.outcome)
                    db.add(outcome_row)

    db.flush()
    return pipeline_run
