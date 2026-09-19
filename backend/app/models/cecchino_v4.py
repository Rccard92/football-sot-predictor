"""Tabelle Cecchino V4 (prefisso cecchino_v4_). Solo additive, nessun legame con tabelle di altri modelli.

JSON portabile: JSONB su PostgreSQL, JSON su SQLite (test).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins import TimestampMixin

PortableJSON = JSON().with_variant(JSONB(), "postgresql")
# SQLite autoincrementa solo INTEGER PRIMARY KEY: BigInteger su PostgreSQL, Integer nei test locali.
PkInteger = BigInteger().with_variant(Integer(), "sqlite")


class CecchinoV4Fixture(Base, TimestampMixin):
    __tablename__ = "cecchino_v4_fixtures"
    __table_args__ = (
        UniqueConstraint("api_fixture_id", name="uq_cecchino_v4_fixtures_api_fixture_id"),
        Index("ix_cecchino_v4_fixtures_kickoff_at", "kickoff_at"),
        Index("ix_cecchino_v4_fixtures_league_day", "league_code", "match_date"),
    )

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    api_fixture_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    league_code: Mapped[str] = mapped_column(String(8), nullable=False)
    api_league_id: Mapped[int] = mapped_column(Integer, nullable=False)
    competition: Mapped[str] = mapped_column(String(64), nullable=False)
    season_label: Mapped[str] = mapped_column(String(9), nullable=False)
    round: Mapped[str | None] = mapped_column(String(64), nullable=True)
    match_date: Mapped[date] = mapped_column(Date, nullable=False)  # data locale Europe/Rome
    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="NS")
    home_team_api_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    away_team_api_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    home_team: Mapped[str] = mapped_column(String(128), nullable=False)
    away_team: Mapped[str] = mapped_column(String(128), nullable=False)
    home_team_history: Mapped[str | None] = mapped_column(String(128), nullable=True)  # nome football-data
    away_team_history: Mapped[str | None] = mapped_column(String(128), nullable=True)
    referee: Mapped[str | None] = mapped_column(String(128), nullable=True)
    venue_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ft_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ft_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_home: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ht_away: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # statistiche post-partita normalizzate: {"home": {"shots":..,"sot":..,"corners":..,"yellow":..,"red":..,"fouls":..,
    #   "shots_inside":..,"shots_outside":..,"blocked":..,"saves":..,"possession":..,"xg":..}, "away": {...}}
    stats_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    stats_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # eventi normalizzati: [{"minute": 23, "type": "goal|card|subst", "team": "home|away", "player": "...", "detail": "..."}]
    events_json: Mapped[list[dict[str, Any]] | None] = mapped_column(PortableJSON, nullable=True)
    lineups_status: Mapped[str] = mapped_column(String(16), nullable=False, default="non_note")
    # {"home": {"formation": "4-3-3", "starters": [{"id":..,"name":..,"pos":..}], "bench": [...]}, "away": {...}, "fetched_at": "..."}
    lineups_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)


class CecchinoV4TeamMap(Base, TimestampMixin):
    __tablename__ = "cecchino_v4_team_map"
    __table_args__ = (UniqueConstraint("league_code", "api_team_id", name="uq_cecchino_v4_team_map_league_team"),)

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    league_code: Mapped[str] = mapped_column(String(8), nullable=False)
    api_team_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    api_team_name: Mapped[str] = mapped_column(String(128), nullable=False)
    history_team_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CecchinoV4OddsSnapshot(Base):
    __tablename__ = "cecchino_v4_odds_snapshots"
    __table_args__ = (
        Index("ix_cecchino_v4_odds_fixture_taken", "fixture_id", "taken_at"),
        Index("ix_cecchino_v4_odds_taken_at", "taken_at"),
    )

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False)
    bookmaker_id: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # mattina|pomeriggio|sera|chiusura
    taken_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    markets_json: Mapped[dict[str, float]] = mapped_column(PortableJSON, nullable=False)  # {market_key: quota}
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CecchinoV4LeagueDay(Base, TimestampMixin):
    """Contesto di campionato per giorno: classifica e infortuni."""

    __tablename__ = "cecchino_v4_league_days"
    __table_args__ = (UniqueConstraint("league_code", "day", name="uq_cecchino_v4_league_days"),)

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    league_code: Mapped[str] = mapped_column(String(8), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    standings_json: Mapped[list[dict[str, Any]] | None] = mapped_column(PortableJSON, nullable=True)
    injuries_json: Mapped[list[dict[str, Any]] | None] = mapped_column(PortableJSON, nullable=True)


class CecchinoV4PlayerMinutes(Base):
    __tablename__ = "cecchino_v4_player_minutes"
    __table_args__ = (
        UniqueConstraint("fixture_id", "player_api_id", name="uq_cecchino_v4_player_minutes"),
        Index("ix_cecchino_v4_player_minutes_team", "team_api_id"),
    )

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False)
    team_api_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_api_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_name: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[str | None] = mapped_column(String(4), nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)


class CecchinoV4Run(Base):
    """Calcolo storico o live: gol, statistiche, selezione."""

    __tablename__ = "cecchino_v4_runs"

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # goals|stats|selection|live
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    config_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CecchinoV4Prediction(Base):
    __tablename__ = "cecchino_v4_predictions"
    __table_args__ = (
        Index("ix_cecchino_v4_predictions_fixture_kind", "fixture_id", "kind"),
        Index("ix_cecchino_v4_predictions_run", "run_id"),
    )

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cecchino_v4_runs.id", ondelete="SET NULL"), nullable=True)
    fixture_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=True)
    history_match_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # id del CSV storico
    kind: Mapped[str] = mapped_column(String(8), nullable=False)  # goals|stats
    payload_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # stato formazioni al momento del calcolo: la previsione si rifa' quando cambiano
    lineups_status: Mapped[str] = mapped_column(String(16), nullable=False, default="non_note")


class CecchinoV4Explanation(Base):
    __tablename__ = "cecchino_v4_explanations"
    __table_args__ = (UniqueConstraint("fixture_id", name="uq_cecchino_v4_explanations_fixture"),)

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    fixture_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)  # i 6 blocchi
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CecchinoV4Shortlist(Base):
    __tablename__ = "cecchino_v4_shortlists"
    __table_args__ = (UniqueConstraint("day", name="uq_cecchino_v4_shortlists_day"),)

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="provvisoria")
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    digest: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sha256 del contenuto sigillato
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CecchinoV4ShortlistItem(Base):
    __tablename__ = "cecchino_v4_shortlist_items"
    __table_args__ = (
        Index("ix_cecchino_v4_shortlist_items_shortlist", "shortlist_id"),
        Index("ix_cecchino_v4_shortlist_items_fixture", "fixture_id"),
    )

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    shortlist_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cecchino_v4_shortlists.id", ondelete="CASCADE"), nullable=False)
    fixture_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("cecchino_v4_fixtures.id", ondelete="CASCADE"), nullable=False)
    market_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    probability: Mapped[float] = mapped_column(Float, nullable=False)
    prob_low: Mapped[float] = mapped_column(Float, nullable=False)
    prob_high: Mapped[float] = mapped_column(Float, nullable=False)
    prob_prudent: Mapped[float] = mapped_column(Float, nullable=False)
    quota: Mapped[float] = mapped_column(Float, nullable=False)
    bookmaker_id: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_profit: Mapped[float] = mapped_column(Float, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="provvisoria")
    withdraw_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)  # frasi del perche'
    closing_quota: Mapped[float | None] = mapped_column(Float, nullable=True)
    clv: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)  # vinta|persa|void
    profit_units: Mapped[float | None] = mapped_column(Float, nullable=True)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CecchinoV4Exam(Base):
    __tablename__ = "cecchino_v4_exams"

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False)  # E1, E2_sot, E4, G6_classici...
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    preregistration_path: Mapped[str] = mapped_column(String(200), nullable=False)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    result_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CecchinoV4Challenger(Base):
    __tablename__ = "cecchino_v4_challengers"

    id: Mapped[int] = mapped_column(PkInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="candidato")  # candidato|superato|non_superato
    exam_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CecchinoV4Job(Base):
    """Job V4 con heartbeat; un solo job dello stesso nome alla volta."""

    __tablename__ = "cecchino_v4_jobs"
    __table_args__ = (Index("ix_cecchino_v4_jobs_name_created", "name", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")  # running|done|failed|stale
    params_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    step: Mapped[str | None] = mapped_column(String(160), nullable=True)
    api_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


V4_TABLES = (
    CecchinoV4Fixture.__table__,
    CecchinoV4TeamMap.__table__,
    CecchinoV4OddsSnapshot.__table__,
    CecchinoV4LeagueDay.__table__,
    CecchinoV4PlayerMinutes.__table__,
    CecchinoV4Run.__table__,
    CecchinoV4Prediction.__table__,
    CecchinoV4Explanation.__table__,
    CecchinoV4Shortlist.__table__,
    CecchinoV4ShortlistItem.__table__,
    CecchinoV4Exam.__table__,
    CecchinoV4Challenger.__table__,
    CecchinoV4Job.__table__,
)
