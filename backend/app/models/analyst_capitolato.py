"""Diario analisi, capitolato di Giovanni del 24/11/2026 (18 modifiche). Solo tabelle nuove.

- AnalystEntryChange: ogni modifica di una giocata dopo il salvataggio, con ora e campo (modifica 12);
- AnalystEntryPhoto: foto facoltative della giocata, ridotte a 1600 px e senza dati EXIF (modifica 18);
- AnalystPaperPlay: giocate "sulla carta", senza puntata, con il loro esito (modifica 11): i segni bloccati che
  l'analista voleva giocare e non ha registrato come eccezione, e l'ipotesi in prova "casa senza obiettivi,
  ospite in lotta: 2" (modifica 17);
- AnalystVenueGeo e AnalystWeather: coordinate della citta' della gara e previsione Open-Meteo (modifiche 5 e 13);
- AnalystLeagueZones: descrizione delle posizioni della classifica dal fornitore (modifica 17).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, Date, DateTime, Float, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

_PK = BigInteger().with_variant(Integer(), "sqlite")

PAPER_BLOCKED = "bloccato"  # segno bloccato scelto dall'analista e non registrato come eccezione
PAPER_HYPOTHESIS_2 = "ipotesi_2"  # casa senza obiettivi, ospite in lotta: segno 2 (ipotesi in prova)


class AnalystEntryChange(Base, TimestampMixin):
    __tablename__ = "analyst_entry_changes"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(_PK, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(_PK, nullable=True)
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_kickoff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AnalystEntryPhoto(Base, TimestampMixin):
    __tablename__ = "analyst_entry_photos"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(_PK, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(_PK, nullable=False)
    caption: Mapped[str] = mapped_column(String(200), nullable=False)
    mime: Mapped[str] = mapped_column(String(32), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    after_kickoff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # tolta dall'analista prima del via: la riga resta (niente si cancella), non si mostra piu'
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalystPaperPlay(Base, TimestampMixin):
    __tablename__ = "analyst_paper_plays"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(_PK, nullable=True, index=True)  # None per l'ipotesi (tutte le gare)
    today_fixture_id: Mapped[int] = mapped_column(_PK, nullable=False, index=True)
    provider_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    match_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    home_team: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team: Mapped[str] = mapped_column(String(120), nullable=False)
    market_key: Mapped[str] = mapped_column(String(24), nullable=False)
    market_label: Mapped[str] = mapped_column(String(40), nullable=False)
    quota: Mapped[float | None] = mapped_column(Float, nullable=True)  # Q, la quota usata dalle regole
    quota_cecchino: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasons_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # [{code, rule, text}]
    alerts_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # avvisi della modifica 17
    entry_id: Mapped[int | None] = mapped_column(_PK, nullable=True)  # registrata poi come eccezione
    outcome: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    result_ht: Mapped[str | None] = mapped_column(String(12), nullable=True)
    result_ft: Mapped[str | None] = mapped_column(String(12), nullable=True)
    profit_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalystVenueGeo(Base, TimestampMixin):
    __tablename__ = "analyst_venue_geo"
    __table_args__ = (UniqueConstraint("city", "country", name="uq_analyst_venue_geo_city_country"),)

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    city: Mapped[str] = mapped_column(String(160), nullable=False)
    country: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | nd
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    found_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    looked_up_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalystWeather(Base, TimestampMixin):
    __tablename__ = "analyst_weather"

    fixture_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # gara del nostro archivio
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | nd
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hourly_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # ora UTC -> valori


class AnalystLeagueZones(Base, TimestampMixin):
    __tablename__ = "analyst_league_zones"
    __table_args__ = (UniqueConstraint("league_id", "season_id", name="uq_analyst_league_zones_league_season"),)

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    league_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | nd | groups (piu' gironi)
    teams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zones_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # posizione -> descrizione
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
