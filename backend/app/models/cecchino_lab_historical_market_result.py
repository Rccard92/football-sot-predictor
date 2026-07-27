"""Risultati mercato per snapshot storico Cecchino Lab."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class CecchinoLabHistoricalMarketResult(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_historical_market_results"
    __table_args__ = (
        UniqueConstraint(
            "match_snapshot_id",
            "market_key",
            name="uq_cecchino_lab_hist_mkt_snap_key",
        ),
        Index("ix_cecchino_lab_hist_mkt_run_id", "run_id"),
        Index("ix_cecchino_lab_hist_mkt_market_key", "market_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_historical_scan_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_historical_match_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    lab_match_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_matches.id", ondelete="CASCADE"),
        nullable=False,
    )
    market_key: Mapped[str] = mapped_column(String(32), nullable=False)
    market_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    line: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quota_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    prob_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    quota_book: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    prob_book_raw: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prob_book_fair: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    quote_source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_real_book_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_derived_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derivation_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    edge_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    vantaggio_prob: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signal_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signal_sources_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    evaluation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    profit_1u_real: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    profit_1u_synthetic: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    result_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profit_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
