from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class TeamSotFeature(Base, TimestampMixin):
    __tablename__ = "team_sot_features"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "team_id",
            name="uq_team_sot_features_fixture_team",
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
    opponent_team_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    fixture_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    season_avg_sot_for: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    season_avg_sot_against: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    home_away_avg_sot_for: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    home_away_avg_sot_against: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    last5_avg_sot_for: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    last5_avg_sot_against: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    last10_avg_sot_for: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    last10_avg_sot_against: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    opponent_season_avg_sot_conceded: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    opponent_home_away_avg_sot_conceded: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)
    opponent_last5_avg_sot_conceded: Mapped[float | None] = mapped_column(Numeric(14, 6), nullable=True)

    rest_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_sot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    previous_matches_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opponent_previous_matches_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    feature_set_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="team_sot_features")
    team = relationship("Team", foreign_keys=[team_id], back_populates="team_sot_features")
    opponent_team = relationship("Team", foreign_keys=[opponent_team_id])
