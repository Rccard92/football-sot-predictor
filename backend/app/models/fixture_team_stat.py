from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class FixtureTeamStat(Base, TimestampMixin):
    __tablename__ = "fixture_team_stats"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "team_id",
            name="uq_fixture_team_stats_fixture_team",
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
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_on_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_off_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blocked_shots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_inside_box: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shots_outside_box: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fouls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corner_kicks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offsides: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ball_possession_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    red_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goalkeeper_saves: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_passes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    accurate_passes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pass_accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_goals: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="team_stats")
    team = relationship("Team", back_populates="fixture_team_stats")
