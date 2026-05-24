"""Calcolo profilo severità arbitro da cartellini (DB + API-Sports)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
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
from app.models.referee_season_profile import (
    SAMPLE_QUALITY_HIGH,
    SAMPLE_QUALITY_LOW,
    SAMPLE_QUALITY_MEDIUM,
)
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.referee_cards_parser import (
    match_cards_from_statistics_blocks_using_mapping,
    match_cards_from_team_stats_rows,
)
from app.services.referee_name_normalize import normalize_referee_name, referee_names_match


def classify_severity(avg_yellow: float | None, avg_red: float | None) -> tuple[str, dict[str, Any]]:
    """Classifica severità e note aggiuntive."""
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
        return SAMPLE_QUALITY_LOW
    if matches_count < SAMPLE_HIGH_MIN:
        return SAMPLE_QUALITY_MEDIUM
    return SAMPLE_QUALITY_HIGH


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
        return db.scalar(
            select(Referee).where(Referee.normalized_name == norm).order_by(Referee.id.asc()),
        )

    def _finished_fixtures_for_referee(
        self,
        db: Session,
        *,
        referee: Referee | None,
        referee_name: str,
        league_api_id: int,
        season_year: int,
    ) -> list[Fixture]:
        league = db.scalar(select(League).where(League.api_league_id == int(league_api_id)))
        if league is None:
            return []
        season = db.scalar(
            select(Season).where(Season.league_id == int(league.id), Season.year == int(season_year)),
        )
        if season is None:
            return []

        norm = normalize_referee_name(referee_name)
        q = (
            select(Fixture)
            .where(
                Fixture.season_id == int(season.id),
                Fixture.status.in_(list(FINISHED_STATUSES)),
            )
            .order_by(Fixture.kickoff_at.desc())
        )
        rows = list(db.scalars(q).all())
        out: list[Fixture] = []
        ref_id = int(referee.id) if referee else None
        for fx in rows:
            if ref_id is not None:
                link = db.scalar(
                    select(FixtureReferee).where(
                        FixtureReferee.fixture_id == int(fx.id),
                        FixtureReferee.referee_id == ref_id,
                    ),
                )
                if link:
                    out.append(fx)
                    continue
            if referee_names_match(fx.referee, referee_name):
                out.append(fx)
        return out

    def _api_finished_fixture_ids(
        self,
        *,
        league_api_id: int,
        season_year: int,
        referee_name: str,
        existing_api_ids: set[int],
    ) -> list[int]:
        try:
            items = self._client.get_fixtures(int(league_api_id), int(season_year), status="FT")
        except ApiFootballError:
            return []
        extra: list[int] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            fx = item.get("fixture") or {}
            ref = fx.get("referee")
            if not referee_names_match(str(ref) if ref else None, referee_name):
                continue
            api_id = fx.get("id")
            if api_id is None:
                continue
            aid = int(api_id)
            if aid not in existing_api_ids:
                extra.append(aid)
        return extra

    def _team_stats_pair(self, db: Session, fixture_id: int) -> tuple[Any | None, Any | None]:
        rows = list(
            db.scalars(select(FixtureTeamStat).where(FixtureTeamStat.fixture_id == int(fixture_id))).all(),
        )
        if len(rows) < 2:
            home_row = rows[0] if rows else None
            return home_row, None
        by_side = {str(r.side or "").lower(): r for r in rows}
        home = by_side.get("home") or rows[0]
        away = by_side.get("away") or rows[1]
        return home, away

    def _cards_for_fixture(self, db: Session, fx: Fixture) -> tuple[int | None, int | None]:
        home_row, away_row = self._team_stats_pair(db, int(fx.id))
        cards = match_cards_from_team_stats_rows(home_row, away_row)
        yellow = cards.yellow_cards
        red = cards.red_cards_total if cards.red_cards_total is not None else cards.red_cards

        if yellow is not None and red is not None:
            return yellow, red

        try:
            blocks = self._client.get_fixture_statistics(int(fx.api_fixture_id))
        except ApiFootballError:
            return yellow, red

        api_cards = match_cards_from_statistics_blocks_using_mapping(blocks)
        if yellow is None:
            yellow = api_cards.yellow_cards
        if red is None:
            red = api_cards.red_cards_total if api_cards.red_cards_total is not None else api_cards.red_cards
        return yellow, red

    def _match_label(self, db: Session, fx: Fixture) -> str:
        home = db.get(Team, int(fx.home_team_id))
        away = db.get(Team, int(fx.away_team_id))
        return f"{home.name if home else 'Casa'} - {away.name if away else 'Trasferta'}"

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

        fixtures = self._finished_fixtures_for_referee(
            db,
            referee=ref_row,
            referee_name=resolved_name,
            league_api_id=league_api_id,
            season_year=int(season_year),
        )

        existing_api_ids = {int(f.api_fixture_id) for f in fixtures}
        api_extra_ids = self._api_finished_fixture_ids(
            league_api_id=league_api_id,
            season_year=int(season_year),
            referee_name=resolved_name,
            existing_api_ids=existing_api_ids,
        )

        fixtures_used: list[dict[str, Any]] = []
        total_yellow = 0
        total_red = 0
        counted = 0

        cap = int(max_matches) if max_matches is not None and max_matches > 0 else None
        candidate_fixtures = fixtures[: cap] if cap else fixtures

        for fx in candidate_fixtures:
            yellow, red = self._cards_for_fixture(db, fx)
            if yellow is None and red is None:
                continue
            y = int(yellow or 0)
            r = int(red or 0)
            total_yellow += y
            total_red += r
            counted += 1
            fixtures_used.append(
                {
                    "fixture_id": int(fx.id),
                    "api_fixture_id": int(fx.api_fixture_id),
                    "match": self._match_label(db, fx),
                    "date": fx.kickoff_at.isoformat() if fx.kickoff_at else None,
                    "yellow_cards": y,
                    "red_cards": r,
                },
            )

        if cap is None and api_extra_ids and counted < SAMPLE_HIGH_MIN:
            for api_id in api_extra_ids[:20]:
                try:
                    blocks = self._client.get_fixture_statistics(api_id)
                except ApiFootballError:
                    continue
                cards = match_cards_from_statistics_blocks_using_mapping(blocks)
                if cards.yellow_cards is None and cards.red_cards is None:
                    continue
                y = int(cards.yellow_cards or 0)
                r = int(cards.red_cards or 0)
                total_yellow += y
                total_red += r
                counted += 1
                fixtures_used.append(
                    {
                        "fixture_id": None,
                        "api_fixture_id": api_id,
                        "match": f"API fixture {api_id}",
                        "date": None,
                        "yellow_cards": y,
                        "red_cards": r,
                        "source": "api_supplement",
                    },
                )

        if counted == 0:
            return {
                "status": "success",
                "referee_name": resolved_name,
                "referee_id": int(ref_row.id) if ref_row else None,
                "league_id": league_api_id,
                "season": int(season_year),
                "matches_count": 0,
                "avg_yellow_cards": None,
                "avg_red_cards": None,
                "severity_label": None,
                "sample_quality": SAMPLE_QUALITY_LOW,
                "message": "Campione insufficiente: nessuna partita finita con cartellini disponibili",
                "fixtures_used": [],
                "saved": False,
            }

        avg_yellow = round(total_yellow / counted, 2)
        avg_red = round(total_red / counted, 2)
        severity_label, severity_notes = classify_severity(avg_yellow, avg_red)
        sample_quality = sample_quality_from_count(counted)
        calculated_at = datetime.now(timezone.utc)

        raw_payload: dict[str, Any] = {
            "fixtures_used": fixtures_used,
            "severity_notes": severity_notes,
            "thresholds": {
                "yellow_permissive_max": SEVERITY_YELLOW_PERMISSIVE_MAX,
                "yellow_medium_max": SEVERITY_YELLOW_MEDIUM_MAX,
                "red_incidence_note": RED_INCIDENCE_NOTE_THRESHOLD,
            },
        }

        saved = False
        if ref_row is not None:
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
            profile.raw_payload = raw_payload
            db.commit()
            saved = True

        result: dict[str, Any] = {
            "status": "success",
            "referee_name": resolved_name,
            "referee_id": int(ref_row.id) if ref_row else None,
            "league_id": league_api_id,
            "season": int(season_year),
            "matches_count": counted,
            "total_yellow_cards": total_yellow,
            "total_red_cards": total_red,
            "avg_yellow_cards": avg_yellow,
            "avg_red_cards": avg_red,
            "severity_label": severity_label,
            "sample_quality": sample_quality,
            "calculated_at": calculated_at.isoformat(),
            "fixtures_used": fixtures_used,
            "saved": saved,
        }
        if severity_notes:
            result["severity_notes"] = severity_notes
        if sample_quality == SAMPLE_QUALITY_LOW:
            result["message"] = "Campione basso: interpretare il profilo con cautela"
        return result


def build_referee_summary_for_fixture(db: Session, fixture_id: int) -> dict[str, Any]:
    """Blocco read-only per dettaglio upcoming."""
    fx = db.get(Fixture, int(fixture_id))
    if fx is None:
        return {"available": False, "message": "Fixture non trovata"}

    settings = get_settings()
    league = db.get(League, int(fx.league_id))
    league_api_id = int(league.api_league_id) if league else int(settings.default_league_id)
    season_row = db.get(Season, int(fx.season_id))
    season_year = int(season_row.year) if season_row else int(settings.default_season)

    link = db.scalar(
        select(FixtureReferee)
        .where(FixtureReferee.fixture_id == int(fx.id))
        .order_by(FixtureReferee.id.desc()),
    )
    referee_name = (link.referee_name if link and link.referee_name else None) or fx.referee
    if not referee_name:
        return {
            "available": False,
            "message": "Arbitro non ancora assegnato per questa partita",
        }

    ref_id = int(link.referee_id) if link and link.referee_id else None
    if ref_id is None:
        ref = db.scalar(
            select(Referee).where(Referee.normalized_name == normalize_referee_name(referee_name)),
        )
        ref_id = int(ref.id) if ref else None

    if ref_id is None:
        return {
            "available": True,
            "referee_name": referee_name,
            "profile_available": False,
            "message": "Profilo severità non calcolato: usa il Catalogo dati per generarlo",
        }

    profile = db.scalar(
        select(RefereeSeasonProfile)
        .where(
            RefereeSeasonProfile.referee_id == ref_id,
            RefereeSeasonProfile.league_id == league_api_id,
            RefereeSeasonProfile.season == season_year,
        )
        .order_by(RefereeSeasonProfile.calculated_at.desc()),
    )
    if profile is None:
        return {
            "available": True,
            "referee_name": referee_name,
            "profile_available": False,
            "message": "Profilo severità non ancora in cache",
        }

    return {
        "available": True,
        "profile_available": True,
        "referee_name": referee_name,
        "avg_yellow_cards": profile.avg_yellow_cards,
        "avg_red_cards": profile.avg_red_cards,
        "severity_label": profile.severity_label,
        "sample_quality": profile.sample_quality,
        "matches_count": profile.matches_count,
    }
