"""Client API-Football della V4: involucro sottile su `ApiFootballClient` con guardia budget.

Ogni chiamata:
1. controlla il contatore del giorno in `api_usage_events` (provider API-Football) e si ferma
   con `BudgetGuardStop` se ha raggiunto `settings.api_daily_stop()` (regola 6);
2. imposta l'`ApiUsageContext` del job (job_id, campionato, partita) cosi' l'evento d'uso
   registrato dal client sottostante e' attribuito alla V4;
3. incrementa il contatore locale `calls` (letto dal job per `api_calls`).

In test si inietta un client finto con gli stessi nomi di metodo di `ApiFootballClient`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.api_usage_event import PROVIDER_API_FOOTBALL, ApiUsageEvent
from app.services.api_usage_context import ApiUsageContext, BudgetGuardStop
from app.services.cecchino_v4 import settings as v4_settings
from app.services.cecchino_v4.constants import LEAGUE_BY_API_ID

BUDGET_STOP_STATUS = "failed_budget_guard"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def api_calls_today(db: Session, *, day: date | None = None) -> int:
    """Chiamate reali (senza cache) del provider API-Football nel giorno UTC `day` (default oggi)."""
    the_day = day or _utcnow().date()
    start = datetime(the_day.year, the_day.month, the_day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    count = db.scalar(
        select(func.count())
        .select_from(ApiUsageEvent)
        .where(
            ApiUsageEvent.provider_source == PROVIDER_API_FOOTBALL,
            ApiUsageEvent.created_at >= start,
            ApiUsageEvent.created_at < end,
            ApiUsageEvent.cache_hit.is_(False),
            ApiUsageEvent.negative_cache_hit.is_(False),
        )
    )
    return int(count or 0)


def ensure_budget(db: Session | None, *, stop_at: int | None = None, calls_counter: Callable[[], int] | None = None) -> int:
    """Ritorna le chiamate del giorno; alza `BudgetGuardStop` se sono >= alla soglia."""
    limit = int(stop_at if stop_at is not None else v4_settings.api_daily_stop())
    if calls_counter is not None:
        used = int(calls_counter())
    elif db is not None:
        used = api_calls_today(db)
    else:
        used = 0
    if used >= limit:
        raise BudgetGuardStop(
            status=BUDGET_STOP_STATUS,
            message=f"Budget API-Football del giorno raggiunto: {used} chiamate su {limit}. La V4 si ferma.",
            api_calls_total=used,
            details={"calls_today": used, "stop_at": limit},
        )
    return used


class V4ApiClient:
    """Metodi di alto livello per i job V4. `inner` e' un `ApiFootballClient` o un finto equivalente."""

    def __init__(
        self,
        inner: Any | None = None,
        *,
        db: Session | None = None,
        stop_at: int | None = None,
        league_ids: Iterable[int] | None = None,
    ) -> None:
        if inner is None:
            from app.services.api_football_client import ApiFootballClient

            inner = ApiFootballClient()
        self._inner = inner
        self._db = db
        self._stop_at = stop_at
        self._context = ApiUsageContext(record_events=True)
        self._league_ids = set(league_ids) if league_ids is not None else set(LEAGUE_BY_API_ID)
        self.calls = 0

    # --- collegamento al job ------------------------------------------------------------
    @property
    def inner(self) -> Any:
        return self._inner

    def bind(self, db: Session, *, job_id: str | None, scan_date: date | None = None) -> None:
        """Collega il client alla sessione e al job: da qui ogni chiamata e' registrata con il job_id."""
        self._db = db
        self._context = ApiUsageContext(job_id=job_id, scan_date=scan_date, record_events=True)
        if hasattr(self._inner, "set_usage_db"):
            self._inner.set_usage_db(db)
        self._apply_context(self._context)

    def _apply_context(self, ctx: ApiUsageContext) -> None:
        if hasattr(self._inner, "set_usage_context"):
            self._inner.set_usage_context(ctx)

    def ensure_budget(self, db: Session | None = None) -> int:
        return ensure_budget(db or self._db, stop_at=self._stop_at)

    def _call(self, fn: Callable[..., Any], *args: Any, league_id: int | None = None, fixture_id: int | None = None, **kwargs: Any) -> Any:
        self.ensure_budget()
        ctx = self._context
        if league_id is not None:
            ctx = ctx.with_league(int(league_id))
        if fixture_id is not None:
            ctx = ctx.with_fixture(int(fixture_id))
        self._apply_context(ctx)
        try:
            self.calls += 1
            return fn(*args, **kwargs)
        finally:
            self._apply_context(self._context)

    # --- fixture ------------------------------------------------------------------------
    def fixtures_by_date(self, day: date | str, *, timezone_name: str = "Europe/Rome") -> list[dict[str, Any]]:
        """GET /fixtures?date= — una chiamata per tutti i campionati, filtrata ai 16 della V4."""
        day_str = day.isoformat() if isinstance(day, date) else str(day)
        items = self._call(self._inner.get_fixtures_by_date, day_str, timezone_name)
        return [it for it in items if self._league_id_of(it) in self._league_ids]

    def fixtures_by_league_season(self, league_id: int, season: int, *, status: str | None = None) -> list[dict[str, Any]]:
        """GET /fixtures?league=&season= — tutte le partite della stagione in una chiamata."""
        return list(self._call(self._inner.get_fixtures, int(league_id), int(season), status, league_id=league_id))

    def fixture_by_id(self, api_fixture_id: int) -> dict[str, Any] | None:
        return self._call(self._inner.get_fixture_by_id, int(api_fixture_id), fixture_id=api_fixture_id)

    def fixture_statistics(self, api_fixture_id: int) -> list[dict[str, Any]]:
        return list(self._call(self._inner.get_fixture_statistics, int(api_fixture_id), fixture_id=api_fixture_id))

    def fixture_events(self, api_fixture_id: int) -> list[dict[str, Any]]:
        return list(self._call(self._inner.get_fixture_events, int(api_fixture_id), fixture_id=api_fixture_id))

    def fixture_players(self, api_fixture_id: int) -> list[dict[str, Any]]:
        return list(self._call(self._inner.get_fixture_players, int(api_fixture_id), fixture_id=api_fixture_id))

    def fixture_lineups(self, api_fixture_id: int) -> list[dict[str, Any]]:
        return list(self._call(self._inner.get_fixture_lineups, int(api_fixture_id), fixture_id=api_fixture_id))

    # --- contesto di campionato -----------------------------------------------------------
    def injuries(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return list(self._call(self._inner.get_injuries, int(league_id), int(season), league_id=league_id))

    def standings(self, league_id: int, season: int) -> list[dict[str, Any]]:
        return list(self._call(self._inner.get_standings, int(league_id), int(season), league_id=league_id))

    # --- quote ------------------------------------------------------------------------------
    def odds_by_league_date(self, league_id: int, season: int, day: date | str, bookmaker_id: int) -> list[dict[str, Any]]:
        """GET /odds?league=&season=&date=&bookmaker= con paginazione manuale (una chiamata per pagina)."""
        day_str = day.isoformat() if isinstance(day, date) else str(day)
        params = {"league": int(league_id), "season": int(season), "date": day_str, "bookmaker": int(bookmaker_id)}
        merged: list[dict[str, Any]] = []
        page = 1
        while True:
            body = self._call(self._inner.get, "odds", {**params, "page": page}, league_id=league_id)
            merged.extend(body.get("response") or [])
            paging = body.get("paging") or {}
            current = int(paging.get("current") or page)
            total = int(paging.get("total") or 1)
            if current >= total:
                break
            page = current + 1
        return merged

    def odds_by_fixture(self, api_fixture_id: int) -> list[dict[str, Any]]:
        """GET /odds?fixture= — tutti i bookmaker nel payload, una chiamata."""
        return list(self._call(self._inner.get_fixture_odds_by_fixture, int(api_fixture_id), fixture_id=api_fixture_id))

    def bookmakers(self) -> list[dict[str, Any]]:
        return list(self._call(self._inner.get_odds_bookmakers))

    # --- utilita' -----------------------------------------------------------------------------
    @staticmethod
    def _league_id_of(item: dict[str, Any]) -> int | None:
        league = item.get("league") if isinstance(item, dict) else None
        try:
            return int((league or {}).get("id"))
        except (TypeError, ValueError):
            return None
