"""Test dettaglio fixture upcoming scoped per competition."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.services.next_round_quick_report_service import (
    build_upcoming_fixture_detail_for_competition,
    build_upcoming_fixture_detail_payload,
)

client = TestClient(app)


def _comp(comp_id: int = 2) -> MagicMock:
    comp = MagicMock(spec=Competition)
    comp.id = comp_id
    comp.name = "Brasileirão Série A"
    comp.season = 2026
    comp.key = "brasileirao"
    return comp


def _fx(fx_id: int = 551, *, competition_id: int = 2) -> MagicMock:
    fx = MagicMock(spec=Fixture)
    fx.id = fx_id
    fx.competition_id = competition_id
    fx.home_team_id = 10
    fx.away_team_id = 11
    return fx


def _sample_match(fx_id: int = 551) -> dict:
    return {
        "fixture_id": fx_id,
        "api_fixture_id": 900551,
        "round": "Regular Season - 18",
        "kickoff_at": "2026-06-01T00:00:00+00:00",
        "status_short": "NS",
        "home_team": {"id": 10, "name": "Flamengo", "logo_url": None},
        "away_team": {"id": 11, "name": "Coritiba", "logo_url": None},
        "model_version_used": "baseline_v2_0_lineup_impact",
        "home_prediction": {"expected_sot": 5.2, "model_version": "baseline_v2_0_lineup_impact", "breakdown": {}},
        "away_prediction": {"expected_sot": 3.1, "model_version": "baseline_v2_0_lineup_impact", "breakdown": {}},
        "total_expected_sot": 8.3,
        "lineup_status": {"label": "Probabili aggiornate", "has_lineup": True, "confirmed": False},
        "lineup_refresh_impact": {"has_comparison": False},
    }


def test_competition_fixture_detail_route_success():
    comp = _comp(2)
    with patch("app.routes.competition_scoped.CompetitionService") as mock_svc_cls, patch(
        "app.routes.competition_scoped.build_upcoming_fixture_detail_for_competition",
        return_value=(
            {
                "status": "success",
                "season": 2026,
                "competition_id": 2,
                "competition_name": comp.name,
                "match": _sample_match(551),
            },
            200,
        ),
    ):
        mock_svc_cls.return_value.get_by_id_or_raise.return_value = comp
        response = client.get(
            "/api/competitions/2/predictions/sot/upcoming-fixture/551/detail"
            "?model_version=baseline_v2_0_lineup_impact"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["competition_id"] == 2
    assert body["match"]["fixture_id"] == 551
    assert body["match"]["lineup_status"]["has_lineup"] is True


def test_competition_fixture_detail_route_competition_not_found():
    from fastapi import HTTPException

    with patch("app.routes.competition_scoped.CompetitionService") as mock_svc_cls:
        mock_svc_cls.return_value.get_by_id_or_raise.side_effect = HTTPException(
            status_code=404, detail="Competition 99 non trovata"
        )
        response = client.get("/api/competitions/99/predictions/sot/upcoming-fixture/551/detail")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "competition_not_found"
    assert body["competition_id"] == 99


def test_build_fixture_detail_for_competition_mismatch():
    comp = _comp(2)
    fx = _fx(551, competition_id=1)
    db = MagicMock()
    db.get.return_value = fx

    payload, code = build_upcoming_fixture_detail_for_competition(db, comp, 551)

    assert code == 404
    assert payload["code"] == "fixture_competition_mismatch"
    assert payload["competition_id"] == 2
    assert payload["fixture_id"] == 551


def test_build_fixture_detail_for_competition_not_found():
    comp = _comp(2)
    db = MagicMock()
    db.get.return_value = None

    payload, code = build_upcoming_fixture_detail_for_competition(db, comp, 551)

    assert code == 404
    assert payload["code"] == "fixture_not_found"


def test_build_fixture_detail_for_competition_delegates_payload_builder():
    comp = _comp(2)
    fx = _fx(551, competition_id=2)
    db = MagicMock()
    db.get.return_value = fx

    active_payload = {
        "season": 2026,
        "competition_id": 2,
        "matches": [_sample_match(551)],
        "model_limitations": {},
    }

    with patch(
        "app.services.prediction_readiness.build_upcoming_active_payload",
        return_value=(active_payload, 200),
    ) as mock_active, patch(
        "app.services.referee_severity_service.build_referee_summary_for_fixture",
        return_value={"referee_name": "Test"},
    ):
        payload, code = build_upcoming_fixture_detail_for_competition(
            db, comp, 551, model_version="baseline_v2_0_lineup_impact"
        )

    assert code == 200
    assert payload["status"] == "success"
    assert payload["competition_id"] == 2
    assert payload["match"]["fixture_id"] == 551
    mock_active.assert_called_once()
    call_kw = mock_active.call_args.kwargs
    assert call_kw["competition_id"] == 2
    assert call_kw["fixture_ids"] == [551]
    assert call_kw["only_next_round"] is False


def test_legacy_serie_a_fixture_detail_route_still_available():
    with patch(
        "app.routes.predictions.build_upcoming_fixture_detail_payload",
        return_value=(
            {"status": "success", "season": 2025, "match": _sample_match(100)},
            200,
        ),
    ):
        response = client.get("/api/predictions/sot/serie-a/2025/upcoming-fixture/100/detail")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_build_upcoming_active_payload_competition_branch_skips_season_row():
    from app.services.prediction_readiness import build_upcoming_active_payload

    comp = _comp(2)
    fx = _fx(551, competition_id=2)
    db = MagicMock()
    db.get.return_value = comp
    db.scalars.return_value.all.return_value = [fx]
    db.scalar.return_value = 0

    with patch("app.services.prediction_readiness.SotPredictionService") as mock_pred_svc, patch(
        "app.services.next_round_selection.select_next_round_fixtures"
    ) as mock_sel:
        from types import SimpleNamespace

        mock_sel.return_value = SimpleNamespace(fixtures=[fx], final_round="Regular Season - 18")
        payload, code = build_upcoming_active_payload(
            db,
            2026,
            competition_id=2,
            fixture_ids=[551],
            only_next_round=False,
            limit=1,
        )

    assert code == 200
    assert payload["competition_id"] == 2
    mock_pred_svc.assert_not_called()
