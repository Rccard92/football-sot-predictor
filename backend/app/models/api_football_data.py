"""Collegamento dati API-Football per i motori: copertura campionati, statistiche scaricate, linee Bet365."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class ApiFootballLeagueCoverage(Base, TimestampMixin):
    """Cosa fornisce API-Football per campionato e stagione (letto da leagues?current=true)."""

    __tablename__ = "api_football_league_coverage"
    __table_args__ = (UniqueConstraint("provider_league_id", "season", name="uq_api_football_league_coverage"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_league_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    league_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    statistics_fixtures: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lineups: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    events: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    odds: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    injuries: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApiFootballFixtureFetch(Base, TimestampMixin):
    """Partite gia' richieste a fixtures?ids (per non richiederle di nuovo senza motivo)."""

    __tablename__ = "api_football_fixture_fetches"

    api_fixture_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fixture_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stats_teams: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stat_types: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lineups_teams: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CecchinoBet365MarketLine(Base, TimestampMixin):
    """Una linea .5 di un mercato Bet365 (gol, tiri, tiri in porta, corner, cartellini) per partita."""

    __tablename__ = "cecchino_bet365_market_lines"
    __table_args__ = (
        UniqueConstraint("provider_fixture_id", "market_key", "line", name="uq_cecchino_bet365_market_lines"),
        Index("ix_cecchino_bet365_market_lines_scan_date_market", "scan_date", "market_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_league_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    market_key: Mapped[str] = mapped_column(String(48), nullable=False)
    market_name: Mapped[str] = mapped_column(String(96), nullable=False)
    line: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    over_odd: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    under_odd: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    odds_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
