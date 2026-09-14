"""Collegamento dati notturno API-Football per V2, V2.5 (e in futuro V3).

Dopo la scansione di Cecchino Today, per i campionati delle partite scansionate:
1. copertura dei campionati (leagues?current=true, 1 chiamata al giorno);
2. stagione precedente (squadre + partite finite, 2 chiamate una sola volta per campionato);
3. statistiche di squadra, arbitro e risultato delle partite finite ancora senza statistiche,
   a blocchi da 20 (fixtures?ids=...), solo nei campionati che le forniscono. Nello stesso blocco
   entrano le partite del registro live gia' giocate, per chiudere gli esiti.

Nessun tetto fisso: prima di ogni blocco si legge il contatore ufficiale di API-Football
(`status`, non consuma chiamate) e ci si ferma solo vicino al limite giornaliero, lasciando
margine agli altri usi del tool.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import FINISHED_STATUSES
from app.models import Competition, Fixture, FixtureTeamStat, League, Season
from app.models.api_football_data import ApiFootballFixtureFetch, ApiFootballLeagueCoverage
from app.models.cecchino_live_prediction import LIVE_STATUS_OPEN, CecchinoLivePrediction
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.api_football_client import ApiFootballClient
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)

BATCH_SIZE = 20
DAILY_LIMIT = 7500
# margine lasciato agli altri usi del tool (pulsanti, aggiornamento risultati, scansioni)
SAFETY_MARGIN = 300
COVERAGE_MAX_AGE = timedelta(hours=20)
# una partita gia' richiesta senza statistiche si riprova solo dopo questo intervallo
REFETCH_AFTER = timedelta(days=3)
MAX_FIXTURES_PER_RUN = 12000


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Budget:
    """Contatore ufficiale API-Football letto prima di ogni blocco, piu' le chiamate fatte qui:
    il contatore ufficiale si aggiorna con ritardo, quindi vale il piu' alto dei due."""

    def __init__(self, client: ApiFootballClient) -> None:
        self.client = client
        self.used: int | None = None
        self.limit: int = DAILY_LIMIT
        self.start: int | None = None
        self.own_calls = 0

    def refresh(self) -> None:
        try:
            requests = (self.client.get("status").get("response") or {}).get("requests") or {}
            official = int(requests.get("current") or 0)
            if self.start is None:
                self.start = official
            self.used = max(official, self.start + self.own_calls)
            self.limit = int(requests.get("limit_day") or DAILY_LIMIT)
        except Exception:  # noqa: BLE001 - senza contatore si procede con prudenza
            logger.warning("data_connector: status API-Football non leggibile", exc_info=True)

    def spent(self, calls: int = 1) -> None:
        self.own_calls += calls
        if self.used is not None:
            self.used += calls

    def can_spend(self, calls: int = 1) -> bool:
        if self.used is None:
            return True
        return self.used + calls <= self.limit - SAFETY_MARGIN


# --- 1. copertura ----------------------------------------------------------------------------


def refresh_coverage(db: Session, client: ApiFootballClient, budget: Budget) -> dict[str, Any]:
    latest = db.scalar(select(func.max(ApiFootballLeagueCoverage.checked_at)))
    if latest is not None and _now() - latest < COVERAGE_MAX_AGE:
        return {"status": "fresh", "checked_at": latest.isoformat()}
    if not budget.can_spend():
        return {"status": "skipped_budget"}
    items = client.get("leagues", {"current": "true"}).get("response") or []
    budget.spent(1)
    now = _now()
    n = 0
    for item in items:
        league = item.get("league") or {}
        season = next((s for s in item.get("seasons") or [] if s.get("current")), None)
        if not league.get("id") or not season:
            continue
        cov = season.get("coverage") or {}
        fx = cov.get("fixtures") or {}
        row = db.scalar(
            select(ApiFootballLeagueCoverage).where(
                ApiFootballLeagueCoverage.provider_league_id == int(league["id"]),
                ApiFootballLeagueCoverage.season == int(season["year"]),
            )
        )
        if row is None:
            row = ApiFootballLeagueCoverage(provider_league_id=int(league["id"]), season=int(season["year"]))
            db.add(row)
        row.league_name = league.get("name")
        row.country = (item.get("country") or {}).get("name")
        row.league_type = league.get("type")
        row.statistics_fixtures = bool(fx.get("statistics_fixtures"))
        row.lineups = bool(fx.get("lineups"))
        row.events = bool(fx.get("events"))
        row.odds = bool(cov.get("odds"))
        row.injuries = bool(cov.get("injuries"))
        row.raw_json = {"coverage": cov, "season": {k: season.get(k) for k in ("year", "start", "end")}}
        row.checked_at = now
        n += 1
    db.commit()
    return {"status": "refreshed", "leagues": n}


def stats_covered(db: Session, provider_league_id: int, season: int) -> bool:
    row = db.scalar(
        select(ApiFootballLeagueCoverage).where(
            ApiFootballLeagueCoverage.provider_league_id == int(provider_league_id),
            ApiFootballLeagueCoverage.season == int(season),
        )
    )
    return bool(row and row.statistics_fixtures)


# --- 2. stagione precedente ------------------------------------------------------------------


def ensure_previous_season(
    db: Session, client: ApiFootballClient, budget: Budget, comp: Competition
) -> str:
    prev_year = int(comp.season) - 1
    prev = db.scalar(
        select(Competition).where(
            Competition.provider_league_id == comp.provider_league_id, Competition.season == prev_year
        )
    )
    if prev is not None and db.scalar(
        select(func.count(Fixture.id)).where(Fixture.competition_id == prev.id, Fixture.status.in_(FINISHED_STATUSES))
    ):
        return "present"
    if not budget.can_spend(2):
        return "skipped_budget"
    from app.services.cecchino.league_ingest_helpers import (
        get_or_create_competition_for_league_season,
        get_or_create_season,
        safe_upsert_team_from_api_item,
    )

    league = db.scalar(select(League).where(League.api_league_id == int(comp.provider_league_id)))
    if league is None:
        return "league_missing"
    ingest = IngestionService(client=client)
    season_row = get_or_create_season(db, league_id=int(league.id), year=prev_year, label=str(prev_year), raw_json={"year": prev_year})
    prev_comp, _ = get_or_create_competition_for_league_season(
        db,
        provider_league_id=int(comp.provider_league_id),
        season=prev_year,
        league_id=int(league.id),
        season_id=int(season_row.id),
        league_meta={"id": comp.provider_league_id, "name": comp.name, "country": comp.country, "season": prev_year},
        league_name=comp.name,
        league_country=comp.country,
    )
    budget.spent(2)
    for t in client.get_teams(int(comp.provider_league_id), prev_year):
        safe_upsert_team_from_api_item(db, ingest, t)
    n = 0
    for item in client.get_fixtures(int(comp.provider_league_id), prev_year, status="FT"):
        if ingest._upsert_fixture_from_api_item(db, league, season_row, item, competition_id=int(prev_comp.id)):
            n += 1
    db.commit()
    return f"imported:{n}"


# --- 3. statistiche a blocchi ----------------------------------------------------------------


def _fixtures_missing_stats(db: Session, competition_ids: Iterable[int], limit: int) -> list[Fixture]:
    ids = list(competition_ids)
    if not ids:
        return []
    with_stats = (
        select(FixtureTeamStat.fixture_id)
        .group_by(FixtureTeamStat.fixture_id)
        .having(func.count(FixtureTeamStat.id) >= 2)
    )
    recently_fetched = select(ApiFootballFixtureFetch.api_fixture_id).where(
        ApiFootballFixtureFetch.fetched_at > _now() - REFETCH_AFTER
    )
    return list(
        db.scalars(
            select(Fixture)
            .where(
                Fixture.competition_id.in_(ids),
                Fixture.status.in_(FINISHED_STATUSES),
                Fixture.id.not_in(with_stats),
                Fixture.api_fixture_id.not_in(recently_fetched),
            )
            .order_by(Fixture.kickoff_at.desc())
            .limit(limit)
        ).all()
    )


def _registry_fixtures_to_close(db: Session) -> list[Fixture]:
    """Partite del registro live iniziate da piu' di 2 ore e ancora aperte."""
    local_ids = db.scalars(
        select(CecchinoLivePrediction.local_fixture_id).where(
            CecchinoLivePrediction.status == LIVE_STATUS_OPEN,
            CecchinoLivePrediction.kickoff < _now() - timedelta(hours=2),
            CecchinoLivePrediction.local_fixture_id.is_not(None),
        )
    ).all()
    if not local_ids:
        return []
    return list(db.scalars(select(Fixture).where(Fixture.id.in_(set(local_ids)))).all())


def fetch_fixture_batches(
    db: Session, client: ApiFootballClient, budget: Budget, fixtures: list[Fixture]
) -> dict[str, int]:
    from app.services.cecchino.cecchino_current_season_xg import _persist_fixture_statistics

    ingest = IngestionService(client=client)
    by_api = {int(f.api_fixture_id): f for f in fixtures}
    api_ids = list(by_api)
    counts = {"calls": 0, "fixtures": 0, "with_stats": 0, "results_updated": 0}
    for start in range(0, len(api_ids), BATCH_SIZE):
        if start % (BATCH_SIZE * 10) == 0:
            budget.refresh()
        if not budget.can_spend():
            counts["stopped_budget"] = 1
            break
        chunk = api_ids[start : start + BATCH_SIZE]
        items = client.get("fixtures", {"ids": "-".join(str(i) for i in chunk)}).get("response") or []
        counts["calls"] += 1
        budget.spent(1)
        now = _now()
        for item in items:
            api_id = int(((item.get("fixture") or {}).get("id")) or 0)
            fx = by_api.get(api_id)
            if fx is None:
                continue
            status = str(((item.get("fixture") or {}).get("status") or {}).get("short") or "")
            league = db.get(League, int(fx.league_id))
            season_row = db.get(Season, int(fx.season_id))
            if league is not None and season_row is not None:
                was_finished = fx.status in FINISHED_STATUSES
                if ingest._upsert_fixture_from_api_item(db, league, season_row, item, competition_id=fx.competition_id):
                    if not was_finished and status in FINISHED_STATUSES:
                        counts["results_updated"] += 1
            stats = item.get("statistics") or []
            types = {s.get("type") for block in stats for s in (block.get("statistics") or []) if s.get("value") is not None}
            if stats and types:
                _persist_fixture_statistics(db, fx, stats)
                counts["with_stats"] += 1
            row = db.get(ApiFootballFixtureFetch, api_id) or ApiFootballFixtureFetch(api_fixture_id=api_id)
            row.fetched_at = now
            row.fixture_status = status[:16]
            row.stats_teams = len(stats)
            row.stat_types = len(types)
            row.lineups_teams = len(item.get("lineups") or [])
            db.merge(row)
            counts["fixtures"] += 1
        db.commit()
    return counts


# --- orchestrazione --------------------------------------------------------------------------


def run_data_connector(db: Session, *, scan_date, client: ApiFootballClient | None = None) -> dict[str, Any]:
    client = client or ApiFootballClient()
    budget = Budget(client)
    budget.refresh()
    out: dict[str, Any] = {"budget_start": budget.used}
    out["coverage"] = refresh_coverage(db, client, budget)

    comp_ids = set(
        db.scalars(
            select(Fixture.competition_id)
            .join(CecchinoTodayFixture, CecchinoTodayFixture.local_fixture_id == Fixture.id)
            .where(CecchinoTodayFixture.scan_date == scan_date, Fixture.competition_id.is_not(None))
        ).all()
    )
    competitions = list(db.scalars(select(Competition).where(Competition.id.in_(comp_ids))).all()) if comp_ids else []

    previous: dict[str, int] = {}
    for comp in competitions:
        try:
            state = ensure_previous_season(db, client, budget, comp)
        except Exception:  # noqa: BLE001 - un campionato non ferma gli altri
            logger.exception("data_connector: stagione precedente fallita comp=%s", comp.id)
            db.rollback()
            state = "error"
        key = state.split(":")[0]
        previous[key] = previous.get(key, 0) + 1
    out["previous_season"] = previous

    covered = [c.id for c in competitions if stats_covered(db, int(c.provider_league_id), int(c.season))]
    out["competitions"] = {"scanned": len(competitions), "with_statistics": len(covered)}
    targets = _registry_fixtures_to_close(db)
    target_ids = {int(f.id) for f in targets}
    targets += [f for f in _fixtures_missing_stats(db, covered, MAX_FIXTURES_PER_RUN) if int(f.id) not in target_ids]
    out["fixtures_requested"] = len(targets)
    out["batches"] = fetch_fixture_batches(db, client, budget, targets)
    budget.refresh()
    out["budget_end"] = budget.used
    out["calls_made"] = budget.own_calls
    return out
