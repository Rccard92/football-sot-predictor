"""Test motore v2.1 — formula, cap, missing neutro, separazione v2.0."""

from __future__ import annotations

from app.core.constants import (
    BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT,
    BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS,
)
from app.services.predictions_v21.baseline_v2_1_weighted_components_service import (
    SotPredictionV21WeightedComponentsService,
)
from app.services.predictions_v21.v21_constants import (
    FINAL_MULTIPLIER_MAX,
    FINAL_MULTIPLIER_MIN,
    MACRO_INDEX_MAX,
    MACRO_INDEX_MIN,
    MICRO_NORM_MAX,
    MICRO_NORM_MIN,
    PREDICTIVE_MACRO_KEYS,
    QUALITY_MACRO_KEY,
)
from app.services.predictions_v21.v21_macro_aggregators import (
    aggregate_v21_macro_score,
    calculate_v21_base_anchor_sot,
    calculate_v21_expected_sot,
    calculate_v21_weighted_macro_multiplier,
)
from app.services.predictions_v21.v21_manifest_definitions import V21_MANIFEST_DEFINITIONS, V21MacroAreaSpec, V21MicroSpec
from app.services.predictions_v21.v21_normalization import (
    V21MicroResult,
    clamp_micro_norm,
    neutral_micro,
    normalize_v21_micro_variable,
)
from app.services.predictions_v21.v21_quality_summary import build_v21_quality_summary


def _micro_result(
    key: str,
    *,
    norm: float = 1.0,
    weight: int = 10,
    status: str = "available",
) -> V21MicroResult:
    return V21MicroResult(
        key=key,
        label=key,
        micro_weight=weight,
        source_path=f"test.{key}",
        raw_value=1.0,
        normalized_value=norm,
        status=status,  # type: ignore[arg-type]
        sample_count=5,
        fallback_used=False,
        contribution="neutra",
    )


def test_clamp_micro_norm_bounds():
    assert clamp_micro_norm(0.5) == MICRO_NORM_MIN
    assert clamp_micro_norm(2.0) == MICRO_NORM_MAX
    assert clamp_micro_norm(1.05) == 1.05


def test_missing_micro_neutral_without_weight_redistribution():
    m = neutral_micro(key="x", label="X", micro_weight=25, source_path="test.x")
    assert m.normalized_value == 1.0
    assert m.contribution == "neutra"
    assert m.status == "missing"


def test_base_anchor_sot_formula():
    anchor, warnings = calculate_v21_base_anchor_sot(team_sot_for=5.0, opponent_sot_conceded=3.0)
    assert anchor == round(0.55 * 5.0 + 0.45 * 3.0, 4)
    assert warnings == []


def test_macro_index_respects_cap():
    macro = V21MacroAreaSpec(
        key="test_macro",
        label="Test",
        macro_weight=10,
        micros=(V21MicroSpec(key="a", label="A", micro_weight=50, source_path="t.a"),),
    )
    micros = [_micro_result("a", norm=2.0, weight=50)]
    result = aggregate_v21_macro_score(macro, micros)
    assert result.macro_index <= MACRO_INDEX_MAX
    assert result.macro_index >= MACRO_INDEX_MIN


def test_weighted_multiplier_excludes_quality_macro():
    macros = []
    for key in PREDICTIVE_MACRO_KEYS[:3]:
        macros.append(
            type("MR", (), {
                "key": key,
                "macro_weight": 10,
                "macro_index": 1.1,
                "is_quality_only": False,
                "micros": [],
                "macro_contribution_to_multiplier": 11.0,
                "coverage_pct": 80.0,
                "status": "available",
                "warnings": [],
                "label": key,
            })(),
        )
    macros.append(
        type("MR", (), {
            "key": QUALITY_MACRO_KEY,
            "macro_weight": 4,
            "macro_index": 0.5,
            "is_quality_only": True,
            "micros": [],
            "macro_contribution_to_multiplier": 2.0,
            "coverage_pct": 100.0,
            "status": "available",
            "warnings": [],
            "label": "Quality",
        })(),
    )
    mult, _ = calculate_v21_weighted_macro_multiplier(macros)  # type: ignore[arg-type]
    assert mult == 1.1
    assert FINAL_MULTIPLIER_MIN <= mult <= FINAL_MULTIPLIER_MAX


def test_expected_sot_non_negative():
    sot = calculate_v21_expected_sot(base_anchor_sot=4.0, weighted_macro_multiplier=0.8)
    assert sot == 3.2
    assert calculate_v21_expected_sot(base_anchor_sot=None, weighted_macro_multiplier=1.0) is None


def test_quality_summary_counts_missing():
    macro = V21MacroAreaSpec(
        key="offensive_production",
        label="Off",
        macro_weight=16,
        micros=(V21MicroSpec(key="a", label="A", micro_weight=10, source_path="t.a"),),
    )
    micros = [
        _micro_result("a", status="available"),
        neutral_micro(key="b", label="B", micro_weight=5, source_path="t.b", status="missing"),
    ]
    mr = aggregate_v21_macro_score(macro, micros)
    q = build_v21_quality_summary([mr], side_warnings=[], prior_team_count=10, prior_opponent_count=8)
    assert q.missing_variables_count >= 1
    assert q.formula_quality_status in ("partial", "ok", "insufficient_data")


def test_v21_service_engine_ready():
    svc = SotPredictionV21WeightedComponentsService()
    assert svc.engine_status == "ready"
    assert svc.model_version == BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS


def test_v21_and_v20_model_versions_distinct():
    assert BASELINE_SOT_MODEL_VERSION_V21_WEIGHTED_COMPONENTS != BASELINE_SOT_MODEL_VERSION_V20_LINEUP_IMPACT


def test_manifest_has_ten_macros():
    assert len(V21_MANIFEST_DEFINITIONS) == 10
    predictive = [m for m in V21_MANIFEST_DEFINITIONS if not m.is_quality_only]
    assert len(predictive) == 9


def test_normalize_with_baseline():
    r = normalize_v21_micro_variable(
        key="avg_sot_for",
        label="SOT",
        micro_weight=10,
        source_path="team_stats.season_avg_sot_for",
        raw_value=5.0,
        baseline=4.0,
        sample_count=20,
    )
    assert r.normalized_value == clamp_micro_norm(5.0 / 4.0)
    assert r.status == "available"


def test_predictive_macro_weights_sum_to_96():
    total = sum(m.macro_weight for m in V21_MANIFEST_DEFINITIONS if not m.is_quality_only)
    assert total == 96


def test_weighted_multiplier_scale_invariant():
    """Pesi manifest (16,14,...) equivalenti a frazioni (0.16,0.14,...)."""
    indices = [1.07, 1.02, 0.98]
    int_weights = [16, 14, 10]
    frac_weights = [0.16, 0.14, 0.10]

    def _mult(weights: list[float]) -> float:
        wsum = sum(weights)
        return sum(i * w for i, w in zip(indices, weights)) / wsum

    assert round(_mult([float(w) for w in int_weights]), 4) == round(_mult(frac_weights), 4)


def test_to_trace_input_includes_micro_weight_and_rounds():
    r = normalize_v21_micro_variable(
        key="avg_sot_for",
        label="SOT",
        micro_weight=25,
        source_path="team_stats.season_avg_sot_for",
        raw_value=4.6875,
        baseline=4.0,
        sample_count=20,
    )
    blob = r.to_trace_input()
    assert blob["micro_weight"] == 25
    assert blob["raw_value"] == 4.69
    assert blob["normalized_value"] == round(clamp_micro_norm(4.6875 / 4.0), 2)
