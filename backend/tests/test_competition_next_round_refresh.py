"""Test refresh prossima giornata multi-campionato."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    fixture_eligible_for_upcoming_sot,
)
from app.main import app
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.services.competition_ingestion_service import CompetitionIngestionService
from app.services.prediction_readiness import build_model_status_for_competition

client = TestClient(app)


def _future_fx(fx_id: int = 101) -> MagicMock:
    future = datetime.now(timezone.utc) + timedelta(days=2)
    fx = MagicMock(spec=Fixture)
    fx.id = fx_id
    fx.status = "NS"
    fx.kickoff_at = future
    fx.competition_id = 2
    fx.round = "Regular Season - 18"
    fx.raw_json = None
    return fx


def test_fixture_eligible_for_upcoming_sot_accepts_status_and_kickoff():
    future = datetime.now(timezone.utc) + timedelta(days=3)
    assert fixture_eligible_for_upcoming_sot("NS", future) is True
    assert fixture_eligible_for_upcoming_sot("TBD", future) is True
    assert fixture_eligible_for_upcoming_sot("FT", future) is False


def test_fixture_eligible_does_not_crash_with_fixture_fields():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    fx = MagicMock(spec=Fixture)
    fx.status = "NS"
    fx.kickoff_at = future
    assert fixture_eligible_for_upcoming_sot(fx.status, fx.kickoff_at) is True


def test_refresh_next_round_dry_run_uses_future_selection():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao"
    comp.name = "Brasileirão Série A"
    comp.provider_league_id = 71
    comp.season = 2026

    fx1 = _future_fx()

    db = MagicMock()
    svc = CompetitionIngestionService()
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    db.scalar.return_value = 0
    db.scalars.return_value.all.return_value = [fx1]
    result = svc.refresh_next_round(db, 2, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["competition_id"] == 2
    assert result["next_round_fixtures"] == 1
    assert result["future_fixtures_count"] == 1
    assert result["round"] == "Regular Season - 18"
    assert "selection" in result


def test_refresh_next_round_returns_error_when_no_future_fixtures():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao"
    comp.name = "Brasileirão Série A"
    comp.provider_league_id = 71
    comp.season = 2026

    db = MagicMock()
    svc = CompetitionIngestionService()
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    db.scalar.return_value = 0
    db.scalars.return_value.all.return_value = []
    result = svc.refresh_next_round(db, 2, dry_run=False)

    assert result["status"] == "error"
    assert result["code"] == "no_future_fixtures"
    assert result["step"] == "select_next_round"


def test_refresh_next_round_generates_v11_and_v20_with_warnings():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao"
    comp.name = "Brasileirão Série A"
    comp.provider_league_id = 71
    comp.season = 2026

    fx1 = _future_fx()

    db = MagicMock()
    svc = CompetitionIngestionService()
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    v11_out = {
        "status": "success",
        "predictions_created_or_updated": 2,
        "valid_predictions": 2,
        "incomplete_predictions": 0,
    }
    v20_out = {"status": "success", "predictions_ok": 2}

    with patch(
        "app.services.predictions_v11.baseline_v1_1_sot_service.SotPredictionV11BaselineSotService.generate_for_competition",
        return_value=v11_out,
    ) as mock_v11, patch(
        "app.services.predictions_v20.baseline_v2_0_lineup_impact_service.SotPredictionV20LineupImpactService.generate_for_competition",
        return_value=v20_out,
    ) as mock_v20:
        db.scalar.return_value = 0
        db.scalars.return_value.all.return_value = [fx1]
        result = svc.refresh_next_round(db, 2, dry_run=False)

    mock_v11.assert_called_once_with(db, 2, fixture_ids=[101])
    mock_v20.assert_called_once_with(db, 2, fixture_ids=[101])
    assert result["status"] == "ok"
    assert result["predictions_created_or_updated"] == 2
    assert any("Lineups non disponibili" in w for w in result["warnings"])
    assert result["v20"]["mode"] == "degraded_fallback"


def test_refresh_next_round_skips_stale_round4_when_future_round18_exists():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao"
    comp.name = "Brasileirão Série A"
    comp.provider_league_id = 71
    comp.season = 2026

    past = datetime.now(timezone.utc) - timedelta(days=90)
    future = datetime.now(timezone.utc) + timedelta(days=5)

    stale = MagicMock(spec=Fixture)
    stale.id = 1
    stale.status = "PST"
    stale.kickoff_at = past
    stale.competition_id = 2
    stale.round = "Regular Season - 4"
    stale.raw_json = None

    future_fx = _future_fx(200)
    future_fx.kickoff_at = future

    db = MagicMock()
    svc = CompetitionIngestionService()
    svc._comp_svc = MagicMock()
    svc._comp_svc.get_by_id_or_raise.return_value = comp

    db.scalar.return_value = 0
    db.scalars.return_value.all.return_value = [stale, future_fx]
    result = svc.refresh_next_round(db, 2, dry_run=True)

    assert result["status"] == "dry_run"
    assert result["future_fixtures_count"] == 1
    assert result["next_round_fixtures"] == 1
    assert result["round"] == "Regular Season - 18"


def test_model_status_fallback_when_no_predictions_but_data_ready():
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao"
    comp.provider_league_id = 71
    comp.season = 2026

    db = MagicMock()
    db.scalars.return_value.all.return_value = [1, 2, 3]
    db.scalar.side_effect = [0, 334, 597, 0, 0, 3, 0, 0]

    payload, code = build_model_status_for_competition(db, comp)

    assert code == 200
    assert payload["status"] == "fallback_ready"
    assert payload["active_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert payload["recommended_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert payload["operating_mode"] == "degraded_fallback"
    assert any("v2.0 senza lineups" in w for w in payload["warnings"])


def test_refresh_route_returns_422_on_service_error():
    with patch("app.routes.admin_competition_ingest.CompetitionIngestionService") as mock_cls:
        mock_cls.return_value.refresh_next_round.return_value = {
            "status": "error",
            "code": "no_future_fixtures",
            "message": "Nessuna partita futura",
            "competition_id": 2,
            "step": "select_next_round",
        }
        response = client.post("/api/admin/competitions/2/refresh/next-round", json={"dry_run": False})

    assert response.status_code == 422
    body = response.json()
    assert body["status"] == "error"
    assert body["step"] == "select_next_round"
