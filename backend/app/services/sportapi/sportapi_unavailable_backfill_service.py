"""Backfill indisponibili SportAPI per fixture finished (Step K.2/K.4)."""

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
    def __init__(
        self,
        debug_svc: SportApiUnavailableDebugService | None = None,
        lineup_svc: SportApiLineupService | None = None,
        match_svc: SportApiMatchingService | None = None,
    ) -> None:
        self._debug_svc = debug_svc or SportApiUnavailableDebugService()
        self._lineup_svc = lineup_svc or SportApiLineupService()
        self._match_svc = match_svc or SportApiMatchingService()

    def _process_one_fixture(
        self,
        db: Session,
        *,
        comp: Competition,
        fixture: Fixture,
        dry_run: bool,
        force_refresh: bool,
        auto_confirm_mapping: bool,
    ) -> dict[str, Any]:
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
        mapping_status = "ok"
        warnings: list[str] = []

        if mapping is None:
            if auto_confirm_mapping:
                match_result = self._match_svc.match_fixture_for_competition(db, fid, comp)
                best = match_result.get("best_candidate")
                score = float(match_result.get("confidence_score") or 0)
                if best and score >= 90 and not dry_run:
                    self._lineup_svc.confirm_mapping(
                        db,
                        fid,
                        provider_event_id=int(best["provider_event_id"]),
                        confidence_score=score,
                        matched_by="auto_k2_backfill",
                        raw_payload=best.get("raw_event"),
                        expected_competition_id=int(comp.id),
                    )
                    mapping_status = "auto_confirmed"
                    mapping = db.scalar(
                        select(FixtureProviderMapping).where(
                            FixtureProviderMapping.fixture_id == fid,
                            FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
                        ),
                    )
                elif best and score >= 90:
                    return {
                        "found": 0,
                        "written": 0,
                        "skipped_provider_id": 0,
                        "api_calls": int(match_result.get("api_calls") or 1),
                        "mapping_missing": True,
                        "fetch_error": False,
                        "detected_paths": [],
                        "warnings": [
                            f"Fixture {fid}: mapping assente, match score={score:.1f} non confermato",
                        ],
                        "sample": SportApiUnavailableBackfillFixtureSample(
                            fixture_id=fid,
                            round=fixture.round,
                            home_team=home_name,
                            away_team=away_name,
                            mapping_status="match_found_not_confirmed",
                            skipped_reason="mapping_missing",
                        ),
                    }

            if mapping is None:
                return {
                    "found": 0,
                    "written": 0,
                    "skipped_provider_id": 0,
                    "api_calls": 0,
                    "mapping_missing": True,
                    "fetch_error": False,
                    "detected_paths": [],
                    "warnings": [f"Fixture {fid}: mapping SportAPI assente — skip (K.4 strict)"],
                    "sample": SportApiUnavailableBackfillFixtureSample(
                        fixture_id=fid,
                        round=fixture.round,
                        home_team=home_name,
                        away_team=away_name,
                        mapping_status="mapping_missing",
                        skipped_reason="mapping_missing",
                    ),
                }

        if not dry_run:
            fetch_out = self._lineup_svc.fetch_and_persist_lineups(db, fid)
            if fetch_out.get("status") != "success":
                msg = str(fetch_out.get("message") or "fetch failed")
                return {
                    "found": 0,
                    "written": 0,
                    "skipped_provider_id": 0,
                    "api_calls": 1,
                    "mapping_missing": False,
                    "fetch_error": True,
                    "detected_paths": [],
                    "warnings": [f"Fixture {fid}: {msg}"],
                    "sample": SportApiUnavailableBackfillFixtureSample(
                        fixture_id=fid,
                        round=fixture.round,
                        home_team=home_name,
                        away_team=away_name,
                        mapping_status=mapping_status,
                        skipped_reason="fetch_error",
                    ),
                }
            found = int(fetch_out.get("missing_players_saved") or 0)
            skipped = int(fetch_out.get("skipped_missing_provider_player_id") or 0)
            return {
                "found": found,
                "written": found,
                "skipped_provider_id": skipped,
                "api_calls": 1,
                "mapping_missing": False,
                "fetch_error": False,
                "detected_paths": [],
                "warnings": warnings,
                "sample": SportApiUnavailableBackfillFixtureSample(
                    fixture_id=fid,
                    round=fixture.round,
                    home_team=home_name,
                    away_team=away_name,
                    unavailable_found=found,
                    would_write=found,
                    written=found,
                    mapping_status=mapping_status,
                    data_source="live",
                ),
            }

        debug_out = self._debug_svc.debug_fixture(
            db,
            fixture_id=fid,
            competition_id=int(comp.id),
            dry_run=True,
            force_refresh=force_refresh,
        )
        if debug_out.status == "error":
            return {
                "found": 0,
                "written": 0,
                "skipped_provider_id": int(debug_out.skipped_missing_provider_player_id),
                "api_calls": 1 if debug_out.mapping_status == "ok" else 0,
                "mapping_missing": debug_out.mapping_status == "mapping_missing",
                "fetch_error": debug_out.mapping_status == "ok",
                "detected_paths": debug_out.detected_paths,
                "warnings": list(debug_out.warnings),
                "sample": SportApiUnavailableBackfillFixtureSample(
                    fixture_id=fid,
                    round=fixture.round,
                    home_team=home_name,
                    away_team=away_name,
                    mapping_status=debug_out.mapping_status,
                    skipped_reason="fetch_error" if debug_out.mapping_status == "ok" else "mapping_missing",
                ),
            }

        found = int(debug_out.total_unavailable_found)
        return {
            "found": found,
            "written": 0,
            "skipped_provider_id": int(debug_out.skipped_missing_provider_player_id),
            "api_calls": 1,
            "mapping_missing": False,
            "fetch_error": False,
            "detected_paths": debug_out.detected_paths,
            "warnings": warnings,
            "sample": SportApiUnavailableBackfillFixtureSample(
                fixture_id=fid,
                round=fixture.round,
                home_team=home_name,
                away_team=away_name,
                unavailable_found=found,
                would_write=int(debug_out.would_write_count),
                written=0,
                mapping_status=mapping_status,
                data_source=debug_out.data_source,
                detected_paths=debug_out.detected_paths,
            ),
        }

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

        total_found = 0
        total_written = 0
        skipped_provider_id = 0
        with_unavailable = 0
        with_mapping = 0
        mapping_missing = 0
        fetch_errors = 0
        samples: list[SportApiUnavailableBackfillFixtureSample] = []
        warnings: list[str] = []

        for fixture in fixtures:
            if fixture is None:
                continue

            result = self._process_one_fixture(
                db,
                comp=comp,
                fixture=fixture,
                dry_run=dry_run,
                force_refresh=force_refresh,
                auto_confirm_mapping=auto_confirm_mapping,
            )

            if result.get("mapping_missing"):
                mapping_missing += 1
            else:
                with_mapping += 1

            total_found += int(result.get("found") or 0)
            total_written += int(result.get("written") or 0)
            skipped_provider_id += int(result.get("skipped_provider_id") or 0)
            if int(result.get("found") or 0) > 0:
                with_unavailable += 1
            if result.get("fetch_error"):
                fetch_errors += 1
            sample = result.get("sample")
            if sample is not None:
                samples.append(sample)
            warnings.extend(result.get("warnings") or [])

        samples = sorted(samples, key=lambda s: s.unavailable_found, reverse=True)[:_SAMPLE_LIMIT]

        return SportApiUnavailableBackfillResponse(
            status="ok",
            dry_run=bool(dry_run),
            competition_id=int(competition_id),
            competition_name=comp.name,
            round_number=round_number,
            fixtures_processed=len([f for f in fixtures if f is not None]),
            fixtures_with_mapping=with_mapping,
            fixtures_mapping_missing=mapping_missing,
            fixtures_with_unavailable_from_provider=with_unavailable,
            total_unavailable_found=total_found,
            total_written=total_written,
            skipped_missing_provider_player_id=skipped_provider_id,
            mapping_missing_count=mapping_missing,
            fetch_errors=fetch_errors,
            samples=samples,
            warnings=warnings[:20],
        )
