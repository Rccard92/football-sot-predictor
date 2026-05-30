"""Test payload errori refresh v2.1."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.models.fixture import Fixture
from app.services.competition_ingestion_service import (
    CompetitionIngestionService,
    _build_v21_refresh_response,
)
from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
    SotPredictionV21WeightedComponentsService,
)


def _future_fx(fx_id: int = 551) -> MagicMock:
    future = datetime.now(timezone.utc) + timedelta(days=2)
    fx = MagicMock(spec=Fixture)
    fx.id = fx_id
    fx.status = "NS"
    fx.kickoff_at = future
    fx.competition_id = 2
    fx.round = "Regular Season - 18"
    fx.home_team_id = 10
    fx.away_team_id = 20
    fx.raw_json = None
    return fx


def test_build_v21_refresh_response_all_failed():
    comp = MagicMock()
    comp.id = 2
    comp.key = "brasileirao_serie_a_2026"
    comp.name = "Brasileirão"
    comp.season = 2026
    v21_result = {
        "status": "error",
        "code": "v21_all_fixtures_failed",
        "predictions_created_or_updated": 0,
        "fixtures_processed": 0,
        "fixtures_failed": [551],
        "fixtures_succeeded": [],
        "errors": [
            {
                "fixture_id": 551,
                "error": "season_not_found_for_competition:2",
                "failed_step": "build_v21_context",
                "error_type": "ValueError",
            },
        ],
    }
    out = _build_v21_refresh_response(
        comp=comp,
        round_label="Regular Season - 18",
        future_fixtures_count=210,
        upcoming_count=10,
        fixture_ids=[551],
        v21_result=v21_result,
        warnings=[],
        lineup_payload={"lineups_required_for_v21": False},
    )
    assert out["status"] == "error"
    assert out["code"] == "v21_all_fixtures_failed"
    assert out["failed_step"] == "v21_generate"
    assert out["failed_fixture_id"] == 551
    assert out["error_type"] == "ValueError"
    assert out["model_version"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def test_build_v21_refresh_response_partial_error():
    comp = MagicMock()
    comp.id = 2
    comp.key = "brasileirao"
    comp.name = "Brasileirão"
    comp.season = 2026
    v21_result = {
        "status": "partial",
        "code": "v21_partial_failures",
        "predictions_created_or_updated": 18,
        "fixtures_processed": 9,
        "fixtures_failed": [560],
        "fixtures_succeeded": [551, 552],
        "errors": [{"fixture_id": 560, "error": "persist_failed", "failed_step": "save_prediction"}],
    }
    out = _build_v21_refresh_response(
        comp=comp,
        round_label="Regular Season - 18",
        future_fixtures_count=210,
        upcoming_count=10,
        fixture_ids=[551, 560],
        v21_result=v21_result,
        warnings=[],
        lineup_payload={},
    )
    assert out["status"] == "partial_error"
    assert out["code"] == "v21_partial_failures"
    assert out["predictions_created_or_updated"] == 18


def test_refresh_v21_only_returns_structured_error_on_zero_predictions():
    comp = MagicMock()
    comp.id = 2
    comp.key = "brasileirao"
    comp.name = "Brasileirão"
    comp.provider_league_id = 71
    comp.season = 2026

    fx1 = _future_fx()

    db = MagicMock()
    svc = CompetitionIngestionService()
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    v21_fail = {
        "status": "error",
        "code": "v21_all_fixtures_failed",
        "predictions_created_or_updated": 0,
        "fixtures_processed": 0,
        "fixtures_failed": [551],
        "fixtures_succeeded": [],
        "errors": [{"fixture_id": 551, "error": "season_not_found", "failed_step": "build_v21_context"}],
    }

    with patch(
        "app.services.predictions_v21.baseline_v2_1_weighted_components_service.SotPredictionV21WeightedComponentsService.generate_for_competition",
        return_value=v21_fail,
    ):
        db.scalar.return_value = 0
        db.scalars.return_value.all.return_value = [fx1]
        result = svc.refresh_next_round(
            db,
            2,
            dry_run=False,
            model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        )

    assert result["status"] == "error"
    assert result["code"] == "v21_all_fixtures_failed"
    assert result["failed_fixture_id"] == 551
    assert result["failed_step"] == "v21_generate"


def test_generate_for_competition_enriches_error_entry_on_exception():
    fx = _future_fx(551)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [fx]

    svc = SotPredictionV21WeightedComponentsService()
    with patch.object(svc, "generate_for_fixture", side_effect=RuntimeError("boom context")):
        out = svc.generate_for_competition(db, 2, fixture_ids=[551])

    assert out["status"] == "error"
    assert out["code"] == "v21_all_fixtures_failed"
    assert out["fixtures_failed"] == [551]
    assert out["errors"][0]["failed_step"] == "build_prediction_v21"
    assert out["errors"][0]["error_type"] == "RuntimeError"
