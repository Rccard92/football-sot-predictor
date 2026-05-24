"""Calcolo profilo severità arbitro da cartellini (DB + cache import + API-Sports)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.constants import FINISHED_STATUSES
from app.core.referee_severity_constants import (
    RED_INCIDENCE_NOTE_THRESHOLD,
    SAMPLE_HIGH_MIN,
    SAMPLE_LOW_MAX,
    SEVERITY_MEDIUM,
    SEVERITY_PERMISSIVE,
    SEVERITY_SEVERE,
    SEVERITY_YELLOW_MEDIUM_MAX,
    SEVERITY_YELLOW_PERMISSIVE_MAX,
)
from app.models import (
    Fixture,
    FixtureReferee,
    FixtureTeamStat,
    League,
    Referee,
    RefereeSeasonProfile,
    Season,
    Team,
)
from app.models.referee_fixture_card_summary import (
    CARD_SOURCE_DB_TEAM_STATS,
    CARD_SOURCE_EVENTS,
    CARD_SOURCE_STATISTICS,
    RefereeFixtureCardSummary,
)
from app.models.referee_season_profile import SAMPLE_QUALITY_LOW
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.referee_cards_parser import (
    match_cards_from_statistics_blocks_using_mapping,
    match_cards_from_team_stats_rows,
)
from app.services.referee_cards_resolver import card_summary_to_dict
from app.services.referee_name_normalize import normalize_referee_name, referee_names_match


def classify_severity(avg_yellow: float | None, avg_red: float | None) -> tuple[str, dict[str, Any]]:
    notes: dict[str, Any] = {}
    y = float(avg_yellow or 0.0)
    if y < SEVERITY_YELLOW_PERMISSIVE_MAX:
        label = SEVERITY_PERMISSIVE
    elif y <= SEVERITY_YELLOW_MEDIUM_MAX:
        label = SEVERITY_MEDIUM
    else:
        label = SEVERITY_SEVERE

    r = float(avg_red or 0.0)
    if r >= RED_INCIDENCE_NOTE_THRESHOLD:
        notes["high_red_incidence"] = True
        notes["red_incidence_note"] = (
            f"Incidenza rossi elevata (media {r:.2f} a partita, soglia {RED_INCIDENCE_NOTE_THRESHOLD})"
        )
    return label, notes


def sample_quality_from_count(matches_count: int) -> str:
    if matches_count <= SAMPLE_LOW_MAX:
        return "low"
    if matches_count < SAMPLE_HIGH_MIN:
        return "medium"
    return "high"


def _league_profile_label(league_api_id: int, season_year: int) -> str:
    if league_api_id == 135:
        return f"Serie A stagione {season_year}"
    return f"Lega {league_api_id} stagione {season_year}"


def aggregate_card_rows(
    rows: list[RefereeFixtureCardSummary],
    *,
    team_api_id: int | None = None,
    team_internal_id: int | None = None,
) -> dict[str, Any]:
    usable = [r for r in rows if r.total_yellow is not None or r.total_red is not None]
    if not usable:
        return {
            "matches_count": 0,
            "avg_yellow_cards": None,
            "avg_red_cards": None,
            "data_source": "db_only",
        }

    sources: set[str] = set()
    total_y = total_r = 0
    team_y = team_r = 0
    team_n = 0
    for r in usable:
        total_y += int(r.total_yellow or 0)
        total_r += int(r.total_red or 0)
        if r.card_source:
            sources.add(r.card_source)
        if team_api_id is not None:
            if r.home_team_api_id == team_api_id:
                if r.home_yellow is not None:
                    team_y += int(r.home_yellow)
                if r.home_red is not None:
                    team_r += int(r.home_red)
                team_n += 1
            elif r.away_team_api_id == team_api_id:
                if r.away_yellow is not None:
                    team_y += int(r.away_yellow)
                if r.away_red is not None:
                    team_r += int(r.away_red)
                team_n += 1

    mc = len(usable)
    data_source = _resolve_data_source(sources)
    out: dict[str, Any] = {
        "matches_count": mc,
        "avg_yellow_cards": round(total_y / mc, 2),
        "avg_red_cards": round(total_r / mc, 2),
        "data_source": data_source,
    }
    if team_n > 0 and team_api_id is not None:
        out["avg_yellow_team"] = round(team_y / team_n, 2)
        out["avg_red_team"] = round(team_r / team_n, 2)
    return out


def _resolve_data_source(sources: set[str]) -> str:
    if not sources:
        return "db_only"
    db_only = {CARD_SOURCE_DB_TEAM_STATS}
    api_only = {CARD_SOURCE_EVENTS, CARD_SOURCE_STATISTICS}
    if sources <= db_only:
        return "db_only"
    if sources <= api_only:
        return "api_sports_fetched"
    return "mixed"


class RefereeSeverityService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def _resolve_referee(
        self,
        db: Session,
        *,
        referee_name: str | None,
        fixture_id: int | None,
    ) -> tuple[Referee | None, str | None]:
        if fixture_id is not None:
            fx = db.get(Fixture, int(fixture_id))
            if fx is None:
                return None, None
            link = db.scalar(
                select(FixtureReferee)
                .where(FixtureReferee.fixture_id == int(fx.id))
                .order_by(FixtureReferee.id.desc()),
            )
            if link and link.referee_id:
                ref = db.get(Referee, int(link.referee_id))
                if ref:
                    return ref, ref.name
            if fx.referee:
                return self._referee_by_name(db, fx.referee), fx.referee
            return None, None
        if referee_name:
            return self._referee_by_name(db, referee_name), referee_name.strip()
        return None, None

    def _referee_by_name(self, db: Session, name: str) -> Referee | None:
        norm = normalize_referee_name(name)
        if not norm:
            return None
        return db.scalar(select(Referee).where(Referee.normalized_name == norm).order_by(Referee.id.asc()))

    def _season_scope(self, db: Session, league_api_id: int, season_year: int) -> tuple[int | None, int]:
        league = db.scalar(select(League).where(League.api_league_id == int(league_api_id)))
        if league is None:
            return None, 0
        season = db.scalar(
            select(Season).where(Season.league_id == int(league.id), Season.year == int(season_year)),
        )
        if season is None:
            return None, 0
        n = db.scalar(
            select(func.count())
            .select_from(Fixture)
            .where(
                Fixture.season_id == int(season.id),
                Fixture.status.in_(list(FINISHED_STATUSES)),
            ),
        )
        return int(season.id), int(n or 0)

    def _referee_match_count_db(
        self,
        db: Session,
        *,
        season_id: int | None,
        referee: Referee | None,
        referee_name: str,
    ) -> int:
        if season_id is None:
            return 0
        rows = list(
            db.scalars(
                select(Fixture).where(
                    Fixture.season_id == int(season_id),
                    Fixture.status.in_(list(FINISHED_STATUSES)),
                ),
            ).all(),
        )
        ref_id = int(referee.id) if referee else None
        n = 0
        for fx in rows:
            if ref_id:
                link = db.scalar(
                    select(FixtureReferee).where(
                        FixtureReferee.fixture_id == int(fx.id),
                        FixtureReferee.referee_id == ref_id,
                    ),
                )
                if link:
                    n += 1
                    continue
            if referee_names_match(fx.referee, referee_name):
                n += 1
        return n

    def _cache_rows_season(
        self,
        db: Session,
        *,
        referee_id: int,
        league_api_id: int,
        season_year: int,
    ) -> list[RefereeFixtureCardSummary]:
        return list(
            db.scalars(
                select(RefereeFixtureCardSummary)
                .where(
                    RefereeFixtureCardSummary.referee_id == int(referee_id),
                    RefereeFixtureCardSummary.league_api_id == int(league_api_id),
                    RefereeFixtureCardSummary.season_year == int(season_year),
                )
                .order_by(RefereeFixtureCardSummary.kickoff_at.desc()),
            ).all(),
        )

    def _team_stats_pair(self, db: Session, fixture_id: int) -> tuple[Any | None, Any | None]:
        rows = list(
            db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(fixture_id))).all(),
        )
        if len(rows) < 2:
            return (rows[0] if rows else None), None
        by_side = {str(r.side or "").lower(): r for r in rows}
        return by_side.get("home") or rows[0], by_side.get("away") or rows[1]

    def _cards_for_fixture_db(self, db: Session, fx: Fixture) -> tuple[int | None, int | None, str]:
        home_row, away_row = self._team_stats_pair(db, int(fx.id))
        cards = match_cards_from_team_stats_rows(home_row, away_row)
        yellow = cards.yellow_cards
        red = cards.red_cards_total if cards.red_cards_total is not None else cards.red_cards
        if yellow is not None and red is not None:
            return yellow, red, CARD_SOURCE_DB_TEAM_STATS
        try:
            blocks = self._client.get_fixture_statistics(int(fx.api_fixture_id))
            api_cards = match_cards_from_statistics_blocks_using_mapping(blocks)
            if api_cards.yellow_cards is not None or api_cards.red_cards is not None:
                y = api_cards.yellow_cards if yellow is None else yellow
                r = api_cards.red_cards_total if red is None else red
                return y, r, CARD_SOURCE_STATISTICS
        except ApiFootballError:
            pass
        return yellow, red, CARD_SOURCE_DB_TEAM_STATS

    def _coverage_metadata(
        self,
        db: Session,
        *,
        league_api_id: int,
        season_year: int,
        referee: Referee | None,
        referee_name: str,
        cache_rows: list[RefereeFixtureCardSummary],
        fixtures_with_card_data: int,
    ) -> dict[str, Any]:
        season_id, fixtures_scanned = self._season_scope(db, league_api_id, season_year)
        with_ref = self._referee_match_count_db(
            db,
            season_id=season_id,
            referee=referee,
            referee_name=referee_name,
        )
        if len(cache_rows) > with_ref:
            with_ref = len(cache_rows)
        missing = max(0, with_ref - fixtures_with_card_data)
        label = _league_profile_label(league_api_id, season_year)
        note = (
            f"Profilo calcolato su {fixtures_with_card_data} partite con cartellini "
            f"su {with_ref} match arbitro individuati (FT in DB: {fixtures_scanned}). "
        )
        if missing > 0:
            note += f"{missing} partite senza cartellini: usa «Importa storico stagione»."
        else:
            note += "Usa import storico per ampliare il campione oltre il DB."
        return {
            "profile_label": label,
            "fixtures_scanned": fixtures_scanned,
            "fixtures_with_same_referee": with_ref,
            "fixtures_with_card_data": fixtures_with_card_data,
            "missing_card_data_count": missing,
            "coverage_note": note,
        }

    def compute_profile(
        self,
        db: Session,
        *,
        referee_name: str | None = None,
        league_id: int | None = None,
        season: int | None = None,
        max_matches: int | None = None,
        fixture_id: int | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        league_api_id = int(league_id if league_id is not None else settings.default_league_id)

        ref_row, resolved_name = self._resolve_referee(db, referee_name=referee_name, fixture_id=fixture_id)
        if not resolved_name:
            return {
                "status": "error",
                "message": "Nome arbitro non disponibile: sincronizza la fixture o indica referee_name",
            }

        season_year = season
        if season_year is None and fixture_id is not None:
            fx0 = db.get(Fixture, int(fixture_id))
            if fx0:
                season_row = db.get(Season, int(fx0.season_id))
                season_year = int(season_row.year) if season_row else None
        if season_year is None:
            season_year = int(settings.default_season)

        profile_label = _league_profile_label(league_api_id, int(season_year))
        fixtures_used: list[dict[str, Any]] = []
        sources_used: set[str] = set()

        if ref_row is not None:
            cache_rows = self._cache_rows_season(
                db,
                referee_id=int(ref_row.id),
                league_api_id=league_api_id,
                season_year=int(season_year),
            )
            cap = int(max_matches) if max_matches and max_matches > 0 else None
            candidates = cache_rows[:cap] if cap else cache_rows
            total_yellow = total_red = 0
            counted = 0
            for row in candidates:
                if row.total_yellow is None and row.total_red is None:
                    continue
                y, r = int(row.total_yellow or 0), int(row.total_red or 0)
                total_yellow += y
                total_red += r
                counted += 1
                if row.card_source:
                    sources_used.add(row.card_source)
                fixtures_used.append(card_summary_to_dict(row))

            if counted > 0:
                avg_yellow = round(total_yellow / counted, 2)
                avg_red = round(total_red / counted, 2)
                severity_label, severity_notes = classify_severity(avg_yellow, avg_red)
                sample_quality = sample_quality_from_count(counted)
                calculated_at = datetime.now(timezone.utc)
                data_source = _resolve_data_source(sources_used)
                coverage = self._coverage_metadata(
                    db,
                    league_api_id=league_api_id,
                    season_year=int(season_year),
                    referee=ref_row,
                    referee_name=resolved_name,
                    cache_rows=cache_rows,
                    fixtures_with_card_data=counted,
                )
                raw_payload = {"fixtures_used": fixtures_used, "severity_notes": severity_notes, "data_source": data_source}
                profile = db.scalar(
                    select(RefereeSeasonProfile).where(
                        RefereeSeasonProfile.referee_id == int(ref_row.id),
                        RefereeSeasonProfile.league_id == league_api_id,
                        RefereeSeasonProfile.season == int(season_year),
                    ),
                )
                if profile is None:
                    profile = RefereeSeasonProfile(
                        referee_id=int(ref_row.id),
                        league_id=league_api_id,
                        season=int(season_year),
                    )
                    db.add(profile)
                profile.matches_count = counted
                profile.total_yellow_cards = total_yellow
                profile.total_red_cards = total_red
                profile.avg_yellow_cards = avg_yellow
                profile.avg_red_cards = avg_red
                profile.severity_label = severity_label
                profile.sample_quality = sample_quality
                profile.calculated_at = calculated_at
                profile.raw_payload = {**raw_payload, **coverage}
                db.commit()

                result = {
                    "status": "success",
                    "profile_label": profile_label,
                    "referee_name": resolved_name,
                    "referee_id": int(ref_row.id),
                    "league_id": league_api_id,
                    "season": int(season_year),
                    "matches_count": counted,
                    "total_yellow_cards": total_yellow,
                    "total_red_cards": total_red,
                    "avg_yellow_cards": avg_yellow,
                    "avg_red_cards": avg_red,
                    "severity_label": severity_label,
                    "sample_quality": sample_quality,
                    "data_source": data_source,
                    "calculated_at": calculated_at.isoformat(),
                    "fixtures_used": fixtures_used,
                    "saved": True,
                    **coverage,
                }
                if severity_notes:
                    result["severity_notes"] = severity_notes
                if counted <= SAMPLE_LOW_MAX:
                    result["message"] = "Campione basso: importa storico stagione per ampliare"
                return result

        coverage_empty = self._coverage_metadata(
            db,
            league_api_id=league_api_id,
            season_year=int(season_year),
            referee=ref_row,
            referee_name=resolved_name,
            cache_rows=[],
            fixtures_with_card_data=0,
        )
        return {
            "status": "success",
            "profile_label": profile_label,
            "referee_name": resolved_name,
            "referee_id": int(ref_row.id) if ref_row else None,
            "league_id": league_api_id,
            "season": int(season_year),
            "matches_count": 0,
            "avg_yellow_cards": None,
            "avg_red_cards": None,
            "severity_label": None,
            "sample_quality": SAMPLE_QUALITY_LOW,
            "data_source": "db_only",
            "message": "Nessun dato in cache: esegui «Importa storico stagione»",
            "fixtures_used": [],
            "saved": False,
            **coverage_empty,
        }

    def recent_history(
        self,
        db: Session,
        *,
        referee_name: str,
        limit: int = 20,
    ) -> dict[str, Any]:
        ref_row = self._referee_by_name(db, referee_name)
        if ref_row is None:
            return {
                "status": "error",
                "message": f"Arbitro «{referee_name}» non in anagrafica",
            }

        rows = list(
            db.scalars(
                select(RefereeFixtureCardSummary)
                .where(RefereeFixtureCardSummary.referee_id == int(ref_row.id))
                .order_by(RefereeFixtureCardSummary.kickoff_at.desc())
                .limit(int(limit)),
            ).all(),
        )

        if not rows:
            return {
                "status": "success",
                "profile_label": f"Ultime {limit} disponibili",
                "referee_name": referee_name,
                "last_matches_count": 0,
                "message": "Storico recente non ancora importato. Importa prima le competizioni/fixture disponibili.",
                "data_source": "db_only",
            }

        agg = aggregate_card_rows(rows)
        competitions = sorted({int(r.league_api_id) for r in rows})
        sev, notes = classify_severity(agg["avg_yellow_cards"], agg["avg_red_cards"])
        mc = agg["matches_count"]
        return {
            "status": "success",
            "profile_label": f"Ultime {limit} disponibili",
            "referee_name": referee_name,
            "referee_id": int(ref_row.id),
            "last_matches_count": mc,
            "matches_count": mc,
            "avg_yellow_cards": agg["avg_yellow_cards"],
            "avg_red_cards": agg["avg_red_cards"],
            "severity_label": sev,
            "sample_quality": sample_quality_from_count(mc),
            "competitions_included": competitions,
            "data_source": agg["data_source"],
            "fixtures_used": [card_summary_to_dict(r) for r in rows],
            "severity_notes": notes or None,
        }


def build_referee_summary_for_fixture(db: Session, fixture_id: int) -> dict[str, Any]:
    """Blocco read-only per dettaglio upcoming (no chiamate API)."""
    from app.services.referee_match_context_service import RefereeMatchContextService

    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {"available": False, "message": "Fixture non trovata"}

    settings = get_settings()
    league = db.get(League, int(fx.league_id))
    league_api_id = int(league.api_league_id) if league else int(settings.default_league_id)
    season_row = db.get(Season, int(fx.season_id))
    season_year = int(season_row.year) if season_row else int(settings.default_season)

    link = db.scalar(
        select(FixtureReferee).where(FixtureReferee.fixture_id == int(fx.id)).order_by(FixtureReferee.id.desc()),
    )
    referee_name = (link.referee_name if link and link.referee_name else None) or fx.referee
    if not referee_name:
        return {"available": False, "message": "Arbitro non ancora assegnato per questa partita"}

    ref_id = int(link.referee_id) if link and link.referee_id else None
    if ref_id is None:
        ref = db.scalar(select(Referee).where(Referee.normalized_name == normalize_referee_name(referee_name)))
        ref_id = int(ref.id) if ref else None

    base: dict[str, Any] = {
        "available": True,
        "referee_name": referee_name,
        "profile_available": False,
    }

    if ref_id:
        profile = db.scalar(
            select(RefereeSeasonProfile).where(
                RefereeSeasonProfile.referee_id == ref_id,
                RefereeSeasonProfile.league_id == league_api_id,
                RefereeSeasonProfile.season == season_year,
            ),
        )
        if profile:
            raw = profile.raw_payload or {}
            base["profile_available"] = True
            base["season_profile"] = {
                "label": _league_profile_label(league_api_id, season_year),
                "matches_count": profile.matches_count,
                "avg_yellow_cards": profile.avg_yellow_cards,
                "avg_red_cards": profile.avg_red_cards,
                "severity_label": profile.severity_label,
                "sample_quality": profile.sample_quality,
                "data_source": raw.get("data_source"),
                "coverage_note": raw.get("coverage_note"),
            }
        else:
            base["message"] = "Profilo stagione non in cache: calcola o importa storico"

        ctx = RefereeMatchContextService().build_match_context(db, fixture_id=int(fixture_id))
        if ctx.get("status") == "success":
            base["home_team_context"] = ctx.get("home_team_context")
            base["away_team_context"] = ctx.get("away_team_context")
            base["direct_h2h_context"] = ctx.get("direct_h2h_context")
    else:
        base["message"] = "Profilo severità non calcolato: usa il Catalogo dati"

    return base
