"""Risultati per valutazione teorica del replay Acquistabilità V3."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
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


class CecchinoLabPurchasabilityV3ReplayResult(Base, TimestampMixin):
    __tablename__ = "cecchino_lab_purchasability_v3_replay_results"
    __table_args__ = (
        UniqueConstraint(
            "replay_run_id",
            "source_snapshot_id",
            "market_key",
            name="uq_cecchino_lab_p3_replay_res_run_snap_mkt",
        ),
        Index("ix_cecchino_lab_p3_replay_res_run_id", "replay_run_id"),
        Index("ix_cecchino_lab_p3_replay_res_market_key", "market_key"),
        Index("ix_cecchino_lab_p3_replay_res_market_family", "market_family"),
        Index("ix_cecchino_lab_p3_replay_res_score", "score"),
        Index("ix_cecchino_lab_p3_replay_res_gate_status", "gate_status"),
        Index("ix_cecchino_lab_p3_replay_res_competition", "competition_name"),
        Index("ix_cecchino_lab_p3_replay_res_kickoff", "kickoff_at"),
        Index("ix_cecchino_lab_p3_replay_res_real_quote", "is_real_book_quote"),
        Index("ix_cecchino_lab_p3_replay_res_derived_quote", "is_derived_quote"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    replay_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_purchasability_v3_replay_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_scan_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_historical_scan_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_snapshot_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_market_result_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    lab_match_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    competition_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    chronological_order: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    market_key: Mapped[str] = mapped_column(String(32), nullable=False)
    market_family: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quote_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quote_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    performance_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_real_book_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_derived_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derivation_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quota_book: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    quota_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    prob_book_raw: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prob_book_fair: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prob_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    edge_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    vantaggio_prob: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)

    calculation_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    gate_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    gate_reason_codes_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    score_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    value_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    total_penalty: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    probability_risk_penalty: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    opposite_market_pressure_penalty: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    extreme_divergence_penalty: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    family_ambiguity_penalty: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    quote_quality_penalty: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    opposite_market_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opposite_fair_probability: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    selected_is_family_edge_leader: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    family_edge_gap_or_deficit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)

    calculation_quality: Mapped[str | None] = mapped_column(String(48), nullable=True)
    reason_codes_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    warnings_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    performance_evaluation_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    profit_1u_real: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    profit_1u_synthetic: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    result_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    source_pre_match_payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_pre_match_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    formula_payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    formula_payload_fields_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    pre_match_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    post_match_fields_excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
