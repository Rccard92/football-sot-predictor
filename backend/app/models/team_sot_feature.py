from typing import Any

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
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
    feature_set_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    fixture = relationship("Fixture", back_populates="team_sot_features")
    team = relationship("Team", back_populates="team_sot_features")
