from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class TeamSotPrediction(Base, TimestampMixin):
    __tablename__ = "team_sot_predictions"
    __table_args__ = (
        UniqueConstraint(
            "fixture_id",
            "team_id",
            "model_version",
            name="uq_team_sot_predictions_fixture_team_model",
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
    model_version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    predicted_sot: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="team_sot_predictions")
    team = relationship("Team", back_populates="team_sot_predictions")
