"""Cecchino V4: tabelle proprie (fixture, mappa squadre, registro quote, contesto, minuti giocatori,
run, previsioni, ragionamenti, shortlist, esami, sfidanti, job). Solo additiva.

Revision ID: 20260920090000_cecchino_v4
Revises: 20260916100000_api_football_data
Create Date: 2026-09-20 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260920090000_cecchino_v4"
down_revision: Union[str, Sequence[str], None] = "20260916100000_api_football_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _ts() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def _json(nullable: bool = True) -> sa.Column:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "cecchino_v4_fixtures",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("api_fixture_id", sa.BigInteger(), nullable=False),
        sa.Column("league_code", sa.String(8), nullable=False),
        sa.Column("api_league_id", sa.Integer(), nullable=False),
        sa.Column("competition", sa.String(64), nullable=False),
        sa.Column("season_label", sa.String(9), nullable=False),
        sa.Column("round", sa.String(64), nullable=True),
        sa.Column("match_date", sa.Date(), nullable=False),
        sa.Column("kickoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default="NS"),
        sa.Column("home_team_api_id", sa.BigInteger(), nullable=False),
        sa.Column("away_team_api_id", sa.BigInteger(), nullable=False),
        sa.Column("home_team", sa.String(128), nullable=False),
        sa.Column("away_team", sa.String(128), nullable=False),
        sa.Column("home_team_history", sa.String(128), nullable=True),
        sa.Column("away_team_history", sa.String(128), nullable=True),
        sa.Column("referee", sa.String(128), nullable=True),
        sa.Column("venue_city", sa.String(128), nullable=True),
        sa.Column("ft_home", sa.Integer(), nullable=True),
        sa.Column("ft_away", sa.Integer(), nullable=True),
        sa.Column("ht_home", sa.Integer(), nullable=True),
        sa.Column("ht_away", sa.Integer(), nullable=True),
        sa.Column("stats_json", _json(), nullable=True),
        sa.Column("stats_fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("events_json", _json(), nullable=True),
        sa.Column("lineups_status", sa.String(16), nullable=False, server_default="non_note"),
        sa.Column("lineups_json", _json(), nullable=True),
        *_ts(),
        sa.UniqueConstraint("api_fixture_id", name="uq_cecchino_v4_fixtures_api_fixture_id"),
    )
    op.create_index("ix_cecchino_v4_fixtures_kickoff_at", "cecchino_v4_fixtures", ["kickoff_at"])
    op.create_index("ix_cecchino_v4_fixtures_league_day", "cecchino_v4_fixtures", ["league_code", "match_date"])

    op.create_table(
        "cecchino_v4_team_map",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("league_code", sa.String(8), nullable=False),
        sa.Column("api_team_id", sa.BigInteger(), nullable=False),
        sa.Column("api_team_name", sa.String(128), nullable=False),
        sa.Column("history_team_name", sa.String(128), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        *_ts(),
        sa.UniqueConstraint("league_code", "api_team_id", name="uq_cecchino_v4_team_map_league_team"),
    )

    op.create_table(
        "cecchino_v4_odds_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fixture_id", sa.BigInteger(), sa.ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bookmaker_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("markets_json", _json(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cecchino_v4_odds_fixture_taken", "cecchino_v4_odds_snapshots", ["fixture_id", "taken_at"])
    op.create_index("ix_cecchino_v4_odds_taken_at", "cecchino_v4_odds_snapshots", ["taken_at"])

    op.create_table(
        "cecchino_v4_league_days",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("league_code", sa.String(8), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("standings_json", _json(), nullable=True),
        sa.Column("injuries_json", _json(), nullable=True),
        *_ts(),
        sa.UniqueConstraint("league_code", "day", name="uq_cecchino_v4_league_days"),
    )

    op.create_table(
        "cecchino_v4_player_minutes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fixture_id", sa.BigInteger(), sa.ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_api_id", sa.BigInteger(), nullable=False),
        sa.Column("player_api_id", sa.BigInteger(), nullable=False),
        sa.Column("player_name", sa.String(128), nullable=False),
        sa.Column("position", sa.String(4), nullable=True),
        sa.Column("minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.UniqueConstraint("fixture_id", "player_api_id", name="uq_cecchino_v4_player_minutes"),
    )
    op.create_index("ix_cecchino_v4_player_minutes_team", "cecchino_v4_player_minutes", ["team_api_id"])

    op.create_table(
        "cecchino_v4_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("config_json", _json(), nullable=True),
        sa.Column("summary_json", _json(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cecchino_v4_predictions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.BigInteger(), sa.ForeignKey("cecchino_v4_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fixture_id", sa.BigInteger(), sa.ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=True),
        sa.Column("history_match_id", sa.BigInteger(), nullable=True),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("payload_json", _json(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lineups_status", sa.String(16), nullable=False, server_default="non_note"),
    )
    op.create_index("ix_cecchino_v4_predictions_fixture_kind", "cecchino_v4_predictions", ["fixture_id", "kind"])
    op.create_index("ix_cecchino_v4_predictions_run", "cecchino_v4_predictions", ["run_id"])

    op.create_table(
        "cecchino_v4_explanations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("fixture_id", sa.BigInteger(), sa.ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("payload_json", _json(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("fixture_id", name="uq_cecchino_v4_explanations_fixture"),
    )

    op.create_table(
        "cecchino_v4_shortlists",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="provvisoria"),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("digest", sa.String(64), nullable=True),
        sa.Column("summary_json", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("day", name="uq_cecchino_v4_shortlists_day"),
    )

    op.create_table(
        "cecchino_v4_shortlist_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shortlist_id", sa.BigInteger(), sa.ForeignKey("cecchino_v4_shortlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fixture_id", sa.BigInteger(), sa.ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("market_key", sa.String(64), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("probability", sa.Float(), nullable=False),
        sa.Column("prob_low", sa.Float(), nullable=False),
        sa.Column("prob_high", sa.Float(), nullable=False),
        sa.Column("prob_prudent", sa.Float(), nullable=False),
        sa.Column("quota", sa.Float(), nullable=False),
        sa.Column("bookmaker_id", sa.Integer(), nullable=False),
        sa.Column("expected_profit", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="provvisoria"),
        sa.Column("withdraw_reason", sa.String(160), nullable=True),
        sa.Column("reason_json", _json(), nullable=True),
        sa.Column("closing_quota", sa.Float(), nullable=True),
        sa.Column("clv", sa.Float(), nullable=True),
        sa.Column("result", sa.String(8), nullable=True),
        sa.Column("profit_units", sa.Float(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cecchino_v4_shortlist_items_shortlist", "cecchino_v4_shortlist_items", ["shortlist_id"])
    op.create_index("ix_cecchino_v4_shortlist_items_fixture", "cecchino_v4_shortlist_items", ["fixture_id"])

    op.create_table(
        "cecchino_v4_exams",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("preregistration_path", sa.String(200), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("result_json", _json(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cecchino_v4_challengers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="candidato"),
        sa.Column("exam_json", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "cecchino_v4_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("params_json", _json(), nullable=True),
        sa.Column("progress_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("step", sa.String(160), nullable=True),
        sa.Column("api_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", _json(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cecchino_v4_jobs_name_created", "cecchino_v4_jobs", ["name", "created_at"])


def downgrade() -> None:
    for name in (
        "cecchino_v4_jobs",
        "cecchino_v4_challengers",
        "cecchino_v4_exams",
        "cecchino_v4_shortlist_items",
        "cecchino_v4_shortlists",
        "cecchino_v4_explanations",
        "cecchino_v4_predictions",
        "cecchino_v4_runs",
        "cecchino_v4_player_minutes",
        "cecchino_v4_league_days",
        "cecchino_v4_odds_snapshots",
        "cecchino_v4_team_map",
        "cecchino_v4_fixtures",
    ):
        op.drop_table(name)
