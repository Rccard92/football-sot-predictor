"""Test blindatura modello v2.0 globale multi-campionato."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.constants import BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
from app.models.competition import Competition
from app.services.model_operating_context import build_v20_operating_context, resolve_operating_mode
from app.services.prediction_readiness import build_model_status_for_competition
from app.services.predictions_v20.baseline_v2_0_lineup_impact_service import SotPredictionV20LineupImpactService
from app.services.sot_model_registry import get_model_display


def _scalar_side_effect_for_brasile_fallback(*, upcoming_in_ctx: int = 3) -> list[int]:
    """predictions_total=0, poi counts da build_v20_operating_context."""
    return [0, 334, 597, 0, 0, upcoming_in_ctx, 0, 0]


def _comp(comp_id: int, *, name: str | None = None) -> MagicMock:
    comp = MagicMock(spec=Competition)
    comp.id = comp_id
    comp.key = "brasileirao" if comp_id == 2 else "serie_a_italy_2025"
    comp.name = name or ("Brasileirão Série A" if comp_id == 2 else "Serie A")
    comp.provider_league_id = 71 if comp_id == 2 else 135
    comp.country = "Brazil" if comp_id == 2 else "Italy"
    comp.season = 2026 if comp_id == 2 else 2025
    return comp


def test_single_global_model_version_constant():
    svc = SotPredictionV20LineupImpactService()
    assert svc.model_version == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    for comp_id in (1, 2):
        comp = _comp(comp_id)
        ctx = build_v20_operating_context(_mock_db_for_context(comp_id), comp)
        assert ctx["global_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT


def _mock_db_for_context(comp_id: int, *, lineups: int = 0, mappings: int = 0) -> MagicMock:
    db = MagicMock()
    db.scalar.side_effect = [334, 597, lineups, mappings, 3, 0, 0]
    return db


def test_no_per_competition_v20_service_modules():
    root = Path(__file__).resolve().parents[1] / "app"
    v20_services = list(root.glob("**/predictions_v20/**/*.py"))
    service_files = [p for p in v20_services if p.name.endswith("_service.py")]
    assert len(service_files) == 1
    assert service_files[0].name == "baseline_v2_0_lineup_impact_service.py"
    for path in service_files:
        stem = path.stem.lower()
        assert "brasile" not in stem
        assert "serie_a" not in stem
    all_py = " ".join(p.read_text(encoding="utf-8", errors="ignore") for p in root.rglob("*.py"))
    assert "brasile_model_v2" not in all_py
    assert "serie_a_model_v2" not in all_py


def test_build_v20_operating_context_degraded_without_lineups():
    comp = _comp(2)
    db = _mock_db_for_context(2, lineups=0, mappings=0)
    ctx = build_v20_operating_context(db, comp)
    assert ctx["global_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert ctx["operating_mode"] == "degraded_fallback"
    assert ctx["lineups_ready"] is False
    assert ctx["inputs_available"]["v11_base_ready"] is True


def test_resolve_operating_mode_matrix():
    assert resolve_operating_mode(lineups_ready=True, v11_base_ready=True, upcoming_fixtures_count=5) == "complete"
    assert (
        resolve_operating_mode(lineups_ready=False, v11_base_ready=True, upcoming_fixtures_count=5)
        == "degraded_fallback"
    )
    assert resolve_operating_mode(lineups_ready=False, v11_base_ready=False, upcoming_fixtures_count=5) == "not_ready"
    assert resolve_operating_mode(lineups_ready=True, v11_base_ready=True, upcoming_fixtures_count=0) == "not_ready"


def test_model_status_fallback_ready_uses_global_v20():
    comp = _comp(2)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [1, 2, 3]
    db.scalar.side_effect = _scalar_side_effect_for_brasile_fallback()

    payload, code = build_model_status_for_competition(db, comp)

    assert code == 200
    assert payload["status"] == "fallback_ready"
    assert payload["active_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert payload["recommended_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert payload["operating_mode"] == "degraded_fallback"
    assert payload["global_model_version"] == BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT
    assert any("v2.0 senza lineups" in w for w in payload["warnings"])


def test_registry_label_used_in_generate_for_competition_response():
    comp = _comp(2)
    db = MagicMock()
    db.get.return_value = comp
    svc = SotPredictionV20LineupImpactService()
    display = get_model_display(BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT)

    with patch.object(
        svc,
        "generate_for_upcoming_season",
        return_value={"status": "success", "predictions_ok": 2},
    ), patch(
        "app.services.model_operating_context.build_v20_operating_context",
        return_value={
            "operating_mode": "degraded_fallback",
            "inputs_available": {"lineups": False},
        },
    ):
        result = svc.generate_for_competition(db, 2)

    assert result["global_model_label"] == display.label
    assert result["operating_mode"] == "degraded_fallback"
    assert result["mode"] == "degraded_fallback"
