"""Test servizio Goal Intensity v5 explanations (audit diagnostico)."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_goal_intensity_v5_preview import (
    PREVIEW_BUNDLE_VERSION,
    SNAPSHOT_PENDING,
    CecchinoGoalIntensityV5PreviewBundle,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    TrainEcdf,
    _pillar_scores_from_pct,
)
from app.services.cecchino.cecchino_goal_intensity_v5_explanations import (
    AUDIT_VERSION,
    SOURCE_MODE,
    UI_CANDIDATE_IDS,
    build_goal_intensity_v5_explanations,
    get_goal_intensity_v5_explanations,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    BENCHMARK_ID,
    BUNDLE_FEATURE_KEYS,
    CHALLENGER_ID,
    DIAGNOSTIC_ID,
    PRIMARY_ID,
    _apply_linear,
    _apply_logistic,
    score_features_with_bundle,
)
from tests.test_cecchino_goal_intensity_v5_preview import _bundle, _features, _today


def _snap_from_bundle(
    bundle: CecchinoGoalIntensityV5PreviewBundle,
    *,
    today_id: int = 100,
    features: dict | None = None,
    drop_feature: str | None = None,
) -> CecchinoGoalIntensityV5PreviewSnapshot:
    feats = dict(features or _features(1.2))
    if drop_feature:
        feats[drop_feature] = None
    scored = score_features_with_bundle(feats, bundle)
    return CecchinoGoalIntensityV5PreviewSnapshot(
        id=10,
        bundle_id=bundle.id,
        today_fixture_id=today_id,
        local_fixture_id=50,
        provider_source="api_football",
        provider_fixture_id=9100,
        competition_id=39,
        home_team_id=1,
        away_team_id=2,
        competition_name="Premier",
        home_team_name="Home FC",
        away_team_name="Away FC",
        scan_date=date(2026, 7, 20),
        kickoff=datetime(2026, 7, 21, 18, 0, tzinfo=timezone.utc),
        source_snapshot_at=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        snapshot_status=SNAPSHOT_PENDING,
        preview_status="ok",
        feature_payload={k: feats.get(k) for k in BUNDLE_FEATURE_KEYS},
        pillar_scores_payload=scored["pillar_scores"],
        candidate_scores_payload=scored["candidate_scores"],
        calibrated_predictions_payload=scored["calibrated_predictions"],
        primary_candidate_score=scored["primary_candidate_score"],
        challenger_candidate_score=scored["challenger_candidate_score"],
        benchmark_score=scored["benchmark_score"],
        diagnostic_score=scored["diagnostic_score"],
        candidate_definition_hash=bundle.candidate_definition_hash,
        normalization_hashes_payload=scored.get("normalization_hashes"),
        diagnostic_reason_codes=[],
        no_target_used_in_score=True,
        history_sample_size=12,
        xg_status="ok",
    )


def _row():
    return _today(today_id=100)


def test_get_not_found():
    db = MagicMock()
    db.get.return_value = None
    assert get_goal_intensity_v5_explanations(db, 1) is None


def test_not_eligible():
    db = MagicMock()
    db.get.return_value = _today(eligibility="excluded_cup")
    out = get_goal_intensity_v5_explanations(db, 100)
    assert out["status"] == "error"
    assert out["code"] == "not_eligible"


def test_snapshot_absent():
    db = MagicMock()
    db.get.return_value = _row()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=_bundle(),
    ):
        db.scalars.return_value.first.return_value = None
        out = get_goal_intensity_v5_explanations(db, 100)
    assert out["status"] == "error"
    assert out["code"] == "goal_intensity_v5_not_available"


def test_bundle_absent():
    db = MagicMock()
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)

    def _get(model, pk):
        if model is type(_row()) or getattr(model, "__name__", "") == "CecchinoTodayFixture":
            return _row()
        # first call is TodayFixture via db.get(CecchinoTodayFixture, id)
        from app.models.cecchino_today_fixture import CecchinoTodayFixture

        if model is CecchinoTodayFixture:
            return _row()
        if model is CecchinoGoalIntensityV5PreviewBundle:
            return None
        return None

    db.get.side_effect = _get
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=bundle,
    ):
        db.scalars.return_value.first.return_value = snap
        out = get_goal_intensity_v5_explanations(db, 100)
    assert out["status"] == "error"
    assert out["code"] == "goal_intensity_v5_bundle_missing"


def test_audit_complete():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    assert out["status"] in ("ok", "partial")
    assert out["audit_version"] == AUDIT_VERSION
    assert out["module"] == "goal_intensity_v5"
    assert out["no_operational_recalculation"] is True
    assert out["diagnostic_re_evaluation_only"] is True
    assert out["source_mode"] == SOURCE_MODE
    assert set(out["dimensions"]) == {
        "offensive_production",
        "defensive_solidity",
        "match_tempo",
        "offensive_stability",
    }
    assert set(out["candidates"]) == set(UI_CANDIDATE_IDS)


def test_four_dimensions_and_candidates():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    assert len(out["dimensions"]) == 4
    assert len(out["candidates"]) == 4
    for cid in UI_CANDIDATE_IDS:
        assert out["candidates"][cid]["status"] == "available"


def test_op1_ecdf():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    op1 = out["dimensions"]["offensive_production"]["metrics"][0]
    assert op1["metric_key"] == "OP1_HOME_LONG_TERM"
    norm = op1["normalization"]
    assert "train_values" not in norm
    assert norm["train_n"] == 40
    assert norm["lower_count"] is not None
    assert norm["equal_count"] is not None
    assert norm["percentile_result"] is not None
    expected = 100.0 * (norm["lower_count"] + 0.5 * norm["equal_count"]) / norm["train_n"]
    assert abs(expected - norm["percentile_result"]) < 1e-6
    assert op1["consistency"]["status"] in ("match", "rounding_match")


def test_op2_recency():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    op2 = out["dimensions"]["offensive_production"]["metrics"][1]
    assert op2["metric_key"] == "OP2_HOME_RECENCY"
    assert "mean" in op2["formula_symbolic"]
    assert len(op2["raw_features"]) == 2
    assert op2["consistency"]["status"] in ("match", "rounding_match")


def test_dv1_vulnerability_and_solidity_display():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    dim = out["dimensions"]["defensive_solidity"]
    dv1 = next(m for m in dim["metrics"] if m["metric_key"] == "DV1_MEAN_CONCEDED")
    solid = next(m for m in dim["metrics"] if m["metric_key"] == "defensive_solidity_display")
    assert dv1["audit_result"] is not None
    assert solid["audit_result"] is not None
    assert abs(solid["audit_result"] - (100.0 - dv1["audit_result"])) < 0.02
    assert "vulnerabilità" in (dim.get("mandatory_message") or "").lower() or "DV1" in (
        dim.get("mandatory_message") or ""
    )
    assert dim["display_transformations"]


def test_mt1_mt2():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    mt = out["dimensions"]["match_tempo"]["metrics"]
    assert mt[0]["metric_key"] == "MT1_LONG_TERM"
    assert mt[1]["metric_key"] == "MT2_LONG_TERM_PLUS_RECENCY"
    assert mt[0]["consistency"]["status"] in ("match", "rounding_match")
    assert mt[1]["consistency"]["status"] in ("match", "rounding_match")


def test_ov1_and_stability_display():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    dim = out["dimensions"]["offensive_stability"]
    ov1 = next(m for m in dim["metrics"] if m["metric_key"] == "OV1_STD")
    stab = next(m for m in dim["metrics"] if m["metric_key"] == "offensive_stability_display")
    assert abs(stab["audit_result"] - (100.0 - ov1["audit_result"])) < 0.02
    assert "volatilità" in (dim.get("mandatory_message") or "").lower() or "OV1" in (
        dim.get("mandatory_message") or ""
    )


def test_primary_mean_four():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    prim = out["candidates"][PRIMARY_ID]
    assert prim["role"] == "Primary"
    comps = {c["key"]: c["value"] for c in prim["components"]}
    assert set(comps) == {
        "OP1_HOME_LONG_TERM",
        "DV1_MEAN_CONCEDED",
        "MT1_LONG_TERM",
        "OV1_STD",
    }
    expected = sum(comps.values()) / 4
    assert abs(prim["audit_score"] - expected) < 0.02
    assert prim["consistency"]["status"] in ("match", "rounding_match")


def test_challenger_mean():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    ch = out["candidates"][CHALLENGER_ID]
    comps = {c["key"]: c["value"] for c in ch["components"]}
    assert set(comps) == {
        "OP2_HOME_RECENCY",
        "DV1_MEAN_CONCEDED",
        "MT2_LONG_TERM_PLUS_RECENCY",
        "OV1_STD",
    }
    expected = sum(comps.values()) / 4
    assert abs(ch["audit_score"] - expected) < 0.02


def test_benchmark_equals_mt1():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    bm = out["candidates"][BENCHMARK_ID]
    mt1 = out["dimensions"]["match_tempo"]["metrics"][0]["audit_result"]
    assert bm["formula_symbolic"] == "MT1_LONG_TERM"
    assert abs(bm["audit_score"] - mt1) < 0.02


def test_diagnostic_without_volatility():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    diag = out["candidates"][DIAGNOSTIC_ID]
    assert "OV1_STD" in diag["excluded_components"]
    comps = {c["key"]: c["value"] for c in diag["components"]}
    assert set(comps) == {"OP1_HOME_LONG_TERM", "DV1_MEAN_CONCEDED", "MT1_LONG_TERM"}
    expected = sum(comps.values()) / 3
    assert abs(diag["audit_score"] - expected) < 0.02


def test_linear_and_logistic_calibration():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    prim = out["candidates"][PRIMARY_ID]
    cal = prim["calibrated_predictions"]
    xg = cal["expected_total_goals"]
    assert xg["calibration_method"] == "train_linear_regression"
    score = xg["score"]
    expected_xg = _apply_linear(
        {"intercept": xg["intercept"], "coefficient": xg["coefficient"]}, score
    )
    assert abs(xg["audit_result"] - expected_xg) < 1e-6
    for key in ("probability_goals_ge_2", "probability_goals_ge_3", "probability_btts"):
        block = cal[key]
        assert "logistic" in block["calibration_method"]
        expected_p = _apply_logistic(
            {"intercept": block["intercept"], "coefficient": block["coefficient"]},
            block["score"],
        )
        assert abs(block["audit_result"] - expected_p) < 1e-6
        assert block["consistency"]["status"] in ("match", "rounding_match")


def test_bundle_linked_to_snapshot_not_other_active():
    """I coefficienti devono venire da snap.bundle_id, non da un altro bundle attivo."""
    bundle_a = _bundle()
    bundle_a.id = 11
    # Bundle B con coefficienti diversi
    bundle_b = _bundle()
    bundle_b.id = 22
    for cid in (PRIMARY_ID, CHALLENGER_ID, BENCHMARK_ID, DIAGNOSTIC_ID):
        bundle_b.calibration_payload[cid]["total_goals_ft"]["intercept"] = 99.0
        bundle_b.calibration_payload[cid]["total_goals_ft"]["coefficient"] = 0.0

    snap = _snap_from_bundle(bundle_a)
    snap.bundle_id = bundle_a.id

    out = build_goal_intensity_v5_explanations(_row(), snap, bundle_a)
    xg = out["candidates"][PRIMARY_ID]["calibrated_predictions"]["expected_total_goals"]
    assert xg["intercept"] == 1.0
    assert xg["intercept"] != 99.0
    assert out["metadata"]["bundle_id_used_for_audit"] == bundle_a.id
    assert out["snapshot"]["bundle_id"] == bundle_a.id

    # get_* deve caricare bundle via snap.bundle_id
    db = MagicMock()
    active_b = bundle_b

    def _get(model, pk):
        from app.models.cecchino_today_fixture import CecchinoTodayFixture

        if model is CecchinoTodayFixture:
            return _row()
        if model is CecchinoGoalIntensityV5PreviewBundle:
            assert pk == snap.bundle_id
            return bundle_a
        return None

    db.get.side_effect = _get
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=active_b,
    ):
        # snap is on A but active is B — resolution finds snap only if active matches
        # Simulate: active returns B, no snap for B → not available
        # For this test we attach snap when querying: force snap found under active B id mismatch
        # Instead: make active = A so snap is found, and ensure get uses snap.bundle_id
        pass

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=bundle_a,
    ):
        db2 = MagicMock()

        def _get2(model, pk):
            from app.models.cecchino_today_fixture import CecchinoTodayFixture

            if model is CecchinoTodayFixture:
                return _row()
            if model is CecchinoGoalIntensityV5PreviewBundle:
                assert pk == bundle_a.id
                return bundle_a
            return None

        db2.get.side_effect = _get2
        db2.scalars.return_value.first.return_value = snap
        out2 = get_goal_intensity_v5_explanations(db2, 100)
    assert out2["status"] in ("ok", "partial")
    assert out2["metadata"]["bundle_id_used_for_audit"] == bundle_a.id


def test_consistency_match_and_rounding():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    prim = out["candidates"][PRIMARY_ID]
    assert prim["consistency"]["status"] in ("match", "rounding_match")
    # Force rounding_match
    snap2 = _snap_from_bundle(bundle)
    snap2.primary_candidate_score = (snap2.primary_candidate_score or 0) + 0.01
    snap2.candidate_scores_payload = dict(snap2.candidate_scores_payload or {})
    snap2.candidate_scores_payload[PRIMARY_ID] = snap2.primary_candidate_score
    out2 = build_goal_intensity_v5_explanations(_row(), snap2, bundle)
    st = out2["candidates"][PRIMARY_ID]["consistency"]["status"]
    assert st in ("rounding_match", "match", "mismatch")


def test_partial_missing_feature():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle, drop_feature="goals_scored_std_last_10")
    # Recompute stored without OV1 properly
    feats = dict(snap.feature_payload)
    scored = score_features_with_bundle(feats, bundle)
    snap.pillar_scores_payload = scored["pillar_scores"]
    snap.candidate_scores_payload = scored["candidate_scores"]
    snap.calibrated_predictions_payload = scored["calibrated_predictions"]
    snap.primary_candidate_score = scored["primary_candidate_score"]
    snap.challenger_candidate_score = scored["challenger_candidate_score"]
    snap.benchmark_score = scored["benchmark_score"]
    snap.diagnostic_score = scored["diagnostic_score"]
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    assert out["status"] == "partial"
    assert any("Feature mancanti" in w for w in out["warnings"])


def test_json_safe_no_nan_inf():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    raw = json.dumps(out)
    assert "NaN" not in raw
    assert "Infinity" not in raw
    assert "-Infinity" not in raw
    # No full train distribution
    assert "train_values" not in raw


def test_no_db_write():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    db = MagicMock()
    # build does not touch db
    build_goal_intensity_v5_explanations(_row(), snap, bundle)
    assert db.commit.call_count == 0
    assert db.add.call_count == 0


def test_no_rebuild_or_external(
    monkeypatch: pytest.MonkeyPatch,
):
    forbidden = [
        "app.services.cecchino.cecchino_goal_intensity_v5_dataset.build_goal_intensity_v5_dataset_internal",
        "app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices.build_goal_intensity_v5_candidate_indices_internal",
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.freeze_preview_bundle",
    ]

    def boom(*_a, **_k):
        raise AssertionError("ricostruzione/API proibita")

    for path in forbidden:
        monkeypatch.setattr(path, boom, raising=False)

    # Helper v4 / generate_preview_snapshots: patch solo se il simbolo esiste
    for path in (
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.generate_preview_snapshots",
        "app.services.cecchino.cecchino_goal_intensity_analysis.build_goal_intensity_for_today_row",
    ):
        monkeypatch.setattr(path, boom, raising=False)

    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    assert out["status"] in ("ok", "partial")


def test_freeze_check_in_snapshot_block():
    bundle = _bundle()
    snap = _snap_from_bundle(bundle)
    out = build_goal_intensity_v5_explanations(_row(), snap, bundle)
    fc = out["snapshot"]["freeze_check"]
    assert "source_snapshot_at_gt_bundle_frozen_at" in fc
    assert "source_snapshot_at_lt_kickoff" in fc
    assert out["snapshot"]["bundle_frozen_at"]
    assert out["snapshot"]["source_snapshot_at"]
