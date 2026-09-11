"""Pattern candidati scoperti dal motore walk-forward (una riga per candidato per fold)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class CecchinoDiscoveredPattern(Base, TimestampMixin):
    """Una foglia dell'albero di scoperta per un fold di training, con le sue
    statistiche out-of-sample sulla stagione di validazione successiva (mai vista
    durante la scoperta). Le foglie di uno stesso albero sono per costruzione
    mutuamente esclusive: non serve un controllo di ridondanza tra formula_slot
    dello stesso fold.
    """

    __tablename__ = "cecchino_discovered_patterns"
    __table_args__ = (
        Index("ix_cecchino_discovered_patterns_run_fold", "discovery_run_id", "fold_index"),
        Index("ix_cecchino_discovered_patterns_market_promoted", "market_key", "promoted"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    discovery_run_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("cecchino_pattern_discovery_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    market_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    fold_index: Mapped[int] = mapped_column(Integer, nullable=False)
    train_seasons_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    validation_season: Mapped[str] = mapped_column(String(32), nullable=False)
    formula_slot: Mapped[str | None] = mapped_column(String(1), nullable=True)

    rule_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    rule_text: Mapped[str] = mapped_column(Text, nullable=False)

    train_n: Mapped[int] = mapped_column(Integer, nullable=False)
    train_wins: Mapped[int] = mapped_column(Integer, nullable=False)
    train_win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    train_avg_profit_1u: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)

    oos_n: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    oos_wins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    oos_win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    oos_win_rate_ci_low_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    oos_win_rate_ci_high_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)
    oos_avg_profit_1u: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    oos_avg_profit_ci_low: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    oos_avg_profit_ci_high: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    oos_avg_quota_book: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    breakeven_win_rate_pct: Mapped[Decimal | None] = mapped_column(Numeric(6, 3), nullable=True)

    promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    promotion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
