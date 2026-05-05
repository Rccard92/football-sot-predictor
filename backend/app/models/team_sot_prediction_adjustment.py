from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class TeamSotPredictionAdjustment(Base, TimestampMixin):
    __tablename__ = "team_sot_prediction_adjustments"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "team_id",
            "model_version",
            name="uq_team_sot_prediction_adjustments_fixture_team_model",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("team_sot_predictions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    baseline_expected_sot: Mapped[float] = mapped_column(Float, nullable=False)
    player_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    h2h_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    motivation_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    availability_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_adjustment: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    adjusted_expected_sot: Mapped[float] = mapped_column(Float, nullable=False)
    adjustment_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    prediction = relationship("TeamSotPrediction")
    fixture = relationship("Fixture")
    team = relationship("Team")
