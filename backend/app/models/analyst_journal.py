"""Diario analisi (dal 30/10/2026): le giocate scelte da un analista e le sue progressioni di cassa.

Sostituisce il file "IL CECCHINO (Report).xlsm": scheda pronostico (checklist), gare della settimana, esiti,
report e gestione cassa con i metodi Cecchino / CeccXino / 8a Meraviglia.
Decisioni dell'utente (30/10/2026): puntate reali in euro; ogni analista vede solo le sue giocate, gli
amministratori tutte; una giocata si blocca al calcio d'inizio (restano modificabili solo le note).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

_PK = BigInteger().with_variant(Integer(), "sqlite")

ENTRY_PENDING = "pending"
ENTRY_WON = "won"
ENTRY_LOST = "lost"
ENTRY_VOID = "void"

CYCLE_OPEN = "aperta"
CYCLE_CLOSED = "chiusa"


class AnalystCycle(Base, TimestampMixin):
    """Una progressione di cassa: metodo, impostazioni iniziali e le giocate collegate."""

    __tablename__ = "analyst_cycles"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(_PK, ForeignKey("app_users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)  # cecchino | ceccxino | meraviglia
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=CYCLE_OPEN)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnalystEntry(Base, TimestampMixin):
    """Una giocata del diario (una riga del foglio "GARE ATTUALE KW" + la sua scheda pronostico)."""

    __tablename__ = "analyst_entries"

    id: Mapped[int] = mapped_column(_PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(_PK, ForeignKey("app_users.id"), nullable=False, index=True)
    cycle_id: Mapped[int | None] = mapped_column(_PK, ForeignKey("analyst_cycles.id"), nullable=True, index=True)
    # partita (da Cecchino Today); se viene rinviata si segue con provider_fixture_id
    today_fixture_id: Mapped[int | None] = mapped_column(_PK, nullable=True, index=True)
    provider_fixture_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    match_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    country_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    home_team: Mapped[str] = mapped_column(String(120), nullable=False)
    away_team: Mapped[str] = mapped_column(String(120), nullable=False)
    # pronostico
    source: Mapped[str] = mapped_column(String(24), nullable=False)  # today | bet_builder | bet_builder_v3
    market_key: Mapped[str] = mapped_column(String(24), nullable=False)
    market_label: Mapped[str] = mapped_column(String(40), nullable=False)
    quota: Mapped[float] = mapped_column(Float, nullable=False)
    stake: Mapped[float | None] = mapped_column(Float, nullable=True)  # euro puntati
    stake_suggested: Mapped[float | None] = mapped_column(Float, nullable=True)  # dal metodo, quando e' stata salvata
    tool_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # cosa diceva il tool in quel momento
    # scheda pronostico: {chiave: {"value": favorevole|neutro|contrario, "note": "..."}}
    checklist_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    analysis_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # descrizione modalita' di intervento
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)  # modificabili anche dopo la partita
    minutes_spent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # esito (automatico dai risultati)
    outcome: Mapped[str] = mapped_column(String(12), nullable=False, default=ENTRY_PENDING)
    result_ht: Mapped[str | None] = mapped_column(String(12), nullable=True)
    result_ft: Mapped[str | None] = mapped_column(String(12), nullable=True)
    profit: Mapped[float | None] = mapped_column(Float, nullable=True)  # euro
    profit_units: Mapped[float | None] = mapped_column(Float, nullable=True)  # a 1 unita'
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
