"""Test confronto prossimo turno v2.0 vs v2.1."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.models.competition import Competition
from app.services.competition_ingestion_service import CompetitionIngestionService
from app.services.next_round_model_comparison_service import (
    _compute_delta,
    _side_from_predictions,
    build_next_round_model_comparison_for_competition,
)


def test_compute_delta_pick_changed():
    base = {
        "predicted_total_sot": 9.05,
        "home_sot": 4.5,
        "away_sot": 4.55,
        "statistical_pick": "Over 8.5 SOT",
        "confidence_label": "Media",
    }
    compare = {
        "predicted_total_sot": 8.27,
        "home_sot": 4.1,
        "away_sot": 4.17,
        "statistical_pick": "Over 7.5 SOT",
        "confidence_label": "Media",
    }
    delta = _compute_delta(base, compare)
    assert delta is not None
    assert delta["total_sot"] == -0.78
    assert delta["direction"] == "down"
    assert delta["pick_changed"] is True
    assert delta["confidence_changed"] is False


@patch("app.services.next_round_model_comparison_service.build_upcoming_report_markets")
def test_side_from_predictions_uses_own_model(mock_markets):
    mock_markets.return_value = [
        {
            "statistical_pick": "Over 7.5 SOT",
            "cautious_pick": "Over 6.5 SOT",
            "statistical_margin": 0.77,
            "confidence_label": "Media",
        },
    ]
    ph = MagicMock()
    ph.predicted_sot = 4.1
    pa = MagicMock()
    pa.predicted_sot = 4.17
    side = _side_from_predictions(
        ph,
        pa,
        model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        advice_ctx={"lineup_status_label": "Probabili aggiornate"},
    )
    assert side is not None
    assert side["predicted_total_sot"] == 8.27
    assert side["statistical_pick"] == "Over 7.5 SOT"
    mock_markets.assert_called_once()
    assert mock_markets.call_args.kwargs["model_version"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def _comp() -> MagicMock:
    comp = MagicMock(spec=Competition)
    comp.id = 2
    comp.key = "brasileirao"
    comp.name = "Brasileirão Série A"
    comp.season = 2026
    return comp


@patch("app.services.next_round_model_comparison_service.load_lineups_by_fixture_ids", return_value={})
@patch("app.services.next_round_model_comparison_service.select_next_round_fixtures")
@patch("app.services.next_round_model_comparison_service.build_upcoming_report_markets")
def test_comparison_row_both_models(mock_markets, mock_select, _mock_lineups):
    fx = MagicMock()
    fx.id = 551
    fx.api_fixture_id = 999
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.kickoff_at = datetime(2026, 5, 30, 21, 0, tzinfo=timezone.utc)
    fx.round = "Regular Season - 18"
    fx.status = "NS"
    mock_select.return_value = MagicMock(fixtures=[fx], final_round="Regular Season - 18", warnings=[])

    def markets_side_effect(home, away, *, model_version, context):
        _ = home, away, context
        if model_version == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT:
            return [{"statistical_pick": "Over 8.5 SOT", "confidence_label": "Media"}]
        return [{"statistical_pick": "Over 7.5 SOT", "confidence_label": "Media"}]

    mock_markets.side_effect = markets_side_effect

    db = MagicMock()
    home = MagicMock(id=1, name="Flamengo", logo_url=None)
    away = MagicMock(id=2, name="Coritiba", logo_url=None)

    preds = []
    for mv, h, a in (
        (BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT, 4.5, 4.55),
        (BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS, 4.1, 4.17),
    ):
        ph = MagicMock(fixture_id=551, team_id=1, model_version=mv, predicted_sot=h)
        pa = MagicMock(fixture_id=551, team_id=2, model_version=mv, predicted_sot=a)
        preds.extend([ph, pa])

    call_n = {"n": 0}

    def scalars_effect(_stmt=None):
        call_n["n"] += 1
        result = MagicMock()
        if call_n["n"] == 1:
            result.all.return_value = [fx]
        elif call_n["n"] == 2:
            result.all.return_value = [home, away]
        else:
            result.all.return_value = preds
        return result

    db.scalars = scalars_effect

    payload, code = build_next_round_model_comparison_for_competition(db, _comp())
    assert code == 200
    assert payload["matches_count"] == 1
    row = payload["rows"][0]
    assert row["v20"]["predicted_total_sot"] == 9.05
    assert row["v21"]["predicted_total_sot"] == 8.27
    assert row["delta"]["pick_changed"] is True
    assert payload["missing"]["base_model_missing_predictions"] == 0


@patch("app.services.next_round_model_comparison_service.load_lineups_by_fixture_ids", return_value={})
@patch("app.services.next_round_model_comparison_service.select_next_round_fixtures")
def test_comparison_missing_v20_no_fallback(mock_select, _mock_lineups):
    fx = MagicMock()
    fx.id = 551
    fx.api_fixture_id = 999
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.kickoff_at = None
    fx.round = "R18"
    fx.status = "NS"
    mock_select.return_value = MagicMock(fixtures=[fx], final_round="R18", warnings=[])

    db = MagicMock()
    home = MagicMock(id=1, name="A", logo_url=None)
    away = MagicMock(id=2, name="B", logo_url=None)
    v21_ph = MagicMock(
        fixture_id=551,
        team_id=1,
        model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        predicted_sot=4.0,
    )
    v21_pa = MagicMock(
        fixture_id=551,
        team_id=2,
        model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        predicted_sot=4.0,
    )

    call_n = {"n": 0}

    def scalars_effect(_stmt=None):
        call_n["n"] += 1
        result = MagicMock()
        if call_n["n"] == 1:
            result.all.return_value = [fx]
        elif call_n["n"] == 2:
            result.all.return_value = [home, away]
        else:
            result.all.return_value = [v21_ph, v21_pa]
        return result

    db.scalars = scalars_effect

    with patch(
        "app.services.next_round_model_comparison_service.build_upcoming_report_markets",
        return_value=[{"statistical_pick": "Over 7.5 SOT", "confidence_label": "Media"}],
    ):
        payload, code = build_next_round_model_comparison_for_competition(db, _comp())

    assert code == 200
    row = payload["rows"][0]
    assert row["v20"] is None
    assert row["v21"] is not None
    assert row["delta"] is None
    assert payload["missing"]["base_model_missing_predictions"] == 1


@patch("app.services.competition_ingestion_service.select_next_round_fixtures")
def test_refresh_comparison_mode_generates_v20_and_v21(mock_select):
    fx = MagicMock()
    fx.id = 10
    fx.competition_id = 2
    mock_select.return_value = MagicMock(
        fixtures=[fx],
        final_round="R18",
        warnings=[],
        future_fixtures_count=1,
        error_code=None,
        as_log_dict=lambda **_: {},
    )

    db = MagicMock()
    db.scalar.side_effect = [100, 50, 10, 5, 3]

    comp = _comp()
    with patch.object(CompetitionIngestionService, "_competition", return_value=comp), patch(
        "app.services.predictions_v20.baseline_v2_0_lineup_impact_service.SotPredictionV20LineupImpactService",
    ) as mock_v20_cls, patch(
        "app.services.predictions_v21.baseline_v2_1_weighted_components_service.SotPredictionV21WeightedComponentsService",
    ) as mock_v21_cls:
        mock_v20_cls.return_value.generate_for_competition.return_value = {
            "predictions_created_or_updated": 2,
            "status": "success",
        }
        mock_v21_cls.return_value.generate_for_competition.return_value = {
            "predictions_created_or_updated": 2,
            "status": "success",
        }
        svc = CompetitionIngestionService()
        result = svc.refresh_next_round(db, 2, generate_mode="v20_v21_comparison")

    assert result["generate_mode"] == "v20_v21_comparison"
    assert result["v20"]["predictions_created_or_updated"] == 2
    assert result["v21"]["predictions_created_or_updated"] == 2
    mock_v20_cls.return_value.generate_for_competition.assert_called_once_with(db, 2, fixture_ids=[10])
    mock_v21_cls.return_value.generate_for_competition.assert_called_once_with(db, 2, fixture_ids=[10])
