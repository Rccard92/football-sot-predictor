"""Create isolated Cecchino Lab historical tables (Football-Data CSV archive).

Revision ID: 20260726220000
Revises: 20260721100000

Additive only: no changes to operative Cecchino / fixtures / odds tables.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260726220000"
down_revision: Union[str, Sequence[str], None] = "20260721100000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cecchino_lab_datasets",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_key", sa.String(length=160), nullable=False),
        sa.Column("competition_name", sa.String(length=128), nullable=False),
        sa.Column("country", sa.String(length=64), nullable=False),
        sa.Column("division_code", sa.String(length=16), nullable=True),
        sa.Column("season_label", sa.String(length=32), nullable=False),
        sa.Column("start_year", sa.Integer(), nullable=True),
        sa.Column("end_year", sa.Integer(), nullable=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Rome"),
        sa.Column(
            "source_provider",
            sa.String(length=64),
            nullable=False,
            server_default="football-data.co.uk",
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="empty"),
        sa.Column("matches_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "data_quality_status",
            sa.String(length=32),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "competition_name",
            "country",
            "season_label",
            "source_provider",
            name="uq_cecchino_lab_datasets_comp_country_season_source",
        ),
    )
    op.create_index(
        "ix_cecchino_lab_datasets_dataset_key", "cecchino_lab_datasets", ["dataset_key"]
    )
    op.create_index("ix_cecchino_lab_datasets_country", "cecchino_lab_datasets", ["country"])
    op.create_index(
        "ix_cecchino_lab_datasets_season_label", "cecchino_lab_datasets", ["season_label"]
    )
    op.create_index(
        "ix_cecchino_lab_datasets_quality_status",
        "cecchino_lab_datasets",
        ["data_quality_status"],
    )

    op.create_table(
        "cecchino_lab_imports",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("columns_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["cecchino_lab_datasets.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "file_sha256",
            "parser_version",
            name="uq_cecchino_lab_imports_sha_parser",
        ),
    )
    op.create_index(
        "ix_cecchino_lab_imports_dataset_id", "cecchino_lab_imports", ["dataset_id"]
    )
    op.create_index("ix_cecchino_lab_imports_status", "cecchino_lab_imports", ["status"])

    op.create_table(
        "cecchino_lab_matches",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=False),
        sa.Column("import_id", sa.BigInteger(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("division_code", sa.String(length=16), nullable=True),
        sa.Column("match_date", sa.Date(), nullable=True),
        sa.Column("match_time", sa.Time(), nullable=True),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("home_team", sa.String(length=128), nullable=True),
        sa.Column("away_team", sa.String(length=128), nullable=True),
        sa.Column("referee", sa.String(length=128), nullable=True),
        sa.Column("ft_home_goals", sa.Integer(), nullable=True),
        sa.Column("ft_away_goals", sa.Integer(), nullable=True),
        sa.Column("ft_result", sa.String(length=1), nullable=True),
        sa.Column("ht_home_goals", sa.Integer(), nullable=True),
        sa.Column("ht_away_goals", sa.Integer(), nullable=True),
        sa.Column("ht_result", sa.String(length=1), nullable=True),
        sa.Column("home_shots", sa.Integer(), nullable=True),
        sa.Column("away_shots", sa.Integer(), nullable=True),
        sa.Column("home_shots_on_target", sa.Integer(), nullable=True),
        sa.Column("away_shots_on_target", sa.Integer(), nullable=True),
        sa.Column("home_fouls", sa.Integer(), nullable=True),
        sa.Column("away_fouls", sa.Integer(), nullable=True),
        sa.Column("home_corners", sa.Integer(), nullable=True),
        sa.Column("away_corners", sa.Integer(), nullable=True),
        sa.Column("home_yellow_cards", sa.Integer(), nullable=True),
        sa.Column("away_yellow_cards", sa.Integer(), nullable=True),
        sa.Column("home_red_cards", sa.Integer(), nullable=True),
        sa.Column("away_red_cards", sa.Integer(), nullable=True),
        sa.Column("bet365_home", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_draw", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_away", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_over_25", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_under_25", sa.Numeric(10, 3), nullable=True),
        sa.Column("asian_handicap_home_line", sa.Numeric(8, 3), nullable=True),
        sa.Column("bet365_ah_home", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_ah_away", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_closing_home", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_closing_draw", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_closing_away", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_closing_over_25", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_closing_under_25", sa.Numeric(10, 3), nullable=True),
        sa.Column("asian_handicap_closing_home_line", sa.Numeric(8, 3), nullable=True),
        sa.Column("bet365_closing_ah_home", sa.Numeric(10, 3), nullable=True),
        sa.Column("bet365_closing_ah_away", sa.Numeric(10, 3), nullable=True),
        sa.Column("result_ft_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("result_ht_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "statistics_ready", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "bet365_1x2_pre_ready",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "bet365_1x2_closing_ready",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "bet365_ou25_pre_ready",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "bet365_ou25_closing_ready",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "row_quality_status",
            sa.String(length=32),
            nullable=False,
            server_default="partial",
        ),
        sa.Column("raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["cecchino_lab_datasets.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["import_id"], ["cecchino_lab_imports.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_lab_matches_dataset_id", "cecchino_lab_matches", ["dataset_id"]
    )
    op.create_index(
        "ix_cecchino_lab_matches_import_id", "cecchino_lab_matches", ["import_id"]
    )
    op.create_index(
        "ix_cecchino_lab_matches_match_date", "cecchino_lab_matches", ["match_date"]
    )
    op.create_index(
        "ix_cecchino_lab_matches_row_quality_status",
        "cecchino_lab_matches",
        ["row_quality_status"],
    )
    op.create_index(
        "ix_cecchino_lab_matches_home_team", "cecchino_lab_matches", ["home_team"]
    )
    op.create_index(
        "ix_cecchino_lab_matches_away_team", "cecchino_lab_matches", ["away_team"]
    )

    op.create_table(
        "cecchino_lab_data_issues",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("import_id", sa.BigInteger(), nullable=False),
        sa.Column("match_id", sa.BigInteger(), nullable=True),
        sa.Column("source_row_number", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("issue_code", sa.String(length=64), nullable=False),
        sa.Column("field_name", sa.String(length=64), nullable=True),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["import_id"], ["cecchino_lab_imports.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["match_id"], ["cecchino_lab_matches.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cecchino_lab_data_issues_import_id",
        "cecchino_lab_data_issues",
        ["import_id"],
    )
    op.create_index(
        "ix_cecchino_lab_data_issues_match_id",
        "cecchino_lab_data_issues",
        ["match_id"],
    )
    op.create_index(
        "ix_cecchino_lab_data_issues_severity",
        "cecchino_lab_data_issues",
        ["severity"],
    )
    op.create_index(
        "ix_cecchino_lab_data_issues_issue_code",
        "cecchino_lab_data_issues",
        ["issue_code"],
    )


def downgrade() -> None:
    op.drop_table("cecchino_lab_data_issues")
    op.drop_table("cecchino_lab_matches")
    op.drop_table("cecchino_lab_imports")
    op.drop_table("cecchino_lab_datasets")
