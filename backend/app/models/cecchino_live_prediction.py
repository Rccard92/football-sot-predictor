"""Registro previsioni live: una riga per partita del giorno e per motore (V2, V2.5, V3).

La previsione si aggiorna solo prima del calcio d'inizio (`frozen_at` < kickoff); dopo il
calcio d'inizio resta congelata e a partita finita riceve gli esiti per mercato.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

LIVE_STATUS_OPEN = "open"
LIVE_STATUS_SETTLED = "settled"
LIVE_STATUS_VOID = "void"


class CecchinoLivePrediction(Base, TimestampMixin):
    __tablename__ = "cecchino_live_predictions"
    __table_args__ = (
        UniqueConstraint("today_fixture_id", "model", name="uq_cecchino_live_predictions_fixture_model"),
        Index("ix_cecchino_live_predictions_scan_date_model", "scan_date", "model"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    today_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    local_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str] = mapped_column(String(16), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=LIVE_STATUS_OPEN)
    frozen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    eligible: Mapped[bool] = mapped_column(nullable=False, default=True)
    # {market_key: {probability, quota_cecchino, quota_book, prob_book_fair, rating, ...}}
    markets_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # classi dei moduli (Equilibrio, Intensita' Goal, segnali) usate dai pattern
    modules_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {market_key: {won, profit}} + punteggio finale
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
