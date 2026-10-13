"""Statistiche delle partite gia' giocate per il profilo xG di Cecchino Today, senza sprechi.

Prima (fino al 13/10/2026) ogni partita eleggibile chiedeva una per una le statistiche di tutte le partite
precedenti delle due squadre che non avevano xG in archivio. Nei campionati dove API-Football non fornisce
gli xG la risposta era sempre vuota e la richiesta si ripeteva a ogni scansione: sabato 10/10 circa 6.300
chiamate su 7.500 sono finite cosi'.

Ora:
1. tag permanente per campionato (`cecchino_xg_league_tags`): dopo `NO_XG_MIN_ANSWERS` partite risposte
   senza xG il campionato e' "senza xG" e non si chiede piu' nulla; con almeno una partita con xG resta
   "con xG" e si scaricano solo le partite nuove;
2. una partita a cui API-Football ha gia' risposto (statistiche in archivio o richiesta registrata dopo
   la fine) non si richiede di nuovo;
3. le richieste partono a gruppi di 20 con `fixtures?ids=` (stesso formato del collegamento dati), e ogni
   chiamata viene contata (`on_call`) e registrata nel consumo API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CecchinoTodayFixture, Fixture, League
from app.models.api_football_data import ApiFootballFixtureFetch
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.models.cecchino_xg_league_tag import (
    XG_TAG_HAS_XG,
    XG_TAG_NO_XG,
    XG_TAG_PENDING,
    CecchinoXgLeagueTag,
)
from app.services.api_football_client import (
    ApiFootballClient,
    ApiFootballError,
    ApiFootballQuotaExhausted,
)
from app.services.fixture_shared import team_stats_map as _team_stats_map

logger = logging.getLogger(__name__)

BATCH_SIZE = 20  # limite di API-Football per fixtures?ids
NO_XG_MIN_ANSWERS = 5  # partite risposte senza xG prima del tag definitivo "senza xG"
# una richiesta registrata vale come risposta definitiva solo se fatta a partita chiusa da un po'
ANSWER_AFTER_KICKOFF = timedelta(hours=3)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


@dataclass
class StatisticsFetchOutcome:
    calls: int = 0
    fixtures_considered: int = 0
    fixtures_requested: int = 0
    fixtures_answered: int = 0
    fixtures_with_stats: int = 0
    fixtures_with_xg: int = 0
    skipped_has_xg: int = 0
    skipped_already_answered: int = 0
    skipped_league_without_xg: int = 0
    leagues_tagged_no_xg: list[int] = field(default_factory=list)
    leagues_tagged_has_xg: list[int] = field(default_factory=list)
    quota_exhausted: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def skipped_total(self) -> int:
        return self.skipped_has_xg + self.skipped_already_answered + self.skipped_league_without_xg

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "fixtures_considered": self.fixtures_considered,
            "fixtures_requested": self.fixtures_requested,
            "fixtures_answered": self.fixtures_answered,
            "fixtures_with_stats": self.fixtures_with_stats,
            "fixtures_with_xg": self.fixtures_with_xg,
            "skipped_has_xg": self.skipped_has_xg,
            "skipped_already_answered": self.skipped_already_answered,
            "skipped_league_without_xg": self.skipped_league_without_xg,
            "leagues_tagged_no_xg": list(self.leagues_tagged_no_xg),
            "leagues_tagged_has_xg": list(self.leagues_tagged_has_xg),
            "quota_exhausted": self.quota_exhausted,
            "errors": list(self.errors[:5]),
        }


# --- lettura dei payload ---------------------------------------------------------------------


def statistics_blocks_have_xg(blocks: Any) -> bool:
    """True se almeno una squadra del payload statistiche ha un valore xG."""
    from app.services.cecchino.cecchino_current_season_xg import _expected_goals_from_statistics_list

    if not isinstance(blocks, list):
        return False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        stats = block.get("statistics")
        if isinstance(stats, list) and _expected_goals_from_statistics_list(stats) is not None:
            return True
    return False


def _stat_types(blocks: Any) -> set[str]:
    if not isinstance(blocks, list):
        return set()
    return {
        str(s.get("type"))
        for block in blocks
        if isinstance(block, dict)
        for s in (block.get("statistics") or [])
        if isinstance(s, dict) and s.get("value") is not None
    }


def _row_has_raw_statistics(row: Any) -> bool:
    raw = getattr(row, "raw_json", None)
    return isinstance(raw, dict) and isinstance(raw.get("statistics"), list)


# --- campionato di una partita e tag ---------------------------------------------------------


class _LeagueResolver:
    def __init__(self, db: Session) -> None:
        self.db = db
        self._cache: dict[int, tuple[int | None, str | None, str | None]] = {}

    def provider_league(self, fx: Fixture) -> tuple[int | None, str | None, str | None]:
        local_id = getattr(fx, "league_id", None)
        if local_id is None:
            return None, None, None
        key = int(local_id)
        if key not in self._cache:
            league = self.db.get(League, key)
            if league is None or getattr(league, "api_league_id", None) is None:
                self._cache[key] = (None, None, None)
            else:
                self._cache[key] = (
                    int(league.api_league_id),
                    getattr(league, "name", None),
                    getattr(league, "country", None),
                )
        return self._cache[key]


def _decide(tag: CecchinoXgLeagueTag, now: datetime) -> str | None:
    """Aggiorna lo stato del tag dalle risposte accumulate; ritorna il nuovo stato se e' cambiato."""
    if tag.status in (XG_TAG_NO_XG, XG_TAG_HAS_XG):
        return None
    if int(tag.fixtures_with_xg or 0) > 0:
        tag.status = XG_TAG_HAS_XG
        tag.decided_at = now
        return XG_TAG_HAS_XG
    if int(tag.fixtures_answered or 0) >= NO_XG_MIN_ANSWERS:
        tag.status = XG_TAG_NO_XG
        tag.decided_at = now
        return XG_TAG_NO_XG
    return None


def _insert_tag(db: Session, tag: CecchinoXgLeagueTag) -> CecchinoXgLeagueTag:
    """Nuovo tag in un savepoint: se un altro processo l'ha appena creato, si usa il suo."""
    try:
        with db.begin_nested():
            db.add(tag)
            db.flush()
        return tag
    except IntegrityError:
        existing = db.get(CecchinoXgLeagueTag, int(tag.provider_league_id))
        return existing if existing is not None else tag


def load_league_tags(db: Session, provider_league_ids: Iterable[int]) -> dict[int, CecchinoXgLeagueTag]:
    ids = sorted({int(i) for i in provider_league_ids if i is not None})
    if not ids:
        return {}
    rows = db.scalars(
        select(CecchinoXgLeagueTag).where(CecchinoXgLeagueTag.provider_league_id.in_(ids))
    ).all()
    return {int(r.provider_league_id): r for r in rows}


# --- scelta delle partite da chiedere --------------------------------------------------------


def _answered_fetches(db: Session, fixtures: list[Fixture]) -> set[int]:
    """api_fixture_id gia' richiesti a partita chiusa (risposta definitiva, anche se vuota)."""
    by_api = {int(f.api_fixture_id): f for f in fixtures if getattr(f, "api_fixture_id", None) is not None}
    if not by_api:
        return set()
    rows = db.scalars(
        select(ApiFootballFixtureFetch).where(ApiFootballFixtureFetch.api_fixture_id.in_(list(by_api)))
    ).all()
    out: set[int] = set()
    for r in rows:
        fx = by_api.get(int(r.api_fixture_id))
        kickoff = _aware(getattr(fx, "kickoff_at", None)) if fx is not None else None
        fetched = _aware(r.fetched_at)
        if fetched is not None and (kickoff is None or fetched >= kickoff + ANSWER_AFTER_KICKOFF):
            out.add(int(r.api_fixture_id))
    return out


def fetch_prior_statistics(
    db: Session,
    fixtures: Iterable[Fixture],
    *,
    client: ApiFootballClient,
    force_refresh: bool = False,
    on_call: Callable[[int], None] | None = None,
    max_calls: int | None = None,
) -> StatisticsFetchOutcome:
    """Scarica (a gruppi di 20) le statistiche che mancano davvero per il profilo xG."""
    from app.services.cecchino.cecchino_current_season_xg import _fixture_pair_xg

    now = _now()
    out = StatisticsFetchOutcome()
    unique: dict[int, Fixture] = {}
    for fx in fixtures:
        if fx is None or getattr(fx, "api_fixture_id", None) is None:
            continue
        unique.setdefault(int(fx.id), fx)
    items = list(unique.values())
    out.fixtures_considered = len(items)
    if not items:
        return out

    resolver = _LeagueResolver(db)
    league_of: dict[int, int | None] = {}
    league_meta: dict[int, tuple[str | None, str | None]] = {}
    for fx in items:
        pl, name, country = resolver.provider_league(fx)
        league_of[int(fx.id)] = pl
        if pl is not None:
            league_meta.setdefault(pl, (name, country))
    tags = load_league_tags(db, [pl for pl in league_of.values() if pl is not None])

    stats_map = _team_stats_map(db, [int(f.id) for f in items])
    answered_api = _answered_fetches(db, items)

    # evidenza gia' in archivio, usata solo per creare il tag la prima volta (nessuna chiamata)
    seed: dict[int, list[int]] = {}
    candidates: list[Fixture] = []
    for fx in items:
        fid = int(fx.id)
        pl = league_of.get(fid)
        home_xg, away_xg = _fixture_pair_xg(fx, stats_map)
        has_xg = home_xg is not None and away_xg is not None
        home_row = stats_map.get((fid, int(fx.home_team_id)))
        away_row = stats_map.get((fid, int(fx.away_team_id)))
        known_stats = _row_has_raw_statistics(home_row) and _row_has_raw_statistics(away_row)
        answered = known_stats or int(fx.api_fixture_id) in answered_api
        if pl is not None and pl not in tags and (has_xg or answered):
            ev = seed.setdefault(pl, [0, 0])
            ev[0] += 1
            ev[1] += 1 if (home_xg is not None or away_xg is not None) else 0
        if force_refresh:
            candidates.append(fx)
            continue
        if has_xg:
            out.skipped_has_xg += 1
            continue
        if answered:
            out.skipped_already_answered += 1
            continue
        candidates.append(fx)

    for pl, (answered_n, with_xg_n) in seed.items():
        name, country = league_meta.get(pl, (None, None))
        tag = CecchinoXgLeagueTag(
            provider_league_id=pl,
            status=XG_TAG_PENDING,
            league_name=(name or None) and str(name)[:255],
            country=(country or None) and str(country)[:128],
            fixtures_answered=answered_n,
            fixtures_with_xg=with_xg_n,
        )
        _decide(tag, now)
        tag = _insert_tag(db, tag)
        tags[pl] = tag
        _note_decision(out, tag)

    if not force_refresh:
        kept: list[Fixture] = []
        for fx in candidates:
            tag = tags.get(league_of.get(int(fx.id)) or -1)
            if tag is not None and tag.status == XG_TAG_NO_XG:
                out.skipped_league_without_xg += 1
                continue
            kept.append(fx)
        candidates = kept
    if not candidates:
        return out

    # ordine: per ogni campionato le partite piu' recenti per prime
    candidates.sort(key=lambda f: (_aware(f.kickoff_at) or now), reverse=True)

    # 1) un gruppo di prova per ogni campionato ancora da decidere; 2) il resto, a gruppi misti
    pending_leagues: dict[int, list[Fixture]] = {}
    rest: list[Fixture] = []
    for fx in candidates:
        pl = league_of.get(int(fx.id))
        tag = tags.get(pl) if pl is not None else None
        if not force_refresh and pl is not None and (tag is None or tag.status == XG_TAG_PENDING):
            pending_leagues.setdefault(pl, []).append(fx)
        else:
            rest.append(fx)

    def _budget_left() -> bool:
        return max_calls is None or out.calls < max_calls

    for pl, group in pending_leagues.items():
        if out.quota_exhausted or not _budget_left():
            break
        probe, remaining = group[:BATCH_SIZE], group[BATCH_SIZE:]
        _request_batch(db, client, probe, league_of, league_meta, tags, out, now, on_call)
        tag = tags.get(pl)
        if tag is not None and tag.status == XG_TAG_NO_XG:
            out.skipped_league_without_xg += len(remaining)
        else:
            rest.extend(remaining)

    rest.sort(key=lambda f: (_aware(f.kickoff_at) or now), reverse=True)
    for start in range(0, len(rest), BATCH_SIZE):
        if out.quota_exhausted or not _budget_left():
            break
        chunk = []
        for fx in rest[start : start + BATCH_SIZE]:
            tag = tags.get(league_of.get(int(fx.id)) or -1)
            if not force_refresh and tag is not None and tag.status == XG_TAG_NO_XG:
                out.skipped_league_without_xg += 1
                continue
            chunk.append(fx)
        if chunk:
            _request_batch(db, client, chunk, league_of, league_meta, tags, out, now, on_call)
    return out


def _note_decision(out: StatisticsFetchOutcome, tag: CecchinoXgLeagueTag) -> None:
    pl = int(tag.provider_league_id)
    if tag.status == XG_TAG_NO_XG and pl not in out.leagues_tagged_no_xg:
        out.leagues_tagged_no_xg.append(pl)
    elif tag.status == XG_TAG_HAS_XG and pl not in out.leagues_tagged_has_xg:
        out.leagues_tagged_has_xg.append(pl)


def _request_batch(
    db: Session,
    client: ApiFootballClient,
    chunk: list[Fixture],
    league_of: dict[int, int | None],
    league_meta: dict[int, tuple[str | None, str | None]],
    tags: dict[int, CecchinoXgLeagueTag],
    out: StatisticsFetchOutcome,
    now: datetime,
    on_call: Callable[[int], None] | None,
) -> None:
    from app.services.cecchino.cecchino_current_season_xg import _persist_fixture_statistics

    by_api = {int(f.api_fixture_id): f for f in chunk}
    ids = "-".join(str(i) for i in by_api)
    try:
        body = client.get("fixtures", {"ids": ids})
    except ApiFootballQuotaExhausted:
        out.quota_exhausted = True
        logger.warning("xg statistics: quota API-Football esaurita, mi fermo")
        return
    except ApiFootballError as exc:
        out.errors.append(str(exc)[:160])
        logger.warning("xg statistics: gruppo non letto ids=%s: %s", ids, exc)
        return
    finally:
        # la chiamata e' partita in ogni caso (anche se fallita): si conta
        out.calls += 1
        if on_call is not None:
            try:
                on_call(1)
            except Exception:  # noqa: BLE001 - un contatore non ferma il lavoro
                logger.debug("xg statistics: on_call fallito", exc_info=True)
    if out.quota_exhausted:
        return

    out.fixtures_requested += len(by_api)
    returned: set[int] = set()
    for item in (body or {}).get("response") or []:
        fixture_obj = item.get("fixture") or {}
        try:
            api_id = int(fixture_obj.get("id"))
        except (TypeError, ValueError):
            continue
        fx = by_api.get(api_id)
        if fx is None:
            continue
        returned.add(api_id)
        blocks = item.get("statistics") or []
        types = _stat_types(blocks)
        has_xg = statistics_blocks_have_xg(blocks)
        if blocks and types:
            try:
                _persist_fixture_statistics(db, fx, blocks)
            except Exception:  # noqa: BLE001 - una partita non ferma il gruppo
                logger.exception("xg statistics: salvataggio fallito fixture=%s", fx.id)
            out.fixtures_with_stats += 1
        if has_xg:
            out.fixtures_with_xg += 1
        status = str(((fixture_obj.get("status") or {}).get("short")) or "")
        fetch = db.get(ApiFootballFixtureFetch, api_id) or ApiFootballFixtureFetch(api_fixture_id=api_id)
        fetch.fetched_at = now
        fetch.fixture_status = status[:16]
        fetch.stats_teams = len(blocks)
        fetch.stat_types = len(types)
        fetch.lineups_teams = len(item.get("lineups") or [])
        db.merge(fetch)
        _count_answer(tags, league_of.get(int(fx.id)), league_meta, has_xg, now, out, db)

    # partite chieste ma non restituite: API-Football ha risposto che non c'e' nulla
    for api_id, fx in by_api.items():
        if api_id not in returned:
            _count_answer(tags, league_of.get(int(fx.id)), league_meta, False, now, out, db)
    out.fixtures_answered += len(by_api)
    db.flush()


def _count_answer(
    tags: dict[int, CecchinoXgLeagueTag],
    provider_league_id: int | None,
    league_meta: dict[int, tuple[str | None, str | None]],
    has_xg: bool,
    now: datetime,
    out: StatisticsFetchOutcome,
    db: Session,
) -> None:
    if provider_league_id is None:
        return
    tag = tags.get(provider_league_id)
    if tag is None:
        name, country = league_meta.get(provider_league_id, (None, None))
        tag = CecchinoXgLeagueTag(
            provider_league_id=provider_league_id,
            status=XG_TAG_PENDING,
            league_name=(name or None) and str(name)[:255],
            country=(country or None) and str(country)[:128],
            fixtures_answered=0,
            fixtures_with_xg=0,
        )
        tag = _insert_tag(db, tag)
        tags[provider_league_id] = tag
    tag.fixtures_answered = int(tag.fixtures_answered or 0) + 1
    if has_xg:
        tag.fixtures_with_xg = int(tag.fixtures_with_xg or 0) + 1
    if _decide(tag, now) is not None:
        _note_decision(out, tag)


# --- fase xG a fine scansione -----------------------------------------------------------------


def run_deferred_xg_phase(
    db: Session,
    today_fixture_ids: Iterable[int],
    *,
    client: ApiFootballClient,
    on_call: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Profili xG delle partite eleggibili, a scansione finita: prima tutte le statistiche mancanti
    in un unico giro a gruppi (partite in comune tra piu' match chieste una volta sola), poi i profili
    calcolati dall'archivio. Se la quota finisce, le partite restanti tengono il profilo precedente
    e lo calcolano all'apertura del dettaglio."""
    from app.services.cecchino.cecchino_current_season_xg import (
        _prior_fixtures_both_teams,
        ensure_current_season_xg_profile_for_fixture,
    )

    ids = list(dict.fromkeys(int(i) for i in today_fixture_ids))
    summary: dict[str, Any] = {"rows": len(ids), "profiles_ok": 0, "profiles_cached": 0, "profiles_skipped": 0}
    union: list[Fixture] = []
    seen: set[int] = set()
    for tid in ids:
        row = db.get(CecchinoTodayFixture, tid)
        if row is None or row.eligibility_status != ELIGIBILITY_ELIGIBLE or not row.local_fixture_id:
            continue
        target = db.get(Fixture, int(row.local_fixture_id))
        if target is None:
            continue
        exclude_api = int(row.provider_fixture_id) if row.provider_fixture_id else None
        try:
            prior = _prior_fixtures_both_teams(db, target, exclude_provider_fixture_id=exclude_api)
        except Exception:  # noqa: BLE001
            logger.exception("xg phase: storico non leggibile today_fixture=%s", tid)
            continue
        for fx in prior:
            if int(fx.id) not in seen:
                seen.add(int(fx.id))
                union.append(fx)

    outcome = fetch_prior_statistics(db, union, client=client, on_call=on_call)
    db.commit()
    summary["statistics"] = outcome.as_dict()
    if outcome.quota_exhausted:
        summary["status"] = "quota_exhausted"
        summary["profiles_skipped"] = len(ids)
        return summary

    for n, tid in enumerate(ids, start=1):
        try:
            res = ensure_current_season_xg_profile_for_fixture(db, tid, client=client, on_call=on_call)
        except Exception:  # noqa: BLE001 - un profilo non ferma gli altri
            logger.exception("xg phase: profilo fallito today_fixture=%s", tid)
            db.rollback()
            summary["profiles_skipped"] += 1
            continue
        status = res.get("status")
        if status == "ok":
            summary["profiles_ok"] += 1
        elif status == "cached":
            summary["profiles_cached"] += 1
        else:
            summary["profiles_skipped"] += 1
        if "xg_provider_quota_exhausted" in (res.get("warnings") or []):
            summary["status"] = "quota_exhausted"
            db.commit()
            return summary
        if n % 20 == 0:
            db.commit()
    db.commit()
    summary["status"] = "ok"
    return summary
