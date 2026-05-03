from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class PredictionBacktest(Base, TimestampMixin):
    __tablename__ = "prediction_backtests"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "fixture_id",
            "team_id",
            name="uq_prediction_backtests_batch_fixture_team",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
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
    predicted_sot: Mapped[float] = mapped_column(Float, nullable=False)
    actual_sot: Mapped[float] = mapped_column(Float, nullable=False)
    error: Mapped[float | None] = mapped_column(Float, nullable=True)
    squared_error: Mapped[float] = mapped_column(Float, nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    ingestion_run_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("ingestion_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    fixture = relationship("Fixture", back_populates="prediction_backtests")
    team = relationship("Team", back_populates="prediction_backtests")
    ingestion_run = relationship("IngestionRun", back_populates="prediction_backtests")
