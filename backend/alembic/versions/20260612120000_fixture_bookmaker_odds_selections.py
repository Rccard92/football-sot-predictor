"""fixture_bookmaker_odds — selection_key per riga

Revision ID: 20260612120000
Revises: 20260611120000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260612120000"
down_revision: Union[str, Sequence[str], None] = "20260611120000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.add_column(
        "fixture_bookmaker_odds",
        sa.Column("provider_fixture_id", sa.BigInteger(), nullable=True),
    )
    op.add_column("fixture_bookmaker_odds", sa.Column("market_label", sa.String(length=255), nullable=True))
    op.add_column(
        "fixture_bookmaker_odds",
        sa.Column("selection_key", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "fixture_bookmaker_odds",
        sa.Column("selection_label", sa.String(length=128), nullable=True),
    )
    op.add_column("fixture_bookmaker_odds", sa.Column("odds_value", sa.Float(), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, home_odds, draw_odds, away_odds, competition_id, fixture_id,
                   provider_source, provider_bookmaker_id, bookmaker_name,
                   provider_market_id, normalized_market, raw_payload_json, odds_updated_at
            FROM fixture_bookmaker_odds
            WHERE selection_key IS NULL
            """,
        ),
    ).fetchall()

    for row in rows:
        rid, home, draw, away = row[0], row[1], row[2], row[3]
        base = {
            "competition_id": row[4],
            "fixture_id": row[5],
            "provider_source": row[6],
            "provider_bookmaker_id": row[7],
            "bookmaker_name": row[8],
            "provider_market_id": row[9],
            "normalized_market": row[10] or "MATCH_WINNER_1X2",
            "raw_payload_json": row[11],
            "odds_updated_at": row[12],
            "market_label": "Match Winner",
        }
        selections = [
            ("HOME", "1", home),
            ("DRAW", "X", draw),
            ("AWAY", "2", away),
        ]
        first = True
        for sk, sl, val in selections:
            if val is None:
                continue
            if first:
                conn.execute(
                    sa.text(
                        """
                        UPDATE fixture_bookmaker_odds
                        SET selection_key = :sk, selection_label = :sl, odds_value = :val,
                            market_label = :ml
                        WHERE id = :id
                        """,
                    ),
                    {"sk": sk, "sl": sl, "val": val, "ml": base["market_label"], "id": rid},
                )
                first = False
            else:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO fixture_bookmaker_odds (
                            competition_id, fixture_id, provider_source, provider_bookmaker_id,
                            bookmaker_name, provider_market_id, normalized_market, market_label,
                            selection_key, selection_label, odds_value, raw_payload_json, odds_updated_at
                        ) VALUES (
                            :competition_id, :fixture_id, :provider_source, :provider_bookmaker_id,
                            :bookmaker_name, :provider_market_id, :normalized_market, :market_label,
                            :selection_key, :selection_label, :odds_value, :raw_payload_json, :odds_updated_at
                        )
                        """,
                    ),
                    {**base, "selection_key": sk, "selection_label": sl, "odds_value": val},
                )
        if first:
            conn.execute(
                sa.text("DELETE FROM fixture_bookmaker_odds WHERE id = :id"),
                {"id": rid},
            )

    op.drop_constraint("uq_fixture_bookmaker_odds_scope", "fixture_bookmaker_odds", type_="unique")
    op.drop_column("fixture_bookmaker_odds", "home_odds")
    op.drop_column("fixture_bookmaker_odds", "draw_odds")
    op.drop_column("fixture_bookmaker_odds", "away_odds")

    op.alter_column("fixture_bookmaker_odds", "selection_key", nullable=False)
    op.alter_column("fixture_bookmaker_odds", "odds_value", nullable=False)

    op.create_unique_constraint(
        "uq_fixture_bookmaker_odds_selection",
        "fixture_bookmaker_odds",
        [
            "competition_id",
            "fixture_id",
            "provider_source",
            "provider_bookmaker_id",
            "normalized_market",
            "selection_key",
        ],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.drop_constraint("uq_fixture_bookmaker_odds_selection", "fixture_bookmaker_odds", type_="unique")
    op.add_column("fixture_bookmaker_odds", sa.Column("home_odds", sa.Float(), nullable=True))
    op.add_column("fixture_bookmaker_odds", sa.Column("draw_odds", sa.Float(), nullable=True))
    op.add_column("fixture_bookmaker_odds", sa.Column("away_odds", sa.Float(), nullable=True))
    op.drop_column("fixture_bookmaker_odds", "odds_value")
    op.drop_column("fixture_bookmaker_odds", "selection_label")
    op.drop_column("fixture_bookmaker_odds", "selection_key")
    op.drop_column("fixture_bookmaker_odds", "market_label")
    op.drop_column("fixture_bookmaker_odds", "provider_fixture_id")
    op.create_unique_constraint(
        "uq_fixture_bookmaker_odds_scope",
        "fixture_bookmaker_odds",
        [
            "competition_id",
            "fixture_id",
            "provider_source",
            "provider_bookmaker_id",
            "normalized_market",
        ],
    )
