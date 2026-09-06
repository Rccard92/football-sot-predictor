"""add bet365 enrichment columns

Revision ID: 99102f74d1c9
Revises: df845d7b484f
Create Date: 2026-09-06 19:41:05.622462

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99102f74d1c9'
down_revision: Union[str, Sequence[str], None] = 'df845d7b484f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cecchino_lab_matches", sa.Column("bet365_dc_1x", sa.Numeric(10, 3), nullable=True))
    op.add_column("cecchino_lab_matches", sa.Column("bet365_dc_12", sa.Numeric(10, 3), nullable=True))
    op.add_column("cecchino_lab_matches", sa.Column("bet365_dc_x2", sa.Numeric(10, 3), nullable=True))

    op.add_column("cecchino_lab_matches", sa.Column("bet365_over_05", sa.Numeric(10, 3), nullable=True))
    op.add_column("cecchino_lab_matches", sa.Column("bet365_under_05", sa.Numeric(10, 3), nullable=True))

    op.add_column("cecchino_lab_matches", sa.Column("bet365_over_15", sa.Numeric(10, 3), nullable=True))
    op.add_column("cecchino_lab_matches", sa.Column("bet365_under_15", sa.Numeric(10, 3), nullable=True))

    op.add_column("cecchino_lab_matches", sa.Column("bet365_over_35", sa.Numeric(10, 3), nullable=True))
    op.add_column("cecchino_lab_matches", sa.Column("bet365_under_35", sa.Numeric(10, 3), nullable=True))

    op.add_column("cecchino_lab_matches", sa.Column("bet365_ht_home", sa.Numeric(10, 3), nullable=True))
    op.add_column("cecchino_lab_matches", sa.Column("bet365_ht_draw", sa.Numeric(10, 3), nullable=True))
    op.add_column("cecchino_lab_matches", sa.Column("bet365_ht_away", sa.Numeric(10, 3), nullable=True))


def downgrade() -> None:
    op.drop_column("cecchino_lab_matches", "bet365_ht_away")
    op.drop_column("cecchino_lab_matches", "bet365_ht_draw")
    op.drop_column("cecchino_lab_matches", "bet365_ht_home")

    op.drop_column("cecchino_lab_matches", "bet365_under_35")
    op.drop_column("cecchino_lab_matches", "bet365_over_35")

    op.drop_column("cecchino_lab_matches", "bet365_under_15")
    op.drop_column("cecchino_lab_matches", "bet365_over_15")

    op.drop_column("cecchino_lab_matches", "bet365_under_05")
    op.drop_column("cecchino_lab_matches", "bet365_over_05")

    op.drop_column("cecchino_lab_matches", "bet365_dc_x2")
    op.drop_column("cecchino_lab_matches", "bet365_dc_12")
    op.drop_column("cecchino_lab_matches", "bet365_dc_1x")