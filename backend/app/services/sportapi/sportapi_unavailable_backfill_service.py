"""Backfill indisponibili SportAPI per fixture finished (Step K.2)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, Fixture, Team
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.schemas.sportapi_unavailable_backfill import (
    SportApiUnavailableBackfillFixtureSample,
    SportApiUnavailableBackfillResponse,
)
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.sportapi.sportapi_lineup_service import SportApiLineupService
from app.services.sportapi.sportapi_matching_service import SportApiMatchingService
from app.services.sportapi.sportapi_unavailable_debug_service import SportApiUnavailableDebugService

_SAMPLE_LIMIT = 10


class SportApiUnavailableBackfillService:
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
        auto_confirm_mapping: bool = False,
    ) -> SportApiUnavailableBackfillResponse:
        comp = db.get(Competition, int(competition_id))
        if comp is None:
            return SportApiUnavailableBackfillResponse(
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

        debug_svc = SportApiUnavailableDebugService()
        lineup_svc = SportApiLineupService()
        match_svc = SportApiMatchingService()

        total_found = 0
        total_written = 0
        with_unavailable = 0
        mapping_missing = 0
        fetch_errors = 0
        samples: list[SportApiUnavailableBackfillFixtureSample] = []
        warnings: list[str] = []

        for fixture in fixtures:
            if fixture is None:
                continue
            fid = int(fixture.id)
            home = db.get(Team, int(fixture.home_team_id))
            away = db.get(Team, int(fixture.away_team_id))

            mapping = db.scalar(
                select(FixtureProviderMapping).where(
                    FixtureProviderMapping.fixture_id == fid,
                    FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                ),
            )
            mapping_status = "ok"

            if mapping is None:
                match_result = match_svc.match_fixture_for_competition(db, fid, comp)
                best = match_result.get("best_candidate")
                score = float(match_result.get("confidence_score") or 0)
                if best and score >= 90:
                    if auto_confirm_mapping and not dry_run:
                        lineup_svc.confirm_mapping(
                            db,
                            fid,
                            provider_event_id=int(best["provider_event_id"]),
                            confidence_score=score,
                            matched_by="auto_k2_backfill",
                            raw_payload=best.get("raw_event"),
                            expected_competition_id=int(competition_id),
                        )
                        mapping_status = "auto_confirmed"
                    else:
                        mapping_status = "match_found_not_confirmed"
                        mapping_missing += 1
                        warnings.append(
                            f"Fixture {fid}: mapping assente, match score={score:.1f} "
                            f"(auto_confirm_mapping={auto_confirm_mapping}, dry_run={dry_run})",
                        )
                        samples.append(
                            SportApiUnavailableBackfillFixtureSample(
                                fixture_id=fid,
                                round=fixture.round,
                                home_team=home.name if home else str(fixture.home_team_id),
                                away_team=away.name if away else str(fixture.away_team_id),
                                mapping_status=mapping_status,
                            ),
                        )
                        continue
                else:
                    mapping_status = "mapping_missing"
                    mapping_missing += 1
                    samples.append(
                        SportApiUnavailableBackfillFixtureSample(
                            fixture_id=fid,
                            round=fixture.round,
                            home_team=home.name if home else str(fixture.home_team_id),
                            away_team=away.name if away else str(fixture.away_team_id),
                            mapping_status=mapping_status,
                        ),
                    )
                    continue

            if not dry_run:
                fetch_out = lineup_svc.fetch_and_persist_lineups(db, fid)
                if fetch_out.get("status") != "success":
                    fetch_errors += 1
                    warnings.append(
                        f"Fixture {fid}: fetch failed — {fetch_out.get('message')}",
                    )
                    continue
                found = int(fetch_out.get("missing_players_saved") or 0)
                written = found
            else:
                debug_out = debug_svc.debug_fixture(
                    db,
                    fixture_id=fid,
                    competition_id=int(competition_id),
                    dry_run=True,
                    force_refresh=force_refresh,
                )
                if debug_out.status == "error":
                    fetch_errors += 1
                    continue
                found = int(debug_out.total_unavailable_found)
                written = 0
                total_found += found
                if found > 0:
                    with_unavailable += 1
                samples.append(
                    SportApiUnavailableBackfillFixtureSample(
                        fixture_id=fid,
                        round=fixture.round,
                        home_team=home.name if home else str(fixture.home_team_id),
                        away_team=away.name if away else str(fixture.away_team_id),
                        unavailable_found=found,
                        would_write=int(debug_out.would_write_count),
                        written=written,
                        mapping_status=mapping_status,
                        data_source=debug_out.data_source,
                        detected_paths=debug_out.detected_paths,
                    ),
                )
                continue

            total_found += found
            if found > 0:
                with_unavailable += 1
            total_written += written
            samples.append(
                SportApiUnavailableBackfillFixtureSample(
                    fixture_id=fid,
                    round=fixture.round,
                    home_team=home.name if home else str(fixture.home_team_id),
                    away_team=away.name if away else str(fixture.away_team_id),
                    unavailable_found=found,
                    would_write=found,
                    written=written,
                    mapping_status=mapping_status,
                    data_source="live",
                ),
            )
            continue

        samples = sorted(samples, key=lambda s: s.unavailable_found, reverse=True)[:_SAMPLE_LIMIT]

        return SportApiUnavailableBackfillResponse(
            status="ok",
            dry_run=bool(dry_run),
            competition_id=int(competition_id),
            competition_name=comp.name,
            round_number=round_number,
            fixtures_processed=len(fixtures),
            fixtures_with_unavailable_from_provider=with_unavailable,
            total_unavailable_found=total_found,
            total_written=total_written,
            mapping_missing_count=mapping_missing,
            fetch_errors=fetch_errors,
            samples=samples,
            warnings=warnings[:20],
        )
