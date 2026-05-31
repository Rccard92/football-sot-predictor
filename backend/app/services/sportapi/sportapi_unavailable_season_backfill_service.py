"""Backfill indisponibili SportAPI per stagione (Step K.4)."""

from __future__ import annotations

import time

from sqlalchemy.orm import Session

from app.models import Competition, Fixture, Team
from app.schemas.sportapi_unavailable_backfill import (
    SportApiUnavailableBackfillFixtureSample,
)
from app.schemas.sportapi_unavailable_season_backfill import (
    SportApiUnavailableSeasonBackfillResponse,
)
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.sportapi.sportapi_unavailable_backfill_service import (
    SportApiUnavailableBackfillService,
)

_SAMPLE_LIMIT = 10


class SportApiUnavailableSeasonBackfillService:
    def __init__(
        self,
        round_svc: SportApiUnavailableBackfillService | None = None,
    ) -> None:
        self._round_svc = round_svc or SportApiUnavailableBackfillService()

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
    ) -> SportApiUnavailableSeasonBackfillResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            return SportApiUnavailableSeasonBackfillResponse(
                status="error",
                dry_run=bool(dry_run),
                competition_id=int(competition_id),
                competition_name="",
                warnings=[f"Competition {competition_id} not found"],
            )

        selection = BacktestFixtureDebugService().select_mapped_fixtures_for_sportapi_unavailable_season(
            db,
            competition_id=int(competition_id),
            only_finished=only_finished,
            round_from=round_from,
            round_to=round_to,
            limit=int(limit),
            offset=int(offset),
        )

        total_found = 0
        total_written = 0
        skipped_provider_id = 0
        with_unavailable = 0
        fetch_errors = 0
        api_calls = 0
        source_paths: set[str] = set()
        samples: list[SportApiUnavailableBackfillFixtureSample] = []
        warnings: list[str] = []

        for candidate in selection.items:
            if sleep_between_fixtures_s and sleep_between_fixtures_s > 0:
                time.sleep(float(sleep_between_fixtures_s))

            fixture = db.get(Fixture, int(candidate.fixture_id))
            if fixture is None:
                continue

            fid = int(fixture.id)
            home = db.get(Team, int(fixture.home_team_id))
            away = db.get(Team, int(fixture.away_team_id))

            result = self._round_svc._process_one_fixture(  # noqa: SLF001
                db,
                comp=comp,
                fixture=fixture,
                dry_run=dry_run,
                force_refresh=force_refresh,
                auto_confirm_mapping=False,
            )

            total_found += int(result.get("found") or 0)
            total_written += int(result.get("written") or 0)
            skipped_provider_id += int(result.get("skipped_provider_id") or 0)
            api_calls += int(result.get("api_calls") or 0)
            if int(result.get("found") or 0) > 0:
                with_unavailable += 1
            if result.get("fetch_error"):
                fetch_errors += 1
            for p in result.get("detected_paths") or []:
                source_paths.add(str(p))
            sample = result.get("sample")
            if sample is not None and len(samples) < _SAMPLE_LIMIT:
                samples.append(sample)
            warnings.extend(result.get("warnings") or [])

        has_more = (int(offset) + int(limit)) < int(selection.total_candidates)

        return SportApiUnavailableSeasonBackfillResponse(
            status="ok",
            dry_run=bool(dry_run),
            competition_id=int(competition_id),
            competition_name=comp.name,
            fixtures_processed=len(selection.items),
            total_candidates=int(selection.total_candidates),
            has_more=has_more,
            fixtures_with_mapping=len(selection.items),
            fixtures_mapping_missing=0,
            fixtures_with_unavailable_from_provider=with_unavailable,
            total_unavailable_found=total_found,
            total_written=total_written,
            skipped_missing_provider_player_id=skipped_provider_id,
            fetch_errors=fetch_errors,
            api_calls=api_calls,
            source_paths_found=sorted(source_paths),
            samples=sorted(samples, key=lambda s: s.unavailable_found, reverse=True)[:_SAMPLE_LIMIT],
            warnings=warnings[:20],
        )
