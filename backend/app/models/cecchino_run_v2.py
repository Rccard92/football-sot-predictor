"""Modelli RUN V2 Cecchino Lab (isolati dalle tabelle RUN V1, solo additivi)."""

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

RUN_V2_STATUS_PENDING = "pending"
RUN_V2_STATUS_RUNNING = "running"
RUN_V2_STATUS_COMPLETED = "completed"
RUN_V2_STATUS_COMPLETED_WITH_WARNINGS = "completed_with_warnings"
RUN_V2_STATUS_FAILED = "failed"
RUN_V2_STATUS_CANCELLED = "cancelled"

RUN_V2_ACTIVE_STATUSES = frozenset({RUN_V2_STATUS_PENDING, RUN_V2_STATUS_RUNNING})
RUN_V2_TERMINAL_STATUSES = frozenset(
    {
        RUN_V2_STATUS_COMPLETED,
        RUN_V2_STATUS_COMPLETED_WITH_WARNINGS,
        RUN_V2_STATUS_FAILED,
        RUN_V2_STATUS_CANCELLED,
    }
)

# Layer di osservazione: un mercato puo avere entrambi i record contemporaneamente.
OBSERVATION_LAYER_CORE_STRICT = "core_strict"
OBSERVATION_LAYER_ECONOMIC = "economic_observation"

OBSERVATION_LAYERS = frozenset(
    {OBSERVATION_LAYER_CORE_STRICT, OBSERVATION_LAYER_ECONOMIC}
)

SNAPSHOT_STATUS_PROCESSED = "processed"
SNAPSHOT_STATUS_ERROR = "error"


class CecchinoRunV2Run(Base, TimestampMixin):
    """Header di una RUN V2 sull'intero dataset Cecchino Lab."""

    __tablename__ = "cecchino_run_v2_runs"
    __table_args__ = (
        Index("ix_cecchino_run_v2_runs_status", "status"),
        Index("ix_cecchino_run_v2_runs_version_status", "run_version", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RUN_V2_STATUS_PENDING, index=True
    )
    run_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="full")
    max_matches: Mapped[int | None] = mapped_column(Integer, nullable=True)

    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    matches_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_error: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    market_rows_written: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    leakage_violations: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)

    min_kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    current_competition: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_lab_match_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_processed_kickoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    quote_policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    module_policy_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    coverage_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    leakage_audit_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    warnings_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    source_git_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_git_commit_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_revision_status: Mapped[str | None] = mapped_column(String(32), nullable=True)

    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CecchinoRunV2MatchSnapshot(Base, TimestampMixin):
    """Snapshot pre-match congelato + label post-match, una riga per match."""

    __tablename__ = "cecchino_run_v2_match_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "lab_match_id", name="uq_cecchino_run_v2_snap_run_match"),
        Index("ix_cecchino_run_v2_snap_run_id", "run_id"),
        Index("ix_cecchino_run_v2_snap_lab_match_id", "lab_match_id"),
        Index("ix_cecchino_run_v2_snap_run_kickoff", "run_id", "kickoff_at"),
        Index("ix_cecchino_run_v2_snap_run_competition", "run_id", "competition_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_run_v2_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    dataset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_datasets.id", ondelete="CASCADE"),
        nullable=False,
    )
    lab_match_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_matches.id", ondelete="CASCADE"),
        nullable=False,
    )

    competition_name: Mapped[str] = mapped_column(String(128), nullable=False)
    competition_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    division_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    season_label: Mapped[str] = mapped_column(String(32), nullable=False)
    season_start_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kickoff_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    home_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    away_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chronological_order: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SNAPSHOT_STATUS_PROCESSED
    )
    eligibility_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    eligibility_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Pre-match congelato (nessun dato della partita stessa o del suo futuro).
    pre_match_payload_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    pre_match_payload_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pre_match_locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    input_snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    cecchino_output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    goal_markets_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    kpi_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    signals_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    balance_v5_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    goal_intensity_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    purchasability_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    quote_bundle_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # BLOCCO 2: rolling extra stats pre-match, mai input dei moduli CORE.
    extra_stats_prematch_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Label post-match: disponibili solo dopo il freeze della prediction.
    actuals_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    result_attached_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Audit anti-leakage esplicito.
    leakage_audit_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    history_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latest_history_kickoff_used: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pre_match_cutoff_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    warnings_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    error_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class CecchinoRunV2MarketResult(Base, TimestampMixin):
    """Risultato per (snapshot, mercato, layer).

    La chiave include `observation_layer` perche uno stesso mercato deve poter
    esporre in contemporanea il record CORE STRICT e quello ECONOMIC BENCHMARK
    senza che l'uno sovrascriva l'altro.
    """

    __tablename__ = "cecchino_run_v2_market_results"
    __table_args__ = (
        UniqueConstraint(
            "match_snapshot_id",
            "market_key",
            "observation_layer",
            name="uq_cecchino_run_v2_mkt_snap_key_layer",
        ),
        Index("ix_cecchino_run_v2_mkt_run_id", "run_id"),
        Index("ix_cecchino_run_v2_mkt_lab_match_id", "lab_match_id"),
        Index("ix_cecchino_run_v2_mkt_run_key_layer", "run_id", "market_key", "observation_layer"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_run_v2_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_snapshot_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_run_v2_match_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    lab_match_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_lab_matches.id", ondelete="CASCADE"),
        nullable=False,
    )

    market_key: Mapped[str] = mapped_column(String(32), nullable=False)
    market_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    market_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    line: Mapped[str | None] = mapped_column(String(16), nullable=True)
    observation_layer: Mapped[str] = mapped_column(String(32), nullable=False)

    # CORE STRICT: prediction e moduli, calcolati solo su input pre-match safe.
    prediction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    probability: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    quota_cecchino: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    kpi_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    edge_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    vantaggio_prob: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    signal_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signal_sources_json: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    buyability_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    buyability_class: Mapped[str | None] = mapped_column(String(48), nullable=True)
    equilibrium_state: Mapped[str | None] = mapped_column(String(48), nullable=True)
    goal_intensity_score: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)

    # Disponibilita e provenance della quota.
    market_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    market_quote_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quota_book: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    prob_book_raw: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    prob_book_fair: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    is_real_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_derived_quote: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    derivation_method: Mapped[str | None] = mapped_column(String(128), nullable=True)
    quote_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quote_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_column: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quote_snapshot_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pre_match_input_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    used_for_prediction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Esito reale (disponibile solo dopo il freeze).
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    won: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    flat_stake_profit: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    result_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # ECONOMIC BENCHMARK: mai chiamato strict/deployable, mai input di prediction.
    economic_benchmark_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    economic_benchmark_profit: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    economic_benchmark_roi: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    economic_observation_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
