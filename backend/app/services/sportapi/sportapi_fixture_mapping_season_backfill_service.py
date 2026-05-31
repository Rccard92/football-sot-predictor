"""Backfill mapping fixture SportAPI per stagione (Step K.4)."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.schemas.sportapi_fixture_mapping_backfill import SportApiFixtureMappingBackfillItem
from app.schemas.sportapi_fixture_mapping_season_backfill import (
    SportApiFixtureMappingSeasonBackfillResponse,
)
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.sportapi.sportapi_fixture_mapping_backfill_service import (
    MATCHED_BY,
    _candidate_brief,
)
from app.services.sportapi.sportapi_fixture_mapping_discovery import SportApiFixtureMappingDiscovery
from app.services.sportapi.sportapi_fixture_mapping_scoring import (
    ScoredMappingCandidate,
    effective_confidence,
)
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService

_SAMPLE_LIMIT = 10


class SportApiFixtureMappingSeasonBackfillService:
    def __init__(
        self,
        discovery: SportApiFixtureMappingDiscovery | None = None,
        lineup_svc: SportApiLineupService | None = None,
    ) -> None:
        self._discovery = discovery or SportApiFixtureMappingDiscovery()
        self._lineup_svc = lineup_svc or SportApiLineupService()

    def backfill_season(
        self,
        db: Session,
        *,
        competition_id: int,
        dry_run: bool = True,
        force_refresh: bool = False,
        only_finished: bool = True,
        limit: int = 400,
        offset: int = 0,
        round_from: int | None = None,
        round_to: int | None = None,
        sleep_between_fixtures_s: float | None = None,
    ) -> SportApiFixtureMappingSeasonBackfillResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            return SportApiFixtureMappingSeasonBackfillResponse(
                status="error",
                dry_run=bool(dry_run),
                competition_id=int(competition_id),
                competition_name="",
                warnings=[f"Competition {competition_id} not found"],
            )

        selection = BacktestFixtureDebugService().select_fixtures_for_sportapi_season_backfill(
            db,
            competition_id=int(competition_id),
            only_finished=only_finished,
            round_from=round_from,
            round_to=round_to,
            limit=int(limit),
            offset=int(offset),
            require_sot_stats=False,
        )
        fixtures = [
            db.get(Fixture, int(c.fixture_id))
            for c in selection.items
            if db.get(Fixture, int(c.fixture_id)) is not None
        ]

        by_date: dict[str, list[Fixture]] = defaultdict(list)
        for fixture in fixtures:
            if fixture is None or fixture.kickoff_at is None:
                continue
            kickoff = fixture.kickoff_at
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            match_date = kickoff.astimezone(timezone.utc).date().isoformat()
            by_date[match_date].append(fixture)

        api_calls = 0
        events_by_date: dict[str, list] = {}
        for match_date in by_date:
            events, calls = self._discovery.fetch_scheduled_events_for_date(match_date)
            events_by_date[match_date] = events
            api_calls += calls

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
            if sleep_between_fixtures_s and sleep_between_fixtures_s > 0:
                time.sleep(float(sleep_between_fixtures_s))

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

            if fixture.kickoff_at is None:
                fetch_errors += 1
                if len(items) < _SAMPLE_LIMIT:
                    items.append(
                        SportApiFixtureMappingBackfillItem(
                            fixture_id=fid,
                            round=fixture.round,
                            home_team=home_name,
                            away_team=away_name,
                            error="Fixture senza kickoff_at",
                        ),
                    )
                continue

            kickoff = fixture.kickoff_at
            if kickoff.tzinfo is None:
                kickoff = kickoff.replace(tzinfo=timezone.utc)
            match_date = kickoff.astimezone(timezone.utc).date().isoformat()
            cached = events_by_date.get(match_date, [])

            discovery = self._discovery.discover_for_fixture(
                db,
                fixture=fixture,
                competition=comp,
                cached_events=cached,
            )
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
                            error=msg,
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

            would_write_intent = (
                confidence == "high"
                and not ambiguous
                and best is not None
                and (not has_existing or force_refresh)
            )
            mapping_written = False

            if confidence in ("medium", "low"):
                item_warnings.append(f"Confidence {confidence}: auto-save non consentito")

            if would_write_intent and not dry_run and best is not None:
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
                        would_write_mapping=would_write_intent,
                        mapping_written=mapping_written,
                        warnings=item_warnings,
                    ),
                )

        has_more = (int(offset) + int(limit)) < int(selection.total_candidates)

        return SportApiFixtureMappingSeasonBackfillResponse(
            status="ok",
            dry_run=bool(dry_run),
            competition_id=int(competition_id),
            competition_name=comp.name,
            fixtures_processed=len([f for f in fixtures if f is not None]),
            total_candidates=int(selection.total_candidates),
            has_more=has_more,
            existing_mappings=existing_count,
            high_confidence_matches=high_count,
            medium_confidence_matches=medium_count,
            low_confidence_matches=low_count,
            written_mappings=written_count,
            ambiguous_matches=ambiguous_count,
            fetch_errors=fetch_errors,
            api_calls=api_calls,
            items_sample=items,
            warnings=warnings,
        )
