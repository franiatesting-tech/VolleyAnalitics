"""volleyball ontology: Season/Competition/Team/Player/Roster/Lineup/
Rotation/MatchSet/Rally/Phase/Action/Outcome/Video/VideoAsset/PipelineRun/
ModelRun/BallObservation/PlayerObservation/HumanCorrection/ReviewedLabel

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-28

Hand-written, frozen DDL -- like 0001, NOT read from volley_domain's live
metadata at migration-run time. An earlier version of this migration called
`Table.create()`/`Table.drop()` against `Base.metadata.sorted_tables`
directly, which meant this file's behavior would silently change if
ontology.py was ever edited after this revision was considered final (e.g.
a future column rename would retroactively rewrite what "revision 0002"
means, instead of requiring a new revision). Caught by independent
architecture review: "the correct third option is to generate the DDL from
metadata once and freeze the result in the file." The table bodies below
were generated once from volley_domain's metadata (as of this revision) via
a one-off script and then reviewed by hand -- not hand-transcribed from
scratch, to avoid the transcription-drift risk 0001's docstring flags, but
frozen as plain text from this point on, exactly like 0001.

Verified via `alembic upgrade head --sql` (offline mode) to confirm the
exact DDL this produces is syntactically valid Postgres before ever
touching a real database (see PROJECT_STATUS.md -- no live Postgres was
available when this was authored).

Enum columns are stored as `sa.String` (matching the ORM's
`native_enum=False` choice, see ontology.py) rather than native Postgres
ENUM types -- consistent with how the ORM actually writes rows, and avoids
the extra migration complexity of managing Postgres enum type alterations
when a StrEnum gains a new member.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# models.py's Match/ProcessingJob gained these nullable FK columns alongside
# the new ontology (see ONTOLOGY.md's "Match structure" section) -- they
# reference tables this same migration creates, so must be added *after*
# the new-tables block in upgrade() and dropped *before* it in downgrade().


def upgrade() -> None:
    op.create_table(
        "human_corrections",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "field_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "previous_value",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "corrected_value",
            sa.JSON(),
            nullable=False,
        ),
        sa.Column(
            "corrected_by_user_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "corrected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "reason",
            sa.Text(),
            nullable=True,
        ),
        sa.Column(
            "correction_version",
            sa.Integer(),
            nullable=False,
        ),
    )
    op.create_index("ix_human_corrections_target_id", "human_corrections", ["target_id"])

    op.create_table(
        "players",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "first_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "last_name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_players_organization_id", "players", ["organization_id"])

    op.create_table(
        "reviewed_labels",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "target_type",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            sa.String(length=36),
            nullable=False,
        ),
        sa.Column(
            "reviewed_by_user_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),
    )
    op.create_index("ix_reviewed_labels_target_id", "reviewed_labels", ["target_id"])

    op.create_table(
        "seasons",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "start_date",
            sa.Date(),
            nullable=False,
        ),
        sa.Column(
            "end_date",
            sa.Date(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_seasons_organization_id", "seasons", ["organization_id"])

    op.create_table(
        "teams",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "short_name",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_teams_organization_id", "teams", ["organization_id"])

    op.create_table(
        "competitions",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "season_id",
            sa.String(length=36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "level",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_competitions_organization_id", "competitions", ["organization_id"])

    op.create_table(
        "rosters",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "player_id",
            sa.String(length=36),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "season_id",
            sa.String(length=36),
            sa.ForeignKey("seasons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "jersey_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "position",
            sa.String(length=8),
            nullable=False,
        ),
        sa.Column(
            "is_libero",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "team_id", "season_id", "jersey_number", name="uq_roster_team_season_jersey"
        ),
    )
    op.create_index("ix_rosters_player_id", "rosters", ["player_id"])
    op.create_index("ix_rosters_team_id", "rosters", ["team_id"])
    op.create_index("ix_rosters_season_id", "rosters", ["season_id"])

    op.create_table(
        "sets",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "match_id",
            sa.String(length=36),
            sa.ForeignKey("matches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "index",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "home_points",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "away_points",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "winner_team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "ended_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("match_id", "index", name="uq_set_match_index"),
    )
    op.create_index("ix_sets_match_id", "sets", ["match_id"])

    op.create_table(
        "videos",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "match_id",
            sa.String(length=36),
            sa.ForeignKey("matches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "filename",
            sa.String(length=500),
            nullable=False,
        ),
        sa.Column(
            "duration_seconds",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "fps",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "codec",
            sa.String(length=50),
            nullable=True,
        ),
        sa.Column(
            "video_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.UniqueConstraint("organization_id", "video_hash", name="uq_video_org_hash"),
    )
    op.create_index("ix_videos_organization_id", "videos", ["organization_id"])

    op.create_table(
        "lineups",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "set_id",
            sa.String(length=36),
            sa.ForeignKey("sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("set_id", "team_id", name="uq_lineup_set_team"),
    )
    op.create_index("ix_lineups_set_id", "lineups", ["set_id"])

    op.create_table(
        "pipeline_runs",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.String(length=36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "pipeline_version",
            sa.String(length=50),
            nullable=False,
        ),
        sa.Column(
            "config_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "code_commit",
            sa.String(length=40),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_pipeline_runs_video_id", "pipeline_runs", ["video_id"])

    op.create_table(
        "video_assets",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.String(length=36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "storage_ref",
            sa.String(length=1000),
            nullable=False,
        ),
        sa.Column(
            "start_ts",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "end_ts",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_video_assets_video_id", "video_assets", ["video_id"])

    op.create_table(
        "lineup_players",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "lineup_id",
            sa.String(length=36),
            sa.ForeignKey("lineups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_starting",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column(
            "is_libero_for_set",
            sa.Boolean(),
            nullable=False,
        ),
    )
    op.create_index("ix_lineup_players_lineup_id", "lineup_players", ["lineup_id"])

    op.create_table(
        "model_runs",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "pipeline_run_id",
            sa.String(length=36),
            sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "stage",
            sa.String(length=32),
            nullable=False,
        ),
        sa.Column(
            "model_version",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "weights_hash",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column(
            "dataset_version",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "metrics",
            sa.JSON(),
            nullable=True,
        ),
    )
    op.create_index("ix_model_runs_pipeline_run_id", "model_runs", ["pipeline_run_id"])

    op.create_table(
        "ball_observations",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.String(length=36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_run_id",
            sa.String(length=36),
            sa.ForeignKey("model_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "video_t",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "court_x",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "court_y",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "court_z",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "provenance",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_ball_observations_video_id", "ball_observations", ["video_id"])

    op.create_table(
        "player_observations",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "video_id",
            sa.String(length=36),
            sa.ForeignKey("videos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "model_run_id",
            sa.String(length=36),
            sa.ForeignKey("model_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "video_t",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "track_id",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "court_x",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "court_y",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_player_observations_video_id", "player_observations", ["video_id"])

    op.create_table(
        "rallies",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "set_id",
            sa.String(length=36),
            sa.ForeignKey("sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "index_in_set",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "serving_team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "point_winner_team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "video_t_start",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "video_t_end",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "duration_seconds",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "model_run_id",
            sa.String(length=36),
            sa.ForeignKey("model_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("set_id", "index_in_set", name="uq_rally_set_index"),
    )
    op.create_index("ix_rallies_set_id", "rallies", ["set_id"])

    op.create_table(
        "phases",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "rally_id",
            sa.String(length=36),
            sa.ForeignKey("rallies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "index_in_rally",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "phase_type",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "team_in_possession_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "model_run_id",
            sa.String(length=36),
            sa.ForeignKey("model_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("rally_id", "index_in_rally", name="uq_phase_rally_index"),
    )
    op.create_index("ix_phases_rally_id", "phases", ["rally_id"])

    op.create_table(
        "rotations",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "set_id",
            sa.String(length=36),
            sa.ForeignKey("sets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sequence_number",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "p1_roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id"),
            nullable=True,
        ),
        sa.Column(
            "p2_roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id"),
            nullable=True,
        ),
        sa.Column(
            "p3_roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id"),
            nullable=True,
        ),
        sa.Column(
            "p4_roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id"),
            nullable=True,
        ),
        sa.Column(
            "p5_roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id"),
            nullable=True,
        ),
        sa.Column(
            "p6_roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id"),
            nullable=True,
        ),
        sa.Column(
            "effective_from_rally_id",
            sa.String(length=36),
            sa.ForeignKey("rallies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_rotations_set_id", "rotations", ["set_id"])

    op.create_table(
        "actions",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "phase_id",
            sa.String(length=36),
            sa.ForeignKey("phases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rally_id",
            sa.String(length=36),
            sa.ForeignKey("rallies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "index_in_phase",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "action_type",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "actor_roster_id",
            sa.String(length=36),
            sa.ForeignKey("rosters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "video_t_start",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "video_t_end",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "court_x",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "court_y",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "confidence",
            sa.Float(),
            nullable=False,
        ),
        sa.Column(
            "model_run_id",
            sa.String(length=36),
            sa.ForeignKey("model_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reviewed_status",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "quality_rating",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "source_clip_ref",
            sa.String(length=500),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("phase_id", "index_in_phase", name="uq_action_phase_index"),
    )
    op.create_index("ix_actions_phase_id", "actions", ["phase_id"])
    op.create_index("ix_actions_rally_id", "actions", ["rally_id"])

    op.create_table(
        "outcomes",
        sa.Column(
            "id",
            sa.String(length=36),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "action_id",
            sa.String(length=36),
            sa.ForeignKey("actions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "result",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column(
            "detail",
            sa.String(length=255),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.add_column(
        "matches",
        sa.Column(
            "competition_id",
            sa.String(length=36),
            sa.ForeignKey("competitions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "season_id",
            sa.String(length=36),
            sa.ForeignKey("seasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "home_team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "matches",
        sa.Column(
            "away_team_id",
            sa.String(length=36),
            sa.ForeignKey("teams.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("matches", sa.Column("venue", sa.String(length=255), nullable=True))
    op.add_column(
        "processing_jobs",
        sa.Column(
            "pipeline_run_id",
            sa.String(length=36),
            sa.ForeignKey("pipeline_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("processing_jobs", "pipeline_run_id")
    op.drop_column("matches", "venue")
    op.drop_column("matches", "away_team_id")
    op.drop_column("matches", "home_team_id")
    op.drop_column("matches", "season_id")
    op.drop_column("matches", "competition_id")

    op.drop_table("outcomes")

    op.drop_index("ix_actions_rally_id", table_name="actions")
    op.drop_index("ix_actions_phase_id", table_name="actions")
    op.drop_table("actions")

    op.drop_index("ix_rotations_set_id", table_name="rotations")
    op.drop_table("rotations")

    op.drop_index("ix_phases_rally_id", table_name="phases")
    op.drop_table("phases")

    op.drop_index("ix_rallies_set_id", table_name="rallies")
    op.drop_table("rallies")

    op.drop_index("ix_player_observations_video_id", table_name="player_observations")
    op.drop_table("player_observations")

    op.drop_index("ix_ball_observations_video_id", table_name="ball_observations")
    op.drop_table("ball_observations")

    op.drop_index("ix_model_runs_pipeline_run_id", table_name="model_runs")
    op.drop_table("model_runs")

    op.drop_index("ix_lineup_players_lineup_id", table_name="lineup_players")
    op.drop_table("lineup_players")

    op.drop_index("ix_video_assets_video_id", table_name="video_assets")
    op.drop_table("video_assets")

    op.drop_index("ix_pipeline_runs_video_id", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")

    op.drop_index("ix_lineups_set_id", table_name="lineups")
    op.drop_table("lineups")

    op.drop_index("ix_videos_organization_id", table_name="videos")
    op.drop_table("videos")

    op.drop_index("ix_sets_match_id", table_name="sets")
    op.drop_table("sets")

    op.drop_index("ix_rosters_season_id", table_name="rosters")
    op.drop_index("ix_rosters_team_id", table_name="rosters")
    op.drop_index("ix_rosters_player_id", table_name="rosters")
    op.drop_table("rosters")

    op.drop_index("ix_competitions_organization_id", table_name="competitions")
    op.drop_table("competitions")

    op.drop_index("ix_teams_organization_id", table_name="teams")
    op.drop_table("teams")

    op.drop_index("ix_seasons_organization_id", table_name="seasons")
    op.drop_table("seasons")

    op.drop_index("ix_reviewed_labels_target_id", table_name="reviewed_labels")
    op.drop_table("reviewed_labels")

    op.drop_index("ix_players_organization_id", table_name="players")
    op.drop_table("players")

    op.drop_index("ix_human_corrections_target_id", table_name="human_corrections")
    op.drop_table("human_corrections")
