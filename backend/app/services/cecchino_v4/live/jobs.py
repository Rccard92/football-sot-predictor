"""Job della pipeline live V4 (docs/v4/ROADMAP.md, Fase 0 e Fase 3; docs/v4/API.md, job admin).

Ogni job: una riga `cecchino_v4_jobs` (uuid, heartbeat, contatore chiamate, risultato), un solo job
dello stesso nome in esecuzione, job senza heartbeat da 30 minuti marcati `stale`. Il budget e' del
client (`V4ApiClient.ensure_budget`): `BudgetGuardStop` e quota esaurita chiudono il job in `failed`
con il messaggio, lasciando in tabella quanto gia' salvato (i job sono ripristinabili).

Persistenza qui, calcolo puro in `normalize.py`. Le quote finiscono solo nel registro.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import JSON, func, or_, select
from sqlalchemy.orm import Session

from app.services.api_football_client import ApiFootballError, ApiFootballQuotaExhausted
from app.services.api_usage_context import BudgetGuardStop
from app.models.cecchino_v4 import (
    CecchinoV4Fixture,
    CecchinoV4Job,
    CecchinoV4LeagueDay,
    CecchinoV4OddsSnapshot,
    CecchinoV4PlayerMinutes,
    CecchinoV4TeamMap,
)
from app.services.cecchino_v4 import settings as v4_settings
from app.services.cecchino_v4.constants import (
    BOOKMAKER_BET365_ID,
    BOOKMAKER_BETFAIR_ID,
    BOOKMAKERS,
    CLOSING_MINUTES_BEFORE_KICKOFF,
    FIXTURE_HORIZON_DAYS,
    LEAGUE_BY_CODE,
    LEAGUES,
)
from app.services.cecchino_v4.history.team_mapping import map_team_detail
from app.services.cecchino_v4.live.client import V4ApiClient, api_calls_today
from app.services.cecchino_v4.live.normalize import (
    COVERAGE_FAMILIES,
    FINAL_STATUSES,
    LINEUPS_OFFICIAL,
    ROME_TZ,
    api_season_for,
    market_family,
    normalize_events,
    normalize_fixture,
    normalize_injuries,
    normalize_lineups,
    normalize_odds_item,
    normalize_players,
    normalize_standings,
    normalize_statistics,
    odds_item_fixture_id,
    rome_date,
    snapshot_kind_for,
)

logger = logging.getLogger(__name__)

STALE_MINUTES = 30
HEARTBEAT_EVERY_ITEMS = 5
POST_MATCH_DELAY = timedelta(hours=2)
POST_MATCH_REFRESH_DAYS = 3
LINEUPS_WINDOW = timedelta(minutes=65)
CLOSING_WINDOW = timedelta(minutes=CLOSING_MINUTES_BEFORE_KICKOFF + 5)
SNAPSHOT_REPEAT_GAP = timedelta(hours=3)
ODDS_SNAPSHOT_DAYS = 3  # oggi, domani, dopodomani
COVERAGE_DAYS = 7
TEAM_MAP_MIN_CONFIDENCE = 0.80

JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_FAILED = "failed"
JOB_STALE = "stale"

FIXTURE_UPDATABLE_FIELDS = (
    "league_code", "api_league_id", "competition", "season_label", "round", "match_date", "kickoff_at",
    "status", "home_team_api_id", "away_team_api_id", "home_team", "away_team", "referee", "venue_city",
)


class JobAlreadyRunning(Exception):
    """Esiste gia' un job con lo stesso nome in esecuzione."""


class UnknownJob(Exception):
    """Nome di job non previsto."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_missing(column):
    """Colonna JSON vuota: SQL NULL oppure JSON `null` (SQLAlchemy salva Python None come 'null')."""
    return or_(column.is_(None), column == JSON.NULL)


def _aware(dt: datetime | None) -> datetime | None:
    """SQLite restituisce datetime senza fuso: li trattiamo come UTC."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# --- contesto di esecuzione -----------------------------------------------------------------------------
@dataclass
class JobContext:
    db: Session
    job: CecchinoV4Job
    client: V4ApiClient
    now: datetime
    params: dict[str, Any]
    history_names: dict[str, set[str]] | None = None
    clock: Callable[[], datetime] = field(default=_utcnow)
    _items: int = 0

    @property
    def today(self) -> date:
        return rome_date(self.now)

    def season(self, day: date | None = None) -> int:
        if self.params.get("season") is not None:
            return int(self.params["season"])
        return api_season_for(day or self.today)

    def heartbeat(self, step: str | None = None, progress: float | None = None, *, force: bool = False) -> None:
        self._items += 1
        if not force and self._items % HEARTBEAT_EVERY_ITEMS != 0:
            return
        self.job.heartbeat_at = self.clock()
        if step is not None:
            self.job.step = str(step)[:160]
        if progress is not None:
            self.job.progress_pct = float(max(0.0, min(100.0, progress)))
        self.job.api_calls = int(self.client.calls)
        self.db.commit()

    def names_for(self, league_code: str) -> set[str]:
        if self.history_names is None:
            from app.services.cecchino_v4.history.team_mapping import load_history_team_names

            self.history_names = load_history_team_names(include_lockbox=True)
        return self.history_names.get(league_code, set())


# --- job: gestione righe ---------------------------------------------------------------------------------
def mark_stale_jobs(db: Session, *, now: datetime | None = None, stale_minutes: int = STALE_MINUTES) -> int:
    """Job `running` senza heartbeat da `stale_minutes` -> `stale`. Ritorna quanti."""
    ref = now or _utcnow()
    cutoff = ref - timedelta(minutes=stale_minutes)
    rows = list(db.scalars(select(CecchinoV4Job).where(CecchinoV4Job.status == JOB_RUNNING, CecchinoV4Job.heartbeat_at < cutoff)).all())
    for row in rows:
        row.status = JOB_STALE
        row.finished_at = ref
        row.error_message = f"Nessun heartbeat da oltre {stale_minutes} minuti: job considerato fermo."
    if rows:
        db.commit()
    return len(rows)


def running_job(db: Session, name: str) -> CecchinoV4Job | None:
    return db.scalars(select(CecchinoV4Job).where(CecchinoV4Job.name == name, CecchinoV4Job.status == JOB_RUNNING).limit(1)).first()


def recent_jobs(db: Session, *, limit: int = 30) -> list[dict[str, Any]]:
    rows = db.scalars(select(CecchinoV4Job).order_by(CecchinoV4Job.created_at.desc()).limit(int(limit))).all()
    return [job_to_dict(r) for r in rows]


def job_to_dict(job: CecchinoV4Job) -> dict[str, Any]:
    def iso(dt: datetime | None) -> str | None:
        a = _aware(dt)
        return a.isoformat() if a else None

    return {
        "job_id": job.id,
        "name": job.name,
        "status": job.status,
        "params": job.params_json or {},
        "progress_pct": float(job.progress_pct or 0.0),
        "step": job.step,
        "api_calls": int(job.api_calls or 0),
        "result": job.result_json,
        "error_message": job.error_message,
        "heartbeat_at": iso(job.heartbeat_at),
        "created_at": iso(job.created_at),
        "finished_at": iso(job.finished_at),
    }


def run_job(
    db: Session,
    name: str,
    *,
    client: V4ApiClient,
    params: dict[str, Any] | None = None,
    now: datetime | None = None,
    history_names: dict[str, set[str]] | None = None,
) -> CecchinoV4Job:
    """Esegue il job `name` e ritorna la riga `CecchinoV4Job` aggiornata (status done|failed)."""
    if name not in JOBS:
        raise UnknownJob(f"Job sconosciuto: {name}. Disponibili: {', '.join(JOBS)}")
    clock: Callable[[], datetime] = (lambda: now) if now is not None else _utcnow
    started = clock()
    mark_stale_jobs(db, now=started)
    if running_job(db, name) is not None:
        raise JobAlreadyRunning(f"Job '{name}' gia' in esecuzione.")

    job = CecchinoV4Job(
        id=str(uuid.uuid4()),
        name=name,
        status=JOB_RUNNING,
        params_json=dict(params or {}) or None,
        progress_pct=0.0,
        step="avvio",
        api_calls=0,
        heartbeat_at=started,
        created_at=started,
    )
    db.add(job)
    db.commit()

    ctx = JobContext(db=db, job=job, client=client, now=started, params=dict(params or {}), history_names=history_names, clock=clock)
    client.bind(db, job_id=job.id, scan_date=ctx.today)
    try:
        client.ensure_budget(db)
        result = JOBS[name](ctx)
        job.status = JOB_DONE
        job.result_json = result
        job.progress_pct = 100.0
        job.step = "completato"
    except BudgetGuardStop as exc:
        db.rollback()
        job.status = JOB_FAILED
        job.error_message = f"Arresto budget: {exc.message}"
        job.result_json = {"budget": exc.details}
        logger.warning("V4 job %s fermato dal budget: %s", name, exc.message)
    except ApiFootballQuotaExhausted as exc:
        db.rollback()
        job.status = JOB_FAILED
        job.error_message = f"Quota API-Football esaurita: {exc}"
        logger.warning("V4 job %s: quota esaurita", name)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job.status = JOB_FAILED
        job.error_message = f"{type(exc).__name__}: {exc}"[:2000]
        logger.exception("V4 job %s fallito", name)
    finally:
        job.api_calls = int(client.calls)
        job.heartbeat_at = clock()
        job.finished_at = clock()
        db.add(job)
        db.commit()
    return job


# --- persistenza fixture e mappa squadre ---------------------------------------------------------------------
def _map_team(ctx: JobContext, league_code: str, api_team_id: int, api_name: str) -> str | None:
    row = ctx.db.scalars(
        select(CecchinoV4TeamMap).where(CecchinoV4TeamMap.league_code == league_code, CecchinoV4TeamMap.api_team_id == int(api_team_id)).limit(1)
    ).first()
    if row is not None:
        if row.verified or row.confidence >= TEAM_MAP_MIN_CONFIDENCE:
            return row.history_team_name
        return None
    detail = map_team_detail(league_code, api_name, ctx.names_for(league_code))
    row = CecchinoV4TeamMap(
        league_code=league_code,
        api_team_id=int(api_team_id),
        api_team_name=str(api_name)[:128],
        history_team_name=detail.history_name,
        confidence=float(detail.confidence),
        verified=False,
    )
    ctx.db.add(row)
    ctx.db.flush()
    return detail.history_name if detail.confidence >= TEAM_MAP_MIN_CONFIDENCE else None


def upsert_fixture(ctx: JobContext, fields: dict[str, Any]) -> tuple[CecchinoV4Fixture, bool]:
    """Inserisce o aggiorna per `api_fixture_id`; non tocca statistiche, eventi e formazioni gia' salvate."""
    fx = ctx.db.scalars(select(CecchinoV4Fixture).where(CecchinoV4Fixture.api_fixture_id == fields["api_fixture_id"]).limit(1)).first()
    created = fx is None
    if created:
        fx = CecchinoV4Fixture(api_fixture_id=fields["api_fixture_id"])
        ctx.db.add(fx)
    for key in FIXTURE_UPDATABLE_FIELDS:
        setattr(fx, key, fields[key])
    for key in ("ft_home", "ft_away", "ht_home", "ht_away"):
        if fields.get(key) is not None:
            setattr(fx, key, fields[key])
    fx.home_team_history = _map_team(ctx, fields["league_code"], fields["home_team_api_id"], fields["home_team"])
    fx.away_team_history = _map_team(ctx, fields["league_code"], fields["away_team_api_id"], fields["away_team"])
    ctx.db.flush()
    return fx, created


def _upsert_fixture_items(ctx: JobContext, items: list[dict[str, Any]]) -> dict[str, int]:
    seen = created = 0
    for item in items:
        fields = normalize_fixture(item)
        if fields is None:
            continue
        seen += 1
        _, was_created = upsert_fixture(ctx, fields)
        created += int(was_created)
    return {"seen": seen, "created": created}


def _unmapped_teams(db: Session) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(CecchinoV4TeamMap).where(CecchinoV4TeamMap.verified.is_(False), CecchinoV4TeamMap.confidence < TEAM_MAP_MIN_CONFIDENCE)
    ).all()
    return [
        {"league_code": r.league_code, "api_team_id": r.api_team_id, "api_team_name": r.api_team_name, "candidate": r.history_team_name, "confidence": round(float(r.confidence), 3)}
        for r in rows
    ]


# --- job: fixture -----------------------------------------------------------------------------------------------
def job_fixtures(ctx: JobContext) -> dict[str, Any]:
    """Partite dei 16 campionati da oggi a oggi + FIXTURE_HORIZON_DAYS: una chiamata per data."""
    start = _param_date(ctx.params.get("date")) or ctx.today
    horizon = int(ctx.params.get("days", FIXTURE_HORIZON_DAYS))
    days = [start + timedelta(days=i) for i in range(horizon + 1)]
    seen = created = 0
    for i, day in enumerate(days):
        items = ctx.client.fixtures_by_date(day)
        counts = _upsert_fixture_items(ctx, items)
        seen += counts["seen"]
        created += counts["created"]
        ctx.db.commit()
        ctx.heartbeat(f"fixture {day.isoformat()}", (i + 1) / len(days) * 100.0, force=True)
    return {"dates": [d.isoformat() for d in days], "fixtures_seen": seen, "created": created, "updated": seen - created, "unmapped_teams": _unmapped_teams(ctx.db)}


def _param_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, date):
        return raw
    return date.fromisoformat(str(raw))


# --- job: post partita -------------------------------------------------------------------------------------------
def process_post_match(ctx: JobContext, fx: CecchinoV4Fixture, *, with_lineups: bool = False) -> dict[str, bool]:
    """Statistiche, eventi, minuti giocatori (ed eventualmente formazioni) di una partita finita. Commit alla fine."""
    done = {"stats": False, "events": False, "players": False, "lineups": False, "score": False}
    fid = int(fx.api_fixture_id)
    home, away = int(fx.home_team_api_id), int(fx.away_team_api_id)

    if fx.ft_home is None or fx.ft_away is None:
        item = ctx.client.fixture_by_id(fid)
        fields = normalize_fixture(item) if item else None
        if fields:
            for key in ("status", "ft_home", "ft_away", "ht_home", "ht_away"):
                if fields.get(key) is not None:
                    setattr(fx, key, fields[key])
            done["score"] = True

    stats = normalize_statistics(ctx.client.fixture_statistics(fid), home, away)
    if stats is not None:
        fx.stats_json = stats
        fx.stats_fetched_at = ctx.clock()
        done["stats"] = True

    events = normalize_events(ctx.client.fixture_events(fid), home, away)
    if events:
        fx.events_json = events
        done["events"] = True

    players = normalize_players(ctx.client.fixture_players(fid))
    if players:
        for old in ctx.db.scalars(select(CecchinoV4PlayerMinutes).where(CecchinoV4PlayerMinutes.fixture_id == fx.id)).all():
            ctx.db.delete(old)
        ctx.db.flush()
        for p in players:
            ctx.db.add(CecchinoV4PlayerMinutes(fixture_id=fx.id, **p))
        done["players"] = True

    if with_lineups and fx.lineups_status != LINEUPS_OFFICIAL:
        lineups, status = normalize_lineups(ctx.client.fixture_lineups(fid), home, away, fetched_at=ctx.clock())
        if lineups is not None:
            fx.lineups_json = lineups
            fx.lineups_status = status
            done["lineups"] = status == LINEUPS_OFFICIAL

    ctx.db.commit()
    return done


def _refresh_unfinished(ctx: JobContext) -> int:
    """Partite in tabella non ancora finali ma con calcio d'inizio passato: una chiamata per data per aggiornare stato e risultato."""
    cutoff = ctx.now - POST_MATCH_DELAY
    floor = ctx.now - timedelta(days=POST_MATCH_REFRESH_DAYS)
    rows = ctx.db.scalars(
        select(CecchinoV4Fixture.match_date)
        .where(CecchinoV4Fixture.status.notin_(tuple(FINAL_STATUSES)), CecchinoV4Fixture.kickoff_at < cutoff, CecchinoV4Fixture.kickoff_at >= floor)
        .distinct()
    ).all()
    dates = sorted({d if isinstance(d, date) else date.fromisoformat(str(d)) for d in rows})
    for day in dates:
        _upsert_fixture_items(ctx, ctx.client.fixtures_by_date(day))
        ctx.db.commit()
    return len(dates)


def job_post_match(ctx: JobContext) -> dict[str, Any]:
    refreshed = _refresh_unfinished(ctx)
    cutoff = ctx.now - POST_MATCH_DELAY
    rows = list(
        ctx.db.scalars(
            select(CecchinoV4Fixture)
            .where(CecchinoV4Fixture.status.in_(tuple(FINAL_STATUSES)), _json_missing(CecchinoV4Fixture.stats_json), CecchinoV4Fixture.kickoff_at < cutoff)
            .order_by(CecchinoV4Fixture.kickoff_at)
        ).all()
    )
    limit = ctx.params.get("limit")
    if limit:
        rows = rows[: int(limit)]
    processed = with_stats = 0
    for i, fx in enumerate(rows):
        done = process_post_match(ctx, fx, with_lineups=bool(ctx.params.get("with_lineups", False)))
        processed += 1
        with_stats += int(done["stats"])
        ctx.heartbeat(f"post partita {fx.home_team} - {fx.away_team}", (i + 1) / len(rows) * 100.0)
    return {"dates_refreshed": refreshed, "fixtures_processed": processed, "with_stats": with_stats, "without_stats": processed - with_stats}


# --- job: formazioni ------------------------------------------------------------------------------------------------
def job_lineups(ctx: JobContext) -> dict[str, Any]:
    rows = list(
        ctx.db.scalars(
            select(CecchinoV4Fixture)
            .where(
                CecchinoV4Fixture.kickoff_at >= ctx.now,
                CecchinoV4Fixture.kickoff_at <= ctx.now + LINEUPS_WINDOW,
                CecchinoV4Fixture.lineups_status != LINEUPS_OFFICIAL,
                CecchinoV4Fixture.status.notin_(tuple(FINAL_STATUSES)),
            )
            .order_by(CecchinoV4Fixture.kickoff_at)
        ).all()
    )
    official = 0
    for i, fx in enumerate(rows):
        items = ctx.client.fixture_lineups(int(fx.api_fixture_id))
        lineups, status = normalize_lineups(items, int(fx.home_team_api_id), int(fx.away_team_api_id), fetched_at=ctx.clock())
        if lineups is not None:
            fx.lineups_json = lineups
            fx.lineups_status = status
            official += int(status == LINEUPS_OFFICIAL)
        ctx.db.commit()
        ctx.heartbeat(f"formazioni {fx.home_team} - {fx.away_team}", (i + 1) / len(rows) * 100.0)
    return {"fixtures_checked": len(rows), "official": official, "pending": len(rows) - official}


# --- job: infortuni e classifiche -------------------------------------------------------------------------------------
def _league_day(ctx: JobContext, league_code: str, day: date) -> CecchinoV4LeagueDay:
    row = ctx.db.scalars(select(CecchinoV4LeagueDay).where(CecchinoV4LeagueDay.league_code == league_code, CecchinoV4LeagueDay.day == day).limit(1)).first()
    if row is None:
        row = CecchinoV4LeagueDay(league_code=league_code, day=day)
        ctx.db.add(row)
    return row


def _selected_leagues(ctx: JobContext):
    code = ctx.params.get("league_code")
    if code:
        if code not in LEAGUE_BY_CODE:
            raise UnknownJob(f"Campionato sconosciuto: {code}")
        return (LEAGUE_BY_CODE[code],)
    return LEAGUES


def job_injuries(ctx: JobContext) -> dict[str, Any]:
    season = ctx.season()
    total = 0
    leagues = _selected_leagues(ctx)
    for i, lg in enumerate(leagues):
        items = normalize_injuries(ctx.client.injuries(lg.api_football_league_id, season))
        row = _league_day(ctx, lg.code, ctx.today)
        row.injuries_json = items
        total += len(items)
        ctx.db.commit()
        ctx.heartbeat(f"infortuni {lg.code}", (i + 1) / len(leagues) * 100.0)
    return {"day": ctx.today.isoformat(), "season": season, "leagues": len(leagues), "injuries": total}


def job_standings(ctx: JobContext) -> dict[str, Any]:
    season = ctx.season()
    total = 0
    leagues = _selected_leagues(ctx)
    for i, lg in enumerate(leagues):
        rows = normalize_standings(ctx.client.standings(lg.api_football_league_id, season))
        row = _league_day(ctx, lg.code, ctx.today)
        row.standings_json = rows
        total += len(rows)
        ctx.db.commit()
        ctx.heartbeat(f"classifica {lg.code}", (i + 1) / len(leagues) * 100.0)
    return {"day": ctx.today.isoformat(), "season": season, "leagues": len(leagues), "rows": total}


# --- job: registro quote ----------------------------------------------------------------------------------------------------
def _recent_snapshot_fixture_ids(db: Session, fixture_ids: list[int], bookmaker_id: int, kind: str, since: datetime) -> set[int]:
    if not fixture_ids:
        return set()
    rows = db.scalars(
        select(CecchinoV4OddsSnapshot.fixture_id).where(
            CecchinoV4OddsSnapshot.fixture_id.in_(fixture_ids),
            CecchinoV4OddsSnapshot.bookmaker_id == int(bookmaker_id),
            CecchinoV4OddsSnapshot.kind == kind,
            CecchinoV4OddsSnapshot.taken_at >= since,
        )
    ).all()
    return {int(r) for r in rows}


def _store_snapshot(ctx: JobContext, fixture_id: int, bookmaker_id: int, kind: str, markets: dict[str, float]) -> CecchinoV4OddsSnapshot | None:
    if not markets:
        return None
    row = CecchinoV4OddsSnapshot(fixture_id=int(fixture_id), bookmaker_id=int(bookmaker_id), kind=kind, taken_at=ctx.now, markets_json=dict(markets), created_at=ctx.clock())
    ctx.db.add(row)
    return row


def job_odds_snapshot(ctx: JobContext) -> dict[str, Any]:
    """Tre istantanee al giorno (mattina, pomeriggio, sera) per campionato, data e bookmaker."""
    kind = snapshot_kind_for(ctx.now)
    since = ctx.now - SNAPSHOT_REPEAT_GAP
    days = [ctx.today + timedelta(days=i) for i in range(int(ctx.params.get("days", ODDS_SNAPSHOT_DAYS)))]
    leagues = _selected_leagues(ctx)
    stored = skipped_calls = calls_done = 0
    unmapped: dict[str, int] = {}
    total_steps = len(leagues) * len(days) * len(BOOKMAKERS)
    step = 0
    for lg in leagues:
        for day in days:
            fixtures = list(
                ctx.db.scalars(
                    select(CecchinoV4Fixture).where(
                        CecchinoV4Fixture.league_code == lg.code, CecchinoV4Fixture.match_date == day, CecchinoV4Fixture.status.notin_(tuple(FINAL_STATUSES))
                    )
                ).all()
            )
            by_api_id = {int(f.api_fixture_id): f for f in fixtures}
            for bookmaker_id in BOOKMAKERS:
                step += 1
                if not fixtures:
                    skipped_calls += 1
                    continue
                recent = _recent_snapshot_fixture_ids(ctx.db, [f.id for f in fixtures], bookmaker_id, kind, since)
                if len(recent) >= len(fixtures):
                    skipped_calls += 1
                    continue
                items = ctx.client.odds_by_league_date(lg.api_football_league_id, ctx.season(day), day, bookmaker_id)
                calls_done += 1
                for item in items:
                    fx = by_api_id.get(odds_item_fixture_id(item) or -1)
                    if fx is None or fx.id in recent:
                        continue
                    norm = normalize_odds_item(item, bookmaker_ids={bookmaker_id}).get(bookmaker_id)
                    if norm is None:
                        continue
                    for name in norm.unmapped_bets:
                        unmapped[name] = unmapped.get(name, 0) + 1
                    if _store_snapshot(ctx, fx.id, bookmaker_id, kind, norm.markets) is not None:
                        stored += 1
                ctx.db.commit()
                ctx.heartbeat(f"quote {lg.code} {day.isoformat()} {BOOKMAKERS[bookmaker_id]}", step / total_steps * 100.0)
    return {"kind": kind, "days": [d.isoformat() for d in days], "snapshots_stored": stored, "league_date_calls": calls_done, "league_date_skipped": skipped_calls, "unmapped_bets": unmapped}


def job_odds_closing(ctx: JobContext) -> dict[str, Any]:
    """Quota di chiusura: una chiamata per partita nei CLOSING_MINUTES_BEFORE_KICKOFF (+5) minuti prima del calcio d'inizio."""
    rows = list(
        ctx.db.scalars(
            select(CecchinoV4Fixture)
            .where(CecchinoV4Fixture.kickoff_at >= ctx.now, CecchinoV4Fixture.kickoff_at <= ctx.now + CLOSING_WINDOW, CecchinoV4Fixture.status.notin_(tuple(FINAL_STATUSES)))
            .order_by(CecchinoV4Fixture.kickoff_at)
        ).all()
    )
    already = set(
        ctx.db.scalars(
            select(CecchinoV4OddsSnapshot.fixture_id).where(CecchinoV4OddsSnapshot.fixture_id.in_([f.id for f in rows] or [-1]), CecchinoV4OddsSnapshot.kind == "chiusura")
        ).all()
    )
    todo = [f for f in rows if f.id not in already]
    stored = 0
    for i, fx in enumerate(todo):
        items = ctx.client.odds_by_fixture(int(fx.api_fixture_id))
        for item in items:
            for bookmaker_id, norm in normalize_odds_item(item, bookmaker_ids=set(BOOKMAKERS)).items():
                if _store_snapshot(ctx, fx.id, bookmaker_id, "chiusura", norm.markets) is not None:
                    stored += 1
        ctx.db.commit()
        ctx.heartbeat(f"chiusura {fx.home_team} - {fx.away_team}", (i + 1) / len(todo) * 100.0)
    return {"fixtures_in_window": len(rows), "fixtures_fetched": len(todo), "snapshots_stored": stored}


# --- job: matrice copertura ----------------------------------------------------------------------------------------------------
def job_coverage_scan(ctx: JobContext) -> dict[str, Any]:
    """Una chiamata quote per partita dei prossimi 7 giorni: quali famiglie di mercato esistono per divisione e bookmaker."""
    rows = list(
        ctx.db.scalars(
            select(CecchinoV4Fixture)
            .where(
                CecchinoV4Fixture.kickoff_at >= ctx.now,
                CecchinoV4Fixture.kickoff_at <= ctx.now + timedelta(days=int(ctx.params.get("days", COVERAGE_DAYS))),
                CecchinoV4Fixture.status.notin_(tuple(FINAL_STATUSES)),
            )
            .order_by(CecchinoV4Fixture.kickoff_at)
        ).all()
    )
    if ctx.params.get("league_code"):
        rows = [f for f in rows if f.league_code == ctx.params["league_code"]]
    limit = ctx.params.get("limit")
    if limit:
        rows = rows[: int(limit)]

    wanted = {BOOKMAKER_BET365_ID, BOOKMAKER_BETFAIR_ID}
    kind = snapshot_kind_for(ctx.now)
    since = ctx.now - SNAPSHOT_REPEAT_GAP
    matrix: dict[str, dict[str, Any]] = {
        lg.code: {"league_code": lg.code, "competition": lg.competition, "fixtures_checked": 0, "fixtures_with_odds": 0, "markets": {f: False for f in COVERAGE_FAMILIES}, "by_bookmaker": {name: {f: False for f in COVERAGE_FAMILIES} for name in BOOKMAKERS.values()}}
        for lg in LEAGUES
    }
    unmapped: dict[str, dict[str, Any]] = {}
    stored = 0
    for i, fx in enumerate(rows):
        entry = matrix[fx.league_code]
        entry["fixtures_checked"] += 1
        items = ctx.client.odds_by_fixture(int(fx.api_fixture_id))
        had_odds = False
        for item in items:
            for bookmaker_id, norm in normalize_odds_item(item, bookmaker_ids=wanted).items():
                book_name = BOOKMAKERS[bookmaker_id]
                if norm.markets:
                    had_odds = True
                for key in norm.markets:
                    fam = market_family(key)
                    if fam in entry["markets"]:
                        entry["markets"][fam] = True
                        entry["by_bookmaker"][book_name][fam] = True
                for name in norm.unmapped_bets:
                    slot = unmapped.setdefault(name, {"bet_name": name, "count": 0, "bookmakers": [], "leagues": [], "example_fixture_id": int(fx.api_fixture_id)})
                    slot["count"] += 1
                    if book_name not in slot["bookmakers"]:
                        slot["bookmakers"].append(book_name)
                    if fx.league_code not in slot["leagues"]:
                        slot["leagues"].append(fx.league_code)
                # la chiamata non va sprecata: vale anche come istantanea del registro
                if norm.markets and fx.id not in _recent_snapshot_fixture_ids(ctx.db, [fx.id], bookmaker_id, kind, since):
                    if _store_snapshot(ctx, fx.id, bookmaker_id, kind, norm.markets) is not None:
                        stored += 1
        entry["fixtures_with_odds"] += int(had_odds)
        ctx.db.commit()
        ctx.heartbeat(f"copertura {fx.league_code} {fx.home_team} - {fx.away_team}", (i + 1) / len(rows) * 100.0)

    coverage = [matrix[lg.code] for lg in LEAGUES]
    unmapped_list = sorted(unmapped.values(), key=lambda u: (-u["count"], u["bet_name"]))
    return {"computed_at": ctx.now.isoformat(), "fixtures_checked": len(rows), "snapshots_stored": stored, "families": list(COVERAGE_FAMILIES), "coverage": coverage, "unmapped_bets": unmapped_list}


# --- job: backfill ------------------------------------------------------------------------------------------------------------------
def job_backfill(ctx: JobContext) -> dict[str, Any]:
    """Stagione intera di un campionato: una chiamata per le partite, poi post partita per ognuna senza statistiche (ripristinabile)."""
    code = ctx.params.get("league_code")
    season = ctx.params.get("season")
    if not code or code not in LEAGUE_BY_CODE or season is None:
        raise UnknownJob("backfill richiede params league_code (es. I1) e season (es. 2024)")
    lg = LEAGUE_BY_CODE[code]
    items = ctx.client.fixtures_by_league_season(lg.api_football_league_id, int(season))
    finals = [it for it in items if str(((it.get("fixture") or {}).get("status") or {}).get("short") or "") in FINAL_STATUSES]
    counts = _upsert_fixture_items(ctx, finals)
    ctx.db.commit()
    ctx.heartbeat(f"backfill {code} {season}: {counts['seen']} partite", 1.0, force=True)

    season_label = f"{int(season)}/{int(season) + 1}"
    todo = list(
        ctx.db.scalars(
            select(CecchinoV4Fixture)
            .where(CecchinoV4Fixture.league_code == code, CecchinoV4Fixture.season_label == season_label, CecchinoV4Fixture.status.in_(tuple(FINAL_STATUSES)), _json_missing(CecchinoV4Fixture.stats_json))
            .order_by(CecchinoV4Fixture.kickoff_at)
        ).all()
    )
    limit = ctx.params.get("limit")
    if limit:
        todo = todo[: int(limit)]
    with_lineups = bool(ctx.params.get("with_lineups", True))
    processed = 0
    for i, fx in enumerate(todo):
        ctx.client.ensure_budget(ctx.db)
        process_post_match(ctx, fx, with_lineups=with_lineups)
        processed += 1
        ctx.heartbeat(f"backfill {code} {season}: {i + 1}/{len(todo)}", (i + 1) / len(todo) * 100.0)
    remaining = len(todo) - processed
    return {"league_code": code, "season": int(season), "fixtures_final": counts["seen"], "fixtures_created": counts["created"], "processed": processed, "remaining_without_stats": remaining, "with_lineups": with_lineups}


JOBS: dict[str, Callable[[JobContext], dict[str, Any]]] = {
    "fixtures": job_fixtures,
    "post_match": job_post_match,
    "lineups": job_lineups,
    "injuries": job_injuries,
    "standings": job_standings,
    "odds_snapshot": job_odds_snapshot,
    "odds_closing": job_odds_closing,
    "coverage_scan": job_coverage_scan,
    "backfill": job_backfill,
}


# --- helper per GET /engine/data ----------------------------------------------------------------------------------------------------
def data_quality(db: Session, since_days: int = 14, *, now: datetime | None = None) -> list[dict[str, Any]]:
    """Per campionato: partite finite negli ultimi `since_days` giorni e percentuali di dati mancanti."""
    ref = now or _utcnow()
    since = ref - timedelta(days=int(since_days))
    rows = list(
        db.scalars(
            select(CecchinoV4Fixture).where(CecchinoV4Fixture.status.in_(tuple(FINAL_STATUSES)), CecchinoV4Fixture.kickoff_at >= since, CecchinoV4Fixture.kickoff_at <= ref)
        ).all()
    )
    with_odds = set(db.scalars(select(CecchinoV4OddsSnapshot.fixture_id).where(CecchinoV4OddsSnapshot.fixture_id.in_([f.id for f in rows] or [-1])).distinct()).all())
    out = []
    for lg in LEAGUES:
        mine = [f for f in rows if f.league_code == lg.code]
        n = len(mine)

        def pct(count: int) -> float | None:
            return round(count / n * 100.0, 1) if n else None

        out.append(
            {
                "league_code": lg.code,
                "competition": lg.competition,
                "fixtures": n,
                "missing_stats_pct": pct(sum(1 for f in mine if f.stats_json is None)),
                "missing_lineups_pct": pct(sum(1 for f in mine if f.lineups_status != LINEUPS_OFFICIAL)),
                "missing_odds_pct": pct(sum(1 for f in mine if f.id not in with_odds)),
            }
        )
    return out


def api_budget_today(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    ref = now or _utcnow()
    day = ref.astimezone(timezone.utc).date()
    return {"date": day.isoformat(), "calls": api_calls_today(db, day=day), "stop_at": int(v4_settings.api_daily_stop())}


def odds_registry_status(db: Session, *, now: datetime | None = None) -> dict[str, Any]:
    ref = now or _utcnow()
    rome_day = ref.astimezone(ROME_TZ).date()
    start = datetime(rome_day.year, rome_day.month, rome_day.day, tzinfo=ROME_TZ).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    today_rows = db.execute(
        select(CecchinoV4OddsSnapshot.kind, func.count()).where(CecchinoV4OddsSnapshot.taken_at >= start, CecchinoV4OddsSnapshot.taken_at < end).group_by(CecchinoV4OddsSnapshot.kind)
    ).all()
    by_kind = {str(k): int(c) for k, c in today_rows}
    last = db.scalar(select(func.max(CecchinoV4OddsSnapshot.taken_at)))
    if isinstance(last, str):
        try:
            last = datetime.fromisoformat(last)
        except ValueError:
            last = None
    last_aware = _aware(last) if isinstance(last, datetime) else None
    return {"snapshots_today": sum(by_kind.values()), "by_kind": by_kind, "last_taken_at": last_aware.isoformat() if last_aware else None}


def latest_coverage(db: Session) -> list[dict[str, Any]]:
    """Matrice dell'ultimo `coverage_scan` riuscito (vuota se non e' mai girato)."""
    job = db.scalars(
        select(CecchinoV4Job).where(CecchinoV4Job.name == "coverage_scan", CecchinoV4Job.status == JOB_DONE).order_by(CecchinoV4Job.created_at.desc()).limit(1)
    ).first()
    if job is None or not job.result_json:
        return []
    return list(job.result_json.get("coverage") or [])


def engine_data(db: Session, *, now: datetime | None = None, since_days: int = 14) -> dict[str, Any]:
    """Payload di GET /engine/data (docs/v4/API.md)."""
    return {
        "coverage": latest_coverage(db),
        "quality": data_quality(db, since_days, now=now),
        "api_budget": api_budget_today(db, now=now),
        "odds_registry": odds_registry_status(db, now=now),
    }


__all__ = [
    "JOBS",
    "JobAlreadyRunning",
    "JobContext",
    "UnknownJob",
    "ApiFootballError",
    "api_budget_today",
    "data_quality",
    "engine_data",
    "job_to_dict",
    "latest_coverage",
    "mark_stale_jobs",
    "odds_registry_status",
    "process_post_match",
    "recent_jobs",
    "run_job",
    "running_job",
    "upsert_fixture",
]
