"""Preparazione dati automatica per analisi giornata (Step I)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Fixture, FixtureMissingPlayer
from app.models.fixture_provider_mapping import PROVIDER_SPORTAPI, FixtureProviderMapping
from app.schemas.backtest_point_in_time import BacktestFixtureCandidate
from app.services.backtest.backtest_fixture_debug_service import BacktestFixtureDebugService
from app.services.predictions_v11.player_layer_lineup_helpers import fixture_both_lineups_available
from app.services.sportapi.sportapi_fixture_mapping_backfill_service import SportApiFixtureMappingBackfillService
from app.services.sportapi.sportapi_unavailable_backfill_service import SportApiUnavailableBackfillService


@dataclass
class FixturePreflight:
    fixture_id: int
    has_lineup: bool
    has_mapping: bool
    unavailable_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass
class RoundAnalysisPrepResult:
    fixtures: list[BacktestFixtureCandidate]
    fixture_preflights: dict[int, FixturePreflight]
    prep_warnings: list[str]
    mapping_backfill_summary: dict[str, Any] | None = None
    unavailable_backfill_summary: dict[str, Any] | None = None


class RoundAnalysisDataPrepService:
    def prepare(
        self,
        db: Session,
        *,
        competition_id: int,
        season_year: int,
        round_number: int,
        limit: int = 50,
    ) -> RoundAnalysisPrepResult:
        selection = BacktestFixtureDebugService().select_fixtures_for_mini_run(
            db,
            competition_id=competition_id,
            round_number=round_number,
            limit=limit,
        )
        fixtures = selection.items
        preflights: dict[int, FixturePreflight] = {}
        prep_warnings: list[str] = []

        missing_mapping_ids: list[int] = []
        for cand in fixtures:
            pf = self._preflight_fixture(db, cand.fixture_id)
            preflights[cand.fixture_id] = pf
            if not pf.has_mapping:
                missing_mapping_ids.append(cand.fixture_id)

        mapping_summary = None
        if missing_mapping_ids:
            resp = SportApiFixtureMappingBackfillService().backfill(
                db,
                competition_id=competition_id,
                round_number=round_number,
                dry_run=False,
                limit=limit,
            )
            mapping_summary = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)  # type: ignore[arg-type]
            prep_warnings.append("mapping_partial")
            db.commit()
            for fid in missing_mapping_ids:
                preflights[fid] = self._preflight_fixture(db, fid)

        unavailable_targets: list[int] = []
        for cand in fixtures:
            pf = preflights[cand.fixture_id]
            if pf.unavailable_count == 0 and pf.has_mapping:
                unavailable_targets.append(cand.fixture_id)

        unavailable_summary = None
        if unavailable_targets:
            resp = SportApiUnavailableBackfillService().backfill(
                db,
                competition_id=competition_id,
                round_number=round_number,
                dry_run=False,
                auto_confirm_mapping=False,
                limit=limit,
            )
            unavailable_summary = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)  # type: ignore[arg-type]
            db.commit()
            for fid in unavailable_targets:
                preflights[fid] = self._preflight_fixture(db, fid)

        for pf in preflights.values():
            if not pf.has_lineup:
                prep_warnings.append("lineup_missing")
            if not pf.has_mapping:
                prep_warnings.append("unavailable_backfill_skipped_no_mapping")
            prep_warnings.extend(pf.warnings)

        return RoundAnalysisPrepResult(
            fixtures=fixtures,
            fixture_preflights=preflights,
            prep_warnings=list(dict.fromkeys(prep_warnings)),
            mapping_backfill_summary=mapping_summary,
            unavailable_backfill_summary=unavailable_summary,
        )

    def _preflight_fixture(self, db: Session, fixture_id: int) -> FixturePreflight:
        fx = db.get(Fixture, int(fixture_id))
        warnings: list[str] = []
        if fx is None:
            return FixturePreflight(
                fixture_id=int(fixture_id),
                has_lineup=False,
                has_mapping=False,
                unavailable_count=0,
                warnings=["fixture_not_found"],
            )

        has_lineup = fixture_both_lineups_available(
            db,
            fixture_id=int(fx.id),
            home_team_id=int(fx.home_team_id),
            away_team_id=int(fx.away_team_id),
        )
        if not has_lineup:
            warnings.append("lineup_missing")

        mapping = db.scalar(
            select(FixtureProviderMapping).where(
                FixtureProviderMapping.fixture_id == int(fx.id),
                FixtureProviderMapping.provider_name == PROVIDER_SPORTAPI,
            ),
        )
        has_mapping = mapping is not None
        if not has_mapping:
            warnings.append("mapping_missing")

        unavailable_count = int(
            db.scalar(
                select(func.count())
                .select_from(FixtureMissingPlayer)
                .where(FixtureMissingPlayer.fixture_id == int(fx.id)),
            )
            or 0,
        )

        return FixturePreflight(
            fixture_id=int(fx.id),
            has_lineup=has_lineup,
            has_mapping=has_mapping,
            unavailable_count=unavailable_count,
            warnings=warnings,
        )

    def fixture_data_quality(self, preflight: FixturePreflight) -> dict[str, str]:
        return {
            "lineup": "ok" if preflight.has_lineup else "missing",
            "mapping": "ok" if preflight.has_mapping else "missing",
            "unavailable": "ok" if preflight.unavailable_count > 0 else "empty",
        }
