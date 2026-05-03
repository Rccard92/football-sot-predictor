"""prediction_backtests: model_version, prediction_id, side; unique fixture+team+model

Revision ID: 20260509120000
Revises: 20260508120000
Create Date: 2026-05-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260509120000"
down_revision: Union[str, Sequence[str], None] = "20260508120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(inspector: sa.Inspector, bind) -> set[str]:
    if bind.dialect.name == "postgresql":
        return set(inspector.get_table_names(schema="public"))
    return set(inspector.get_table_names())


def table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in _table_names(inspector, bind)


def column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in _table_names(inspector, bind):
        return False
    col_kw: dict = {"schema": "public"} if bind.dialect.name == "postgresql" else {}
    columns = [col["name"] for col in inspector.get_columns(table_name, **col_kw)]
    return column_name in columns


def constraint_exists_pg(constraint_name: str) -> bool:
    bind = op.get_bind()
    r = bind.execute(
        sa.text("SELECT 1 FROM pg_constraint WHERE conname = :n"),
        {"n": constraint_name},
    )
    return r.scalar() is not None


def add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if table_exists(table_name) and not column_exists(table_name, column.name):
        op.add_column(table_name, column)


def upgrade() -> None:
    add_column_if_missing(
        "prediction_backtests",
        sa.Column("model_version", sa.String(length=64), nullable=True),
    )
    add_column_if_missing(
        "prediction_backtests",
        sa.Column("prediction_id", sa.BigInteger(), nullable=True),
    )
    add_column_if_missing(
        "prediction_backtests",
        sa.Column("side", sa.String(length=8), nullable=True),
    )
    add_column_if_missing("prediction_backtests", sa.Column("line_value", sa.Double(), nullable=True))
    add_column_if_missing(
        "prediction_backtests",
        sa.Column("predicted_side", sa.String(length=32), nullable=True),
    )
    add_column_if_missing(
        "prediction_backtests",
        sa.Column("actual_side", sa.String(length=32), nullable=True),
    )
    add_column_if_missing(
        "prediction_backtests",
        sa.Column("is_correct", sa.Boolean(), nullable=True),
    )

    bind = op.get_bind()
    if bind.dialect.name != "postgresql" or not table_exists("prediction_backtests"):
        return

    op.execute(
        sa.text(
            """
            UPDATE prediction_backtests
            SET model_version = COALESCE(details->>'model_version', 'legacy_batch')
            WHERE model_version IS NULL;
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            DELETE FROM prediction_backtests a
            USING prediction_backtests b
            WHERE a.id < b.id
              AND a.fixture_id = b.fixture_id
              AND a.team_id = b.team_id
              AND COALESCE(a.model_version, '') = COALESCE(b.model_version, '');
            """,
        ),
    )

    if constraint_exists_pg("uq_prediction_backtests_batch_fixture_team"):
        op.drop_constraint(
            "uq_prediction_backtests_batch_fixture_team",
            "prediction_backtests",
            type_="unique",
        )

    op.alter_column("prediction_backtests", "batch_id", nullable=True)

    if not constraint_exists_pg("uq_prediction_backtests_fixture_team_model"):
        op.create_unique_constraint(
            "uq_prediction_backtests_fixture_team_model",
            "prediction_backtests",
            ["fixture_id", "team_id", "model_version"],
        )

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_prediction_backtests_prediction_id'
              ) THEN
                ALTER TABLE prediction_backtests
                  ADD CONSTRAINT fk_prediction_backtests_prediction_id
                  FOREIGN KEY (prediction_id) REFERENCES team_sot_predictions(id) ON DELETE SET NULL;
              END IF;
            END $$;
            """,
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        for col in (
            "is_correct",
            "actual_side",
            "predicted_side",
            "line_value",
            "side",
            "prediction_id",
            "model_version",
        ):
            if table_exists("prediction_backtests") and column_exists("prediction_backtests", col):
                op.drop_column("prediction_backtests", col)
        return

    if bind.dialect.name == "postgresql" and table_exists("prediction_backtests"):
        op.execute(
            sa.text(
                "ALTER TABLE prediction_backtests DROP CONSTRAINT IF EXISTS fk_prediction_backtests_prediction_id;",
            ),
        )
        if constraint_exists_pg("uq_prediction_backtests_fixture_team_model"):
            op.drop_constraint(
                "uq_prediction_backtests_fixture_team_model",
                "prediction_backtests",
                type_="unique",
            )
        if not constraint_exists_pg("uq_prediction_backtests_batch_fixture_team"):
            op.create_unique_constraint(
                "uq_prediction_backtests_batch_fixture_team",
                "prediction_backtests",
                ["batch_id", "fixture_id", "team_id"],
            )
        op.alter_column("prediction_backtests", "batch_id", nullable=False)

    for col in (
        "is_correct",
        "actual_side",
        "predicted_side",
        "line_value",
        "side",
        "prediction_id",
        "model_version",
    ):
        if table_exists("prediction_backtests") and column_exists("prediction_backtests", col):
            op.drop_column("prediction_backtests", col)
