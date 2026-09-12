"""Candidati trovati dal motore Pattern Grid — una riga per combinazione di
filtri, con lo storico completo stadio per stadio (lignaggio)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class CecchinoPatternGridCandidate(Base, TimestampMixin):
    __tablename__ = "cecchino_pattern_grid_candidates"
    __table_args__ = (
        Index("ix_cecchino_pattern_grid_candidates_run", "grid_run_id"),
        Index("ix_cecchino_pattern_grid_candidates_market_verdict", "market_key", "final_verdict"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    grid_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_pattern_grid_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    market_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    competition: Mapped[str | None] = mapped_column(String(128), nullable=True)

    filters_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    filters_text: Mapped[str] = mapped_column(Text, nullable=False)
    filters_text_human: Mapped[str] = mapped_column(Text, nullable=False)
    born_stage: Mapped[int] = mapped_column(Integer, nullable=False)
    refined_from_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    per_stage_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    total_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    total_roi_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True, index=True)
    total_avg_quota: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    final_verdict: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
