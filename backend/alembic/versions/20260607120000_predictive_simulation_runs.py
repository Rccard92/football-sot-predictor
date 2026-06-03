"""predictive_simulation_runs

Revision ID: 20260607120000
Revises: 20260606120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260607120000"
down_revision: Union[str, Sequence[str], None] = "20260606120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.create_table(
        "predictive_simulation_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("competition_id", sa.BigInteger(), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("season_label", sa.String(length=32), nullable=True),
        sa.Column("run_type", sa.String(length=32), nullable=False, server_default="full_lab"),
        sa.Column("model_version", sa.String(length=16), nullable=False, server_default="v3.1"),
        sa.Column("strategy_status_filter", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("strategies_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fixtures_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("round_range", sa.String(length=16), nullable=True),
        sa.Column("recommended_strategy", sa.String(length=64), nullable=True),
        sa.Column("recommendation_note", sa.Text(), nullable=True),
        sa.Column("recommendation_tradeoff", sa.Text(), nullable=True),
        sa.Column("phase", sa.String(length=64), nullable=False, server_default="predictive_numeric"),
        sa.Column("betting_phase_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "summary_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "simulator_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "pattern_payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "audit_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["competition_id"], ["competitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_predictive_simulation_runs_comp_season_created",
        "predictive_simulation_runs",
        ["competition_id", "season_year", "created_at"],
        unique=False,
    )

    op.create_table(
        "predictive_fixture_predictions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("home_team_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("away_team_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("strategy_key", sa.String(length=64), nullable=False),
        sa.Column("predicted_total_sot", sa.Float(), nullable=True),
        sa.Column("actual_total_sot", sa.Float(), nullable=True),
        sa.Column("error", sa.Float(), nullable=True),
        sa.Column("abs_error", sa.Float(), nullable=True),
        sa.Column("predicted_bucket", sa.String(length=32), nullable=True),
        sa.Column("actual_bucket", sa.String(length=32), nullable=True),
        sa.Column("actual_bucket_dynamic", sa.String(length=32), nullable=True),
        sa.Column("win_quality", sa.String(length=64), nullable=True),
        sa.Column("outcome_type", sa.String(length=64), nullable=True),
        sa.Column(
            "reason_codes_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("probable_reason", sa.Text(), nullable=True),
        sa.Column("boost_applied", sa.Float(), nullable=True),
        sa.Column("high_total_signal", sa.Float(), nullable=True),
        sa.Column("feature_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["predictive_simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "fixture_id",
            "strategy_key",
            name="uq_predictive_fixture_predictions_run_fixture_strategy",
        ),
    )
    op.create_index(
        "ix_predictive_fixture_predictions_run_id",
        "predictive_fixture_predictions",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_predictive_fixture_predictions_run_round",
        "predictive_fixture_predictions",
        ["run_id", "round_number"],
        unique=False,
    )
    op.create_index(
        "ix_predictive_fixture_predictions_run_strategy",
        "predictive_fixture_predictions",
        ["run_id", "strategy_key"],
        unique=False,
    )
    op.create_index(
        "ix_predictive_fixture_predictions_run_abs_error",
        "predictive_fixture_predictions",
        ["run_id", "abs_error"],
        unique=False,
    )

    op.create_table(
        "predictive_pattern_insights",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("insight_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "evidence_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("recommended_action", sa.Text(), nullable=True),
        sa.Column("strategy_key", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["predictive_simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_predictive_pattern_insights_run_id",
        "predictive_pattern_insights",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_predictive_pattern_insights_run_type",
        "predictive_pattern_insights",
        ["run_id", "insight_type"],
        unique=False,
    )

    op.create_table(
        "predictive_fixture_notes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy_key", sa.String(length=64), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("tag", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["predictive_simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "fixture_id",
            "strategy_key",
            name="uq_predictive_fixture_notes_run_fixture_strategy",
        ),
    )
    op.create_index(
        "ix_predictive_fixture_notes_run_id",
        "predictive_fixture_notes",
        ["run_id"],
        unique=False,
    )

    op.create_table(
        "predictive_ai_insights",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "output_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["predictive_simulation_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_predictive_ai_insights_run_id",
        "predictive_ai_insights",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.drop_index("ix_predictive_ai_insights_run_id", table_name="predictive_ai_insights")
    op.drop_table("predictive_ai_insights")
    op.drop_index("ix_predictive_fixture_notes_run_id", table_name="predictive_fixture_notes")
    op.drop_table("predictive_fixture_notes")
    op.drop_index("ix_predictive_pattern_insights_run_type", table_name="predictive_pattern_insights")
    op.drop_index("ix_predictive_pattern_insights_run_id", table_name="predictive_pattern_insights")
    op.drop_table("predictive_pattern_insights")
    op.drop_index("ix_predictive_fixture_predictions_run_abs_error", table_name="predictive_fixture_predictions")
    op.drop_index("ix_predictive_fixture_predictions_run_strategy", table_name="predictive_fixture_predictions")
    op.drop_index("ix_predictive_fixture_predictions_run_round", table_name="predictive_fixture_predictions")
    op.drop_index("ix_predictive_fixture_predictions_run_id", table_name="predictive_fixture_predictions")
    op.drop_table("predictive_fixture_predictions")
    op.drop_index("ix_predictive_simulation_runs_comp_season_created", table_name="predictive_simulation_runs")
    op.drop_table("predictive_simulation_runs")
