"""Model-status: raccomandazione v2.1/v2.0 basata sul prossimo turno."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.models.competition import Competition
from app.services.model_version_preference import resolve_recommended_model_version_for_next_round
from app.services.prediction_readiness import build_model_status_for_competition


def test_resolve_recommended_prefers_v21_on_next_round():
    by_version = {
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: {
            "is_available_for_upcoming": True,
            "next_round_predictions_count": 20,
        },
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: {
            "is_available_for_upcoming": True,
            "next_round_predictions_count": 20,
        },
    }
    with patch("app.services.model_applied_variable_manifest.v21_manifest_valid", return_value=True):
        rec = resolve_recommended_model_version_for_next_round(
            by_version=by_version,
            next_round_fixtures_total=10,
        )
    assert rec == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def test_resolve_recommended_falls_back_to_v20_when_v21_partial():
    by_version = {
        BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS: {
            "is_available_for_upcoming": True,
            "next_round_predictions_count": 4,
        },
        BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT: {
            "is_available_for_upcoming": True,
            "next_round_predictions_count": 20,
        },
    }
    with patch("app.services.model_applied_variable_manifest.v21_manifest_valid", return_value=True):
        rec = resolve_recommended_model_version_for_next_round(
            by_version=by_version,
            next_round_fixtures_total=10,
        )
    assert rec == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT


def _comp(comp_id: int = 2) -> MagicMock:
    comp = MagicMock(spec=Competition)
    comp.id = comp_id
    comp.key = "brasileirao"
    comp.name = "Brasileirão Série A"
    comp.provider_league_id = 71
    comp.country = "Brazil"
    comp.season = 2026
    return comp


@patch("app.services.next_round_selection.select_next_round_fixtures")
@patch("app.services.prediction_readiness.build_v20_operating_context")
def test_model_status_recommends_v21_despite_full_season_upcoming(mock_ctx, mock_select):
    comp = _comp()
    db = MagicMock()

    upcoming_ids = list(range(1, 101))
    db.scalars.return_value.all.side_effect = [
        upcoming_ids,
        [MagicMock(id=i) for i in range(1, 11)],
    ]

    def scalar_side_effect(stmt=None):
        sql = str(getattr(stmt, "statement", stmt))
        if "count()" in sql and "team_sot_predictions" in sql and "group_by" not in sql:
            return 40
        return 0

    db.scalar.side_effect = scalar_side_effect
    db.execute.return_value.mappings.return_value.all.side_effect = [
        [
            {
                "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
                "predictions_total": 20,
                "upcoming_predictions": 20,
                "generated_at": None,
            },
        ],
        [
            {
                "model_version": BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
                "next_round_predictions": 20,
            },
        ],
    ]

    mock_select.return_value = MagicMock(fixtures=[MagicMock(id=i) for i in range(1, 11)])
    mock_ctx.return_value = {
        "global_model_version": BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
        "global_model_label": "v2.0 SOT Lineup Impact",
        "operating_mode": "complete",
        "lineups_ready": True,
        "lineups_probable_only": False,
        "confirmed_lineups_count": 0,
        "probable_lineups_count": 10,
        "next_round_lineup_coverage_pct": 100.0,
        "inputs_available": {"v11_base_ready": True},
        "competition_name": comp.name,
    }

    with patch("app.services.model_applied_variable_manifest.v21_manifest_valid", return_value=True):
        payload, code = build_model_status_for_competition(
            db,
            comp,
            selected_model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
        )

    assert code == 200
    assert payload["recommended_model_version"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    assert payload["active_model_version"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    assert payload["selected_model_version"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
    assert payload["stable_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert payload.get("global_model_version") is None
