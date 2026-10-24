"""Cecchino V5: giocate degli specialisti (liste sigillate, docs/v5/LIVE_REGOLE.md)."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.cecchino_v4 import PkInteger


class CecchinoV5Play(Base):
    __tablename__ = "cecchino_v5_plays"
    __table_args__ = (
        UniqueConstraint("day", "specialist", "fixture_id", name="uq_cecchino_v5_plays_day_specialist_fixture"),
        Index("ix_cecchino_v5_plays_day", "day"),
        Index("ix_cecchino_v5_plays_fixture", "fixture_id"),
    )

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)  # data della partita, ora di Roma
    specialist: Mapped[str] = mapped_column(String(24), nullable=False)  # tiri_porta | angoli | cartellini | valore
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # consigliata | osservazione
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)  # cecchino_v4_fixtures.id
    league_code: Mapped[str] = mapped_column(String(8), nullable=False)
    market_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    expected: Mapped[float | None] = mapped_column(Float, nullable=True)  # valore atteso della statistica
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    prob_prudent: Mapped[float] = mapped_column(Float, nullable=False)
    quota: Mapped[float] = mapped_column(Float, nullable=False)
    bookmaker_id: Mapped[int] = mapped_column(Integer, nullable=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # orario della quota
    closing_quota: Mapped[float | None] = mapped_column(Float, nullable=True)
    clv: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str | None] = mapped_column(String(16), nullable=True)
    profit_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # combo (dal 24/10/2026): giocate della combo [{key, label}] e dettagli; bookmaker_id 0 = prodotto delle singole, -1 = senza quote
    legs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
