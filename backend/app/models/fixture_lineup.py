from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class FixtureLineup(Base, TimestampMixin):
    __tablename__ = "fixture_lineups"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "team_id",
            name="uq_fixture_lineups_fixture_team",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    formation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lineup_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="lineups")
    team = relationship("Team", back_populates="fixture_lineups")
