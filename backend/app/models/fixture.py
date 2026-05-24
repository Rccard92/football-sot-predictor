from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class Fixture(Base, TimestampMixin):
    __tablename__ = "fixtures"
    __table_args__ = (UniqueConstraint("api_fixture_id", name="uq_fixtures_api_fixture_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    api_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    league_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    home_team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    away_team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round: Mapped[str | None] = mapped_column(String(64), nullable=True)
    referee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status_long: Mapped[str | None] = mapped_column(String(128), nullable=True)
    elapsed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goals_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    venue_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    venue_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    league = relationship("League", back_populates="fixtures")
    season = relationship("Season", back_populates="fixtures")
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_fixtures")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_fixtures")
    team_stats = relationship("FixtureTeamStat", back_populates="fixture")
    player_stats = relationship("FixturePlayerStat", back_populates="fixture")
    lineups = relationship("FixtureLineup", back_populates="fixture")
    team_sot_features = relationship("TeamSotFeature", back_populates="fixture")
    team_sot_predictions = relationship("TeamSotPrediction", back_populates="fixture")
    prediction_backtests = relationship("PredictionBacktest", back_populates="fixture")
    availability_events = relationship("PlayerAvailabilityEvent", back_populates="fixture")
    provider_mappings = relationship("FixtureProviderMapping", back_populates="fixture", cascade="all, delete-orphan")
    provider_lineups = relationship("FixtureProviderLineup", back_populates="fixture", cascade="all, delete-orphan")
    lineup_refresh_impacts = relationship(
        "FixtureLineupRefreshImpact",
        back_populates="fixture",
        cascade="all, delete-orphan",
    )
    tracked_betting_picks = relationship(
        "TrackedBettingPick",
        back_populates="fixture",
        cascade="all, delete-orphan",
    )
    fixture_referees = relationship(
        "FixtureReferee",
        back_populates="fixture",
        cascade="all, delete-orphan",
    )
