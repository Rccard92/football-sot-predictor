"""Backfill mapping fixture SportAPI per round/fixture finished (Step K.3)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.schemas.sportapi_fixture_mapping_backfill import (
    SportApiFixtureMappingBackfillItem,
    SportApiFixtureMappingBackfillResponse,
)
from app.schemas.sportapi_fixture_mapping_debug import SportApiMappingCandidateBrief
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.sportapi.sportapi_fixture_mapping_discovery import SportApiFixtureMappingDiscovery
from app.services.sportapi.sportapi_fixture_mapping_scoring import (
    ScoredMappingCandidate,
    effective_confidence,
)
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService

_SAMPLE_LIMIT = 10


def _candidate_brief(c: ScoredMappingCandidate | None) -> SportApiMappingCandidateBrief | None:
    if c is None:
        return None
    return SportApiMappingCandidateBrief(
        provider_event_id=c.provider_event_id,
        score=c.score,
        confidence=c.confidence,
        home_team_name=c.home_team_name,
        away_team_name=c.away_team_name,
        start_timestamp=c.start_timestamp,
        round_number=c.round_number,
        tournament_name=c.tournament_name,
        breakdown=dict(c.breakdown),
    )


MATCHED_BY = "sportapi_fixture_discovery"


class SportApiFixtureMappingBackfillService:
    def __init__(
        self,
        discovery: SportApiFixtureMappingDiscovery | None = None,
        lineup_svc: SportApiLineupService | None = None,
    ) -> None:
        self._discovery = discovery or SportApiFixtureMappingDiscovery()
        self._lineup_svc = lineup_svc or SportApiLineupService()

    def backfill(
        self,
        db: Session,
        *,
        competition_id: int,
        round_number: int | None = None,
        fixture_ids: list[int] | None = None,
        dry_run: bool = True,
        force_refresh: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> SportApiFixtureMappingBackfillResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            return SportApiFixtureMappingBackfillResponse(
                status="error",
                dry_run=bool(dry_run),
                competition_id=int(competition_id),
                competition_name="",
                round_number=round_number,
                warnings=[f"Competition {competition_id} not found"],
            )

        if fixture_ids:
            unique_ids = list(dict.fromkeys(int(x) for x in fixture_ids))
            fixtures = list(
                db.scalars(
                    select(Fixture).where(
                        Fixture.id.in_(unique_ids),
                        Fixture.competition_id == int(competition_id),
                    ),
                ).all(),
            )
        else:
            selection = BacktestFixtureDebugService().select_fixtures_for_mini_run(
                db,
                competition_id=int(competition_id),
                limit=int(limit),
                offset=int(offset),
                round_number=round_number,
            )
            fixtures = [
                db.get(Fixture, int(c.fixture_id))
                for c in selection.items
                if db.get(Fixture, int(c.fixture_id)) is not None
            ]

        existing_count = 0
        high_count = 0
        medium_count = 0
        low_count = 0
        written_count = 0
        ambiguous_count = 0
        fetch_errors = 0
        items: list[SportApiFixtureMappingBackfillItem] = []
        warnings: list[str] = []

        for fixture in fixtures:
            if fixture is None:
                continue
            fid = int(fixture.id)
            home = db.get(Team, int(fixture.home_team_id))
            away = db.get(Team, int(fixture.away_team_id))
            home_name = home.name if home else str(fixture.home_team_id)
            away_name = away.name if away else str(fixture.away_team_id)

            mapping = db.scalar(
                select(FixtureProviderMapping).where(
                    FixtureProviderMapping.fixture_id == fid,
                    FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                ),
            )
            has_existing = mapping is not None
            if has_existing and not force_refresh:
                existing_count += 1
                if len(items) < _SAMPLE_LIMIT:
                    items.append(
                        SportApiFixtureMappingBackfillItem(
                            fixture_id=fid,
                            round=fixture.round,
                            home_team=home_name,
                            away_team=away_name,
                            existing_mapping=True,
                            match_confidence="high",
                            warnings=["Mapping esistente — skip"],
                        ),
                    )
                continue

            discovery = self._discovery.discover_for_fixture(db, fixture=fixture, competition=comp)
            item_warnings = list(discovery.get("warnings") or [])

            if discovery.get("status") != "ok":
                fetch_errors += 1
                msg = str(discovery.get("message") or "Discovery fallita")
                item_warnings.append(msg)
                if len(items) < _SAMPLE_LIMIT:
                    items.append(
                        SportApiFixtureMappingBackfillItem(
                            fixture_id=fid,
                            round=fixture.round,
                            home_team=home_name,
                            away_team=away_name,
                            existing_mapping=has_existing,
                            warnings=item_warnings,
                        ),
                    )
                continue

            best: ScoredMappingCandidate | None = discovery.get("best")
            ambiguous = bool(discovery.get("ambiguous_high"))
            confidence = effective_confidence(best, ambiguous=ambiguous)

            if ambiguous:
                ambiguous_count += 1
            if confidence == "high":
                high_count += 1
            elif confidence == "medium":
                medium_count += 1
            elif confidence == "low":
                low_count += 1

            would_write = (
                not dry_run
                and confidence == "high"
                and not ambiguous
                and best is not None
            )
            mapping_written = False

            if confidence in ("medium", "low"):
                item_warnings.append(f"Confidence {confidence}: auto-save non consentito")

            if would_write and best is not None:
                result = self._lineup_svc.confirm_mapping(
                    db,
                    fid,
                    provider_event_id=int(best.provider_event_id),
                    confidence_score=float(best.score),
                    matched_by=MATCHED_BY,
                    raw_payload=best.raw_event,
                    expected_competition_id=int(competition_id),
                )
                if result.get("status") == "success":
                    mapping_written = True
                    written_count += 1
                else:
                    item_warnings.append(str(result.get("message") or "confirm_mapping fallito"))

            if len(items) < _SAMPLE_LIMIT:
                items.append(
                    SportApiFixtureMappingBackfillItem(
                        fixture_id=fid,
                        round=fixture.round,
                        home_team=home_name,
                        away_team=away_name,
                        existing_mapping=has_existing,
                        match_confidence=confidence,
                        ambiguous_high_matches=ambiguous,
                        best_candidate=_candidate_brief(best),
                        would_write_mapping=would_write,
                        mapping_written=mapping_written,
                        warnings=item_warnings,
                    ),
                )

        return SportApiFixtureMappingBackfillResponse(
            status="ok",
            dry_run=bool(dry_run),
            competition_id=int(competition_id),
            competition_name=comp.name,
            round_number=round_number,
            fixtures_processed=len([f for f in fixtures if f is not None]),
            existing_mappings=existing_count,
            high_confidence_matches=high_count,
            medium_confidence_matches=medium_count,
            low_confidence_matches=low_count,
            written_mappings=written_count,
            ambiguous_matches=ambiguous_count,
            fetch_errors=fetch_errors,
            items=items,
            warnings=warnings,
        )
