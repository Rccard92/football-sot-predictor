"""Test lista fixture audit e spiegazione scoped per competition."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models.competition import Competition
from app.models.fixture import Fixture
from app.services.prediction_readiness import (
    build_competition_audit_fixtures_list,
    build_competition_fixture_explanation,
)

client = TestClient(app)


def _comp(comp_id: int = 2) -> MagicMock:
    comp = MagicMock(spec=Competition)
    comp.id = comp_id
    comp.name = "Brasileirão Série A"
    comp.season = 2026
    return comp


def _fx(fx_id: int = 551, *, competition_id: int = 2) -> MagicMock:
    fx = MagicMock(spec=Fixture)
    fx.id = fx_id
    fx.competition_id = competition_id
    fx.api_fixture_id = 9000 + fx_id
    fx.round = "Regular Season - 18"
    fx.status = "NS"
    fx.kickoff_at = None
    fx.home_team_id = 10
    fx.away_team_id = 11
    return fx


def test_audit_fixtures_route_success():
    comp = _comp(2)
    with patch("app.routes.competition_scoped.CompetitionService") as mock_svc_cls, patch(
        "app.routes.competition_scoped.build_competition_audit_fixtures_list",
        return_value=(
            {
                "competition_id": 2,
                "competition_name": comp.name,
                "fixtures": [
                    {
                        "fixture_id": 551,
                        "match_name": "Flamengo – Coritiba",
                        "competition_id": 2,
                        "has_prediction": True,
                        "home_team": {"id": 10, "name": "Flamengo"},
                        "away_team": {"id": 11, "name": "Coritiba"},
                    }
                ],
            },
            200,
        ),
    ):
        mock_svc_cls.return_value.get_by_id_or_raise.return_value = comp
        response = client.get("/api/competitions/2/predictions/sot/fixtures?scope=next_round")

    assert response.status_code == 200
    body = response.json()
    assert body["competition_id"] == 2
    assert body["fixtures"][0]["fixture_id"] == 551
    assert body["fixtures"][0]["competition_id"] == 2


def test_explanation_route_mismatch():
    comp = _comp(2)
    with patch("app.routes.competition_scoped.CompetitionService") as mock_svc_cls, patch(
        "app.routes.competition_scoped.build_competition_fixture_explanation",
        return_value=(
            {
                "status": "error",
                "code": "fixture_competition_mismatch",
                "competition_id": 2,
                "fixture_id": 551,
            },
            404,
        ),
    ):
        mock_svc_cls.return_value.get_by_id_or_raise.return_value = comp
        response = client.get("/api/competitions/2/predictions/sot/fixture/551/explanation")

    assert response.status_code == 404
    assert response.json()["code"] == "fixture_competition_mismatch"


def test_build_explanation_delegates_with_guardrail():
    comp = _comp(2)
    fx = _fx(551, competition_id=2)
    db = MagicMock()
    db.get.side_effect = lambda model, pk: fx if model is Fixture and pk == 551 else None

    explanation = {"status": "ok", "fixture": {"fixture_id": 551}, "prediction_summary": {}}

    with patch(
        "app.services.sot_fixture_explanation_service.build_fixture_sot_explanation",
        return_value=explanation,
    ) as mock_expl:
        payload, code = build_competition_fixture_explanation(
            db, comp, 551, model_version="baseline_v2_0_lineup_impact"
        )

    assert code == 200
    assert payload["competition_id"] == 2
    mock_expl.assert_called_once()


def test_build_explanation_mismatch():
    comp = _comp(2)
    fx = _fx(551, competition_id=1)
    db = MagicMock()
    db.get.return_value = fx

    payload, code = build_competition_fixture_explanation(db, comp, 551)

    assert code == 404
    assert payload["code"] == "fixture_competition_mismatch"


def test_build_audit_fixtures_invalid_scope():
    comp = _comp(2)
    db = MagicMock()
    payload, code = build_competition_audit_fixtures_list(db, comp, scope="invalid")
    assert code == 400
    assert payload["code"] == "invalid_scope"
