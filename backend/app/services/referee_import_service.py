"""Import manuale storico arbitro per stagione/league da API-Sports."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureReferee, Referee
from app.models.fixture_referee import SOURCE_API_SPORTS
from app.models.referee import PROVIDER_API_SPORTS
from app.models.referee_fixture_card_summary import RefereeFixtureCardSummary
from app.services.api_football_client import ApiFootballClient, ApiFootballError
from app.services.api_football_fixture_detail import _parse_dt, parse_fixture_detail_item
from app.services.referee_cards_resolver import resolve_cards_for_api_fixture
from app.services.referee_name_normalize import compare_referee_names, normalize_referee_name

MAX_CARD_FETCHES_PER_RUN = 50


class RefereeImportService:
    def __init__(self, client: ApiFootballClient | None = None) -> None:
        self._client = client or ApiFootballClient()

    def _get_or_create_referee(self, db: Session, name: str) -> Referee:
        norm = normalize_referee_name(name)
        row = db.scalar(
            select(Referee).where(
                Referee.provider == PROVIDER_API_SPORTS,
                Referee.normalized_name == norm,
            ),
        )
        if row is None:
            row = Referee(
                provider=PROVIDER_API_SPORTS,
                name=name.strip(),
                normalized_name=norm,
            )
            db.add(row)
            db.flush()
        else:
            row.name = name.strip()
        return row

    def _upsert_card_summary(
        self,
        db: Session,
        *,
        referee_id: int,
        api_fixture_id: int,
        fixture_id: int | None,
        league_api_id: int,
        season_year: int,
        detail: dict[str, Any],
        cards: Any,
        card_source: str,
    ) -> RefereeFixtureCardSummary:
        row = db.scalar(
            select(RefereeFixtureCardSummary).where(
                RefereeFixtureCardSummary.api_fixture_id == int(api_fixture_id),
            ),
        )
        if row is None:
            row = RefereeFixtureCardSummary(
                api_fixture_id=int(api_fixture_id),
                referee_id=int(referee_id),
                league_api_id=int(league_api_id),
                season_year=int(season_year),
            )
            db.add(row)
        row.fixture_id = fixture_id
        row.referee_id = int(referee_id)
        row.league_api_id = int(league_api_id)
        row.season_year = int(season_year)
        row.home_team_api_id = detail.get("home_team_api_id")
        row.away_team_api_id = detail.get("away_team_api_id")
        row.home_team_name = detail.get("home_team_name")
        row.away_team_name = detail.get("away_team_name")
        row.kickoff_at = detail.get("kickoff_at")
        row.total_yellow = cards.total_yellow
        row.total_red = cards.total_red
        row.home_yellow = cards.home_yellow
        row.home_red = cards.home_red
        row.away_yellow = cards.away_yellow
        row.away_red = cards.away_red
        row.card_source = card_source
        row.raw_payload = {"imported_at": datetime.now(timezone.utc).isoformat()}
        return row

    def import_season_history(
        self,
        db: Session,
        *,
        referee_name: str,
        league_id: int,
        season: int,
    ) -> dict[str, Any]:
        target = referee_name.strip()
        ref_row = self._get_or_create_referee(db, target)
        match_warnings: list[str] = []

        try:
            items = self._client.get_fixtures(int(league_id), int(season), status="FT")
        except ApiFootballError as exc:
            return {"status": "error", "message": str(exc)}

        fixtures_scanned = len(items)
        referee_matches: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            detail = parse_fixture_detail_item(item)
            api_ref = detail.get("referee")
            cmp = compare_referee_names(api_ref, target)
            if not cmp.matches:
                continue
            if cmp.match_warning:
                match_warnings.append(cmp.match_warning)
            referee_matches.append(detail)

        referee_matches_found = len(referee_matches)
        fixtures_imported = 0
        card_data_found = 0
        api_fetches = 0
        errors: list[dict[str, str]] = []

        for detail in referee_matches:
            api_id = detail.get("api_fixture_id")
            if api_id is None:
                continue
            api_id = int(api_id)
            db_fx = db.scalar(select(Fixture).where(Fixture.api_fixture_id == api_id))
            fixture_id = int(db_fx.id) if db_fx else None

            if db_fx is not None:
                db_fx.referee = str(detail.get("referee") or target)[:255]
                link = db.scalar(
                    select(FixtureReferee).where(
                        FixtureReferee.fixture_id == int(db_fx.id),
                        FixtureReferee.source == SOURCE_API_SPORTS,
                    ),
                )
                if link is None:
                    link = FixtureReferee(
                        fixture_id=int(db_fx.id),
                        api_fixture_id=api_id,
                        source=SOURCE_API_SPORTS,
                    )
                    db.add(link)
                link.referee_id = int(ref_row.id)
                link.referee_name = detail.get("referee") or target
                kickoff = detail.get("kickoff_at")
                if isinstance(kickoff, str):
                    kickoff = _parse_dt(kickoff)
                link.assigned_at = kickoff
                fixtures_imported += 1

            cards = None
            card_source = None
            existing = db.scalar(
                select(RefereeFixtureCardSummary).where(
                    RefereeFixtureCardSummary.api_fixture_id == api_id,
                ),
            )
            if existing and existing.total_yellow is not None:
                card_data_found += 1
                continue

            if api_fetches < MAX_CARD_FETCHES_PER_RUN:
                api_fetches += 1
                try:
                    cards, card_source = resolve_cards_for_api_fixture(
                        self._client,
                        api_fixture_id=api_id,
                        home_team_api_id=detail.get("home_team_api_id"),
                        away_team_api_id=detail.get("away_team_api_id"),
                        db=db,
                        fixture_id=fixture_id,
                    )
                except Exception as exc:
                    errors.append({"api_fixture_id": str(api_id), "error": str(exc)})
                    continue
            else:
                errors.append(
                    {
                        "api_fixture_id": str(api_id),
                        "error": f"Limite fetch API ({MAX_CARD_FETCHES_PER_RUN}) raggiunto; rieseguire import",
                    },
                )
                continue

            if cards is None or not cards.has_data():
                continue

            self._upsert_card_summary(
                db,
                referee_id=int(ref_row.id),
                api_fixture_id=api_id,
                fixture_id=fixture_id,
                league_api_id=int(league_id),
                season_year=int(season),
                detail=detail,
                cards=cards,
                card_source=card_source or "statistics",
            )
            card_data_found += 1

        db.commit()
        result: dict[str, Any] = {
            "status": "success",
            "referee_name": target,
            "referee_id": int(ref_row.id),
            "league_id": int(league_id),
            "season": int(season),
            "fixtures_scanned": fixtures_scanned,
            "referee_matches_found": referee_matches_found,
            "fixtures_imported": fixtures_imported,
            "card_data_found": card_data_found,
            "api_fetches_used": api_fetches,
            "errors": errors,
        }
        if match_warnings:
            result["match_warning"] = match_warnings[0]
        if api_fetches >= MAX_CARD_FETCHES_PER_RUN and referee_matches_found > card_data_found:
            result["message"] = (
                f"Import parziale: recuperati cartellini per {card_data_found} partite "
                f"(max {MAX_CARD_FETCHES_PER_RUN} chiamate API per esecuzione). Rieseguire per il resto."
            )
        return result
