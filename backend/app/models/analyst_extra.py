"""Dati in piu' per il Diario analisi (documento di Giovanni del 17/11/2026, migliorie 1-3).

- AnalystOddsRead: seconda lettura Bet365 di ogni gara ammessa 75 minuti prima del via (8 settimane), per
  misurare il movimento della probabilita' senza margine e se va verso il numero del Cecchino;
- AnalystTeamGame: calendario delle squadre in tutte le competizioni (coppe comprese) dalle liste delle gare del
  giorno del fornitore (una chiamata per giorno);
- AnalystLineup: formazione titolare di una squadra in una gara (e i gialli dagli eventi), per i titolari abituali;
- AnalystInjury: indisponibili annunciati dal fornitore per una gara (dove il fornitore li dichiara).
Solo tabelle nuove: niente di quello che c'era cambia.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin


class AnalystOddsRead(Base, TimestampMixin):
    __tablename__ = "analyst_odds_reads"
    __table_args__ = (UniqueConstraint("today_fixture_id", "kind", name="uq_analyst_odds_reads_fixture_kind"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    today_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="t75")  # t75 = 75 minuti prima del via
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | nd
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bookmaker_id: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    markets_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # chiave del Diario -> quota


class AnalystTeamGame(Base, TimestampMixin):
    __tablename__ = "analyst_team_games"
    __table_args__ = (UniqueConstraint("provider_fixture_id", name="uq_analyst_team_games_fixture"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    kickoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider_league_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    league_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    league_country: Mapped[str | None] = mapped_column(String(80), nullable=True)
    league_round: Mapped[str | None] = mapped_column(String(120), nullable=True)
    home_provider_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    away_provider_team_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    home_team_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    away_team_name: Mapped[str | None] = mapped_column(String(160), nullable=True)


class AnalystCalendarDay(Base, TimestampMixin):
    """Giorni gia' scaricati per il calendario (un giorno passato si scarica una volta, uno futuro ogni giorno)."""

    __tablename__ = "analyst_calendar_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    games: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AnalystLineup(Base, TimestampMixin):
    __tablename__ = "analyst_lineups"
    __table_args__ = (UniqueConstraint("provider_fixture_id", "provider_team_id", name="uq_analyst_lineups_fixture_team"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok | nd (il fornitore non la da')
    formation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    starters_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)  # [{id, name, pos}]
    yellow_cards: Mapped[int | None] = mapped_column(Integer, nullable=True)  # dagli eventi della gara


class AnalystInjury(Base, TimestampMixin):
    __tablename__ = "analyst_injuries"
    __table_args__ = (
        UniqueConstraint("provider_fixture_id", "provider_team_id", "player_id", name="uq_analyst_injuries_fixture_player"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    provider_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(60), nullable=True)  # Missing Fixture / Questionable
    reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
