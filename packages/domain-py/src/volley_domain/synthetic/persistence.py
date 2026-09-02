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

from volley_domain.models import Match
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


def _get_or_create_season(
    db: Session, *, organization_id: str, name: str, start_date: date
) -> Season:
    """Keyed on (organization_id, name), per TECH_DEBT.md's fix
    recommendation -- repeated demo generation must not accumulate a fresh
    'Synthetic Demo Season' row every single call."""
    existing = (
        db.query(Season)
        .filter(Season.organization_id == organization_id, Season.name == name)
        .one_or_none()
    )
    if existing is not None:
        return existing
    season = Season(organization_id=organization_id, name=name, start_date=start_date)
    db.add(season)
    db.flush()
    return season


def _get_or_create_team(db: Session, *, organization_id: str, name: str) -> Team:
    existing = (
        db.query(Team)
        .filter(Team.organization_id == organization_id, Team.name == name)
        .one_or_none()
    )
    if existing is not None:
        return existing
    team = Team(organization_id=organization_id, name=name)
    db.add(team)
    db.flush()
    return team


def _get_or_create_player(
    db: Session, *, organization_id: str, first_name: str, last_name: str
) -> Player:
    """Keyed on (organization_id, first_name, last_name) -- sound *only*
    because this generator's player names are deterministic per team-name
    + roster index ("{team_name} Player {i+1}"), never per seed, so the
    same name always refers to the same synthetic person across repeated
    demo runs. This key would be wrong for real players (two real people
    can share a name) -- never reuse this helper outside the synthetic
    demo path."""
    existing = (
        db.query(Player)
        .filter(
            Player.organization_id == organization_id,
            Player.first_name == first_name,
            Player.last_name == last_name,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    player = Player(organization_id=organization_id, first_name=first_name, last_name=last_name)
    db.add(player)
    db.flush()
    return player


def _get_or_create_roster(
    db: Session,
    *,
    team_id: str,
    player_id: str,
    season_id: str,
    jersey_number: int,
    position: RosterPosition,
    is_libero: bool,
) -> Roster:
    """Keyed on (team_id, player_id, season_id) -- the actual membership
    identity. `uq_roster_team_season_jersey` alone would not catch a
    duplicate here (a re-run's freshly-randomized jersey_number for the
    same physical player would differ from the earlier run's), so this
    must be an application-level lookup, not something a DB constraint
    happens to already enforce."""
    existing = (
        db.query(Roster)
        .filter(
            Roster.team_id == team_id, Roster.player_id == player_id, Roster.season_id == season_id
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    roster = Roster(
        team_id=team_id,
        player_id=player_id,
        season_id=season_id,
        jersey_number=jersey_number,
        position=position,
        is_libero=is_libero,
    )
    db.add(roster)
    db.flush()
    return roster


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
    season = _get_or_create_season(
        db,
        organization_id=organization_id,
        name="Synthetic Demo Season",
        start_date=date(synthetic.generated_at.year, 1, 1),
    )

    home_team = _get_or_create_team(
        db, organization_id=organization_id, name=synthetic.home_roster.team_name
    )
    away_team = _get_or_create_team(
        db, organization_id=organization_id, name=synthetic.away_roster.team_name
    )

    # Link the Match row to the Team rows we just created -- MatchOut
    # exposes these so the frontend can resolve "home"/"away" without
    # inferring it from the synthetic JSON blob. An earlier version never
    # did this (only match.status was ever written to Match), so
    # MatchOut.home_team_id/away_team_id would have shipped permanently
    # null despite existing on the model -- caught by independent
    # architecture review before the API field was even added.
    #
    # A missing Match here is a caller-contract violation, not a normal
    # case to swallow -- this function's own docstring requires the Match
    # to already exist (MatchSet.match_id is NOT NULL). An earlier version
    # silently no-op'd instead of raising, which is exactly the class of
    # "write that never happens with nothing complaining" this fix exists
    # to close -- caught by independent re-review.
    match = db.get(Match, match_id)
    if match is None:
        raise ValueError(f"persist_synthetic_match: no Match row exists for match_id={match_id!r}")
    match.home_team_id = home_team.id
    match.away_team_id = away_team.id

    team_row_by_side = {"home": home_team, "away": away_team}
    roster_row_by_player_id: dict[str, Roster] = {}

    for side, roster in (("home", synthetic.home_roster), ("away", synthetic.away_roster)):
        team_row = team_row_by_side[side]
        for player in roster.players:
            first_name, last_name = _split_name(player.name)
            player_row = _get_or_create_player(
                db, organization_id=organization_id, first_name=first_name, last_name=last_name
            )
            roster_row = _get_or_create_roster(
                db,
                team_id=team_row.id,
                player_id=player_row.id,
                season_id=season.id,
                jersey_number=player.jersey_number,
                position=RosterPosition(player.position),
                is_libero=(player.position == "L"),
            )
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

                    outcome_row = Outcome(
                        action_id=action_row.id,
                        result=synthetic_action.outcome,
                        detail=synthetic_action.detail,
                    )
                    db.add(outcome_row)

    db.flush()
    return pipeline_run
