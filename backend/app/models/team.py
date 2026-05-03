from typing import Any

from sqlalchemy import BigInteger, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class Team(Base, TimestampMixin):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("api_team_id", name="uq_teams_api_team_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    api_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    players = relationship("Player", back_populates="team")
    home_fixtures = relationship(
        "Fixture",
        foreign_keys="Fixture.home_team_id",
        back_populates="home_team",
    )
    away_fixtures = relationship(
        "Fixture",
        foreign_keys="Fixture.away_team_id",
        back_populates="away_team",
    )
    fixture_team_stats = relationship("FixtureTeamStat", back_populates="team")
    fixture_player_stats = relationship("FixturePlayerStat", back_populates="team")
    fixture_lineups = relationship("FixtureLineup", back_populates="team")
    team_sot_features = relationship("TeamSotFeature", back_populates="team")
    team_sot_predictions = relationship("TeamSotPrediction", back_populates="team")
    prediction_backtests = relationship("PredictionBacktest", back_populates="team")
