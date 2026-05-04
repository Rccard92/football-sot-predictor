from sqlalchemy import BigInteger, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class PlayerSotProfile(Base, TimestampMixin):
    __tablename__ = "player_sot_profiles"
    __table_args__ = (
        UniqueConstraint("season_id", "player_id", name="uq_player_sot_profiles_season_player"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    team_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    appearances: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    starts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_shots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_shots_on_target: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shots_on_target_per90: Mapped[float | None] = mapped_column(Float, nullable=True)
    team_sot_share_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last5_shots_on_target_per90: Mapped[float | None] = mapped_column(Float, nullable=True)
    reliability_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impact_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    season = relationship("Season", back_populates="player_sot_profiles")
    team = relationship("Team", back_populates="player_sot_profiles")
    player = relationship("Player", back_populates="sot_profile_rows")
