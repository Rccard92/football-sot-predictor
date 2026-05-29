"""Explanation strict: model_version esplicito senza fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
from app.services.sot_fixture_explanation_service import build_fixture_sot_explanation


@patch("app.services.sot_fixture_explanation_service.MatchVariableAuditService")
def test_explanation_strict_missing_v21(mock_audit_svc):
    fx = MagicMock()
    fx.id = 551
    fx.home_team_id = 1
    fx.away_team_id = 2
    fx.status = "NS"
    fx.kickoff_at = None
    fx.round = "R5"
    fx.competition_id = 2
    home = MagicMock()
    home.name = "Home FC"
    away = MagicMock()
    away.name = "Away FC"

    row_v20_home = MagicMock()
    row_v20_home.model_version = "baseline_v2_0_lineup_impact"
    row_v20_home.team_id = 1
    row_v20_home.predicted_sot = 4.0
    row_v20_home.raw_json = {}
    row_v20_home.actual_sot = None
    row_v20_away = MagicMock()
    row_v20_away.model_version = "baseline_v2_0_lineup_impact"
    row_v20_away.team_id = 2
    row_v20_away.predicted_sot = 3.0
    row_v20_away.raw_json = {}
    row_v20_away.actual_sot = None

    db = MagicMock()

    def _get(model, pk):
        if model.__name__ == "Fixture":
            return fx
        if pk == 1:
            return home
        if pk == 2:
            return away
        return None

    db.get.side_effect = _get
    db.scalars.return_value.all.return_value = [row_v20_home, row_v20_away]
    mock_audit_svc.return_value.build_fixture_variables_shots_on_target.return_value = None

    out = build_fixture_sot_explanation(
        db,
        551,
        model_version=BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
    )

    assert out["status"] == "missing_prediction"
    assert out["model_version"] == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS
