from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.mixins import TimestampMixin


class Season(Base, TimestampMixin):
    __tablename__ = "seasons"
    __table_args__ = (
        UniqueConstraint("league_id", "year", name="uq_seasons_league_year"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    league_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("leagues.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    league = relationship("League", back_populates="seasons")
    fixtures = relationship("Fixture", back_populates="season")
