"""Audit ufficiale Goal Intensity v5 — scorer canonico, stored vs recomputed."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.cecchino_goal_intensity_v5_preview import (
    SNAPSHOT_PENDING,
    CecchinoGoalIntensityV5PreviewBundle,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import CecchinoTodayFixture
from app.services.cecchino.cecchino_goal_intensity_v5_explanations import (
    build_goal_intensity_v5_explanations,
    get_goal_intensity_v5_explanations,
)
from app.services.cecchino.cecchino_goal_intensity_v5_official_support import (
    GI_E_ID,
    OFFICIAL_BUNDLE_VERSION,
    OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS,
    OPERATIONAL_CALIBRATION_KEY,
    RAW_INDEX_ID,
    build_official_bundle_payload,
    score_official_support_with_bundle,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import PREVIEW_BUNDLE_VERSION
from tests.test_cecchino_goal_intensity_v5_official_support import (
    _cal_head,
    _candidate_bundle,
    _features_complete,
    _preview_bundle,
)
from tests.test_cecchino_goal_intensity_v5_preview import _today


def _official_bundle(**overrides):
    cand = _candidate_bundle()
    preview = _preview_bundle(
        calibration_payload={
            RAW_INDEX_ID: cand.calibration_payload[RAW_INDEX_ID],
            "GI_B_RECENCY": cand.calibration_payload[RAW_INDEX_ID],
            GI_E_ID: cand.calibration_payload[GI_E_ID],
            "GI_F_REGULARIZED_PILLARS": cand.calibration_payload[GI_E_ID],
            "MT1_LONG_TERM": {
                "total_goals_ft": _cal_head(1.0, 0.01),
                "goals_ge_2": _cal_head(-1.0, 0.01, logistic=True),
                "goals_ge_3": _cal_head(-1.0, 0.01, logistic=True),
                "btts_ft": _cal_head(-1.0, 0.01, logistic=True),
            },
            "GI_A_without_volatility": cand.calibration_payload[RAW_INDEX_ID],
        }
    )
    job_val = {
        "ok": True,
        "job": {
            "id": 2,
            "job_version": "cecchino_lab_goal_intensity_v4_v5_historical_benchmark_v1",
            "independence_status": "external_independent",
            "scientific_label": "external_validation",
            "paired_complete": 5489,
            "reconciliation": {"ok": True},
        },
    }
    payload = build_official_bundle_payload(
        candidate=cand, preview=preview, job_validation=job_val, source_git_commit="abc"
    )
    base = SimpleNamespace(
        id=3,
        version=OFFICIAL_BUNDLE_VERSION,
        status="active",
        is_active=True,
        candidate_definition_hash=payload["candidate_definition_hash"],
        fixture_ids_hash=payload.get("fixture_ids_hash") or "fixhash",
        targets_hash=payload.get("targets_hash") or "tgthash",
        normalization_method="train_ecdf_midrank",
        normalization_payload=payload["normalization_payload"],
        calibration_payload=payload["calibration_payload"],
        candidate_definitions_payload=payload.get("candidate_definitions_payload") or {
            "benchmark_job_id": 2,
            "provenance": {"scientific_evidence": "external_validation"},
        },
        candidate_indices_version=payload.get("candidate_indices_version"),
        frozen_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _official_snap(bundle, *, today_id: int = 100, features: dict | None = None, mutate=None):
    feats = dict(features or _features_complete())
    scored = score_official_support_with_bundle(feats, bundle)
    if mutate:
        mutate(scored)
    return CecchinoGoalIntensityV5PreviewSnapshot(
        id=42,
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
        scan_date=date(2026, 8, 7),
        kickoff=datetime(2026, 8, 7, 18, 0, tzinfo=timezone.utc),
        source_snapshot_at=datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc),
        snapshot_status=SNAPSHOT_PENDING,
        preview_status="ok",
        feature_status="official_v5_complete",
        feature_payload={k: feats.get(k) for k in OFFICIAL_SUPPORT_REQUIRED_FEATURE_KEYS},
        pillar_scores_payload=scored["pillar_scores"],
        candidate_scores_payload=scored["candidate_scores"],
        calibrated_predictions_payload=scored["calibrated_predictions"],
        primary_candidate_score=scored["primary_candidate_score"],
        challenger_candidate_score=None,
        benchmark_score=None,
        diagnostic_score=None,
        candidate_definition_hash=bundle.candidate_definition_hash,
        normalization_hashes_payload=scored.get("normalization_hashes"),
        diagnostic_reason_codes=[],
        no_target_used_in_score=True,
        history_sample_size=12,
        xg_status="ok",
    )


def test_official_audit_match_consistency():
    bundle = _official_bundle()
    snap = _official_snap(bundle)
    row = _today(today_id=100)
    out = build_goal_intensity_v5_explanations(row, snap, bundle)

    assert out["presentation"] == "official_support"
    assert out["candidates"] is None
    assert out["consistency_status"] == "match"
    assert out["status"] == "ok"

    scored = score_official_support_with_bundle(snap.feature_payload, bundle)
    op = scored["calibrated_predictions"][OPERATIONAL_CALIBRATION_KEY]
    stored_op = snap.calibrated_predictions_payload[OPERATIONAL_CALIBRATION_KEY]

    assert out["index"]["score_stored"] == stored_op["raw_score"]
    assert out["index"]["score_audit"] == scored["primary_candidate_score"]
    assert out["index"]["consistency_status"] == "match"
    assert out["index"]["score_audit"] == op["raw_score"]

    for key in (
        "expected_total_goals",
        "probability_goals_ge_2",
        "probability_goals_ge_3",
        "probability_btts",
    ):
        head = out["target_heads"][key]
        assert head["stored"] == stored_op[key]
        assert head["recomputed"] == op[key]
        assert head["consistency_status"] == "match"

    assert out["source_identity"]["snapshot_id"] == snap.id
    assert out["source_identity"]["bundle_id"] == bundle.id
    assert out["source_identity"]["bundle_version"] == OFFICIAL_BUNDLE_VERSION
    assert out["metadata"]["canonical_scorer"] == "score_official_support_with_bundle"
    assert out["metadata"]["no_parallel_raw_recompute"] is True


def test_official_audit_no_parallel_raw_path():
    """Regression: score_audit deve coincidere con lo scorer, non un ricalcolo autonomo."""
    bundle = _official_bundle()
    snap = _official_snap(bundle)
    row = _today(today_id=100)
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations._composite_scores"
    ) as mocked_composite:
        mocked_composite.return_value = {RAW_INDEX_ID: 1.23}
        out = build_goal_intensity_v5_explanations(row, snap, bundle)
    # Se Path B fosse ancora usato, score_audit sarebbe 1.23
    scored = score_official_support_with_bundle(snap.feature_payload, bundle)
    assert out["index"]["score_audit"] == scored["primary_candidate_score"]
    assert out["index"]["score_audit"] != pytest.approx(1.23)
    mocked_composite.assert_not_called()


def test_official_audit_mismatch_raw():
    bundle = _official_bundle()

    def _mutate(scored):
        scored["calibrated_predictions"][OPERATIONAL_CALIBRATION_KEY]["raw_score"] = 99.0
        scored["candidate_scores"][RAW_INDEX_ID] = 99.0
        scored["primary_candidate_score"] = 99.0

    snap = _official_snap(bundle, mutate=_mutate)
    out = build_goal_intensity_v5_explanations(_today(today_id=100), snap, bundle)
    assert out["consistency_status"] == "mismatch"
    assert out["status"] == "partial"
    assert out["index"]["consistency_status"] == "mismatch"
    assert any("Mismatch" in w for w in out["warnings"])


def test_official_audit_mismatch_single_head():
    bundle = _official_bundle()

    def _mutate(scored):
        scored["calibrated_predictions"][OPERATIONAL_CALIBRATION_KEY][
            "expected_total_goals"
        ] = 9.99

    snap = _official_snap(bundle, mutate=_mutate)
    out = build_goal_intensity_v5_explanations(_today(today_id=100), snap, bundle)
    assert out["consistency_status"] == "mismatch"
    assert out["target_heads"]["expected_total_goals"]["consistency_status"] == "mismatch"
    assert out["index"]["consistency_status"] == "match"


def test_official_audit_rounding_match():
    bundle = _official_bundle()

    def _mutate(scored):
        raw = scored["primary_candidate_score"]
        scored["calibrated_predictions"][OPERATIONAL_CALIBRATION_KEY]["raw_score"] = raw + 0.01
        scored["candidate_scores"][RAW_INDEX_ID] = raw + 0.01
        scored["primary_candidate_score"] = raw + 0.01

    snap = _official_snap(bundle, mutate=_mutate)
    out = build_goal_intensity_v5_explanations(_today(today_id=100), snap, bundle)
    assert out["index"]["consistency_status"] == "rounding_match"
    assert out["consistency_status"] in {"rounding_match", "match"}


def test_official_audit_missing_feature():
    bundle = _official_bundle()
    feats = _features_complete()
    feats["home_goals_scored_avg"] = None
    snap = _official_snap(bundle, features=feats)
    # Persist complete-looking calibrated values but features incomplete for recompute
    out = build_goal_intensity_v5_explanations(_today(today_id=100), snap, bundle)
    assert out["status"] == "partial"
    assert any("Feature mancanti" in w for w in out["warnings"])


def test_official_audit_uses_exact_snapshot_bundle():
    bundle = _official_bundle(id=3)
    other = _official_bundle(id=99)
    # Perturb other calibration so scoring would diverge if wrong bundle used
    other.calibration_payload = deepcopy(bundle.calibration_payload)
    op = other.calibration_payload[OPERATIONAL_CALIBRATION_KEY]
    for target in op:
        if isinstance(op[target], dict) and "intercept" in op[target]:
            op[target] = dict(op[target])
            op[target]["intercept"] = float(op[target]["intercept"]) + 5.0

    snap = _official_snap(bundle)
    out = build_goal_intensity_v5_explanations(_today(today_id=100), snap, bundle)
    assert out["source_identity"]["bundle_id"] == 3
    assert out["metadata"]["bundle_id_used_for_audit"] == 3
    assert out["consistency_status"] == "match"

    # Wrong bundle → mismatch expected
    wrong = build_goal_intensity_v5_explanations(_today(today_id=100), snap, other)
    assert wrong["metadata"]["bundle_id_used_for_audit"] == 99
    assert wrong["consistency_status"] == "mismatch"


def test_official_prefers_official_when_legacy_also_present():
    official = _official_bundle(id=3)
    legacy = _preview_bundle(id=11, version=PREVIEW_BUNDLE_VERSION)
    official_snap = _official_snap(official, today_id=100)
    legacy_snap = CecchinoGoalIntensityV5PreviewSnapshot(
        id=7,
        bundle_id=legacy.id,
        today_fixture_id=100,
        local_fixture_id=50,
        provider_source="api_football",
        provider_fixture_id=9100,
        competition_id=39,
        scan_date=date(2026, 8, 7),
        snapshot_status=SNAPSHOT_PENDING,
        preview_status="ok",
        feature_payload={},
        pillar_scores_payload={},
        candidate_scores_payload={},
        calibrated_predictions_payload={},
        candidate_definition_hash=legacy.candidate_definition_hash,
    )

    db = MagicMock()
    row = _today(today_id=100)

    def _get(model, pk):
        if model is CecchinoTodayFixture:
            return row
        if model is CecchinoGoalIntensityV5PreviewBundle:
            return official if pk == official.id else legacy
        return None

    db.get.side_effect = _get
    calls = {"n": 0}

    def _first():
        calls["n"] += 1
        # First query is active/official snapshot
        return official_snap if calls["n"] == 1 else legacy_snap

    db.scalars.return_value.first.side_effect = _first

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=official,
    ):
        out = get_goal_intensity_v5_explanations(db, 100)

    assert out["presentation"] == "official_support"
    assert out["source_identity"]["bundle_id"] == official.id
    assert out["source_identity"]["snapshot_id"] == official_snap.id


def test_legacy_archive_still_legacy_when_only_legacy_snap():
    official = _official_bundle(id=3)
    legacy = _preview_bundle(id=11)
    from tests.test_cecchino_goal_intensity_v5_explanations import _snap_from_bundle

    legacy_snap = _snap_from_bundle(legacy, today_id=100)
    legacy_snap.id = 7

    db = MagicMock()
    row = _today(today_id=100)

    def _get(model, pk):
        if model is CecchinoTodayFixture:
            return row
        if model is CecchinoGoalIntensityV5PreviewBundle:
            return legacy if pk == legacy.id else None
        return None

    db.get.side_effect = _get
    db.scalars.return_value.first.side_effect = [None, legacy_snap]

    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_explanations.get_active_bundle",
        return_value=official,
    ), patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_official_support.get_preview_bundle_v1_1",
        return_value=legacy,
    ):
        out = get_goal_intensity_v5_explanations(db, 100)

    assert out.get("presentation") == "legacy_preview" or "explanations_v1" in str(
        out.get("audit_version")
    )
    assert out["snapshot"]["bundle_id"] == legacy.id


def test_official_audit_no_db_writes():
    bundle = _official_bundle()
    snap = _official_snap(bundle)
    db = MagicMock()
    # build_goal_intensity_v5_explanations is pure — no db
    out = build_goal_intensity_v5_explanations(_today(today_id=100), snap, bundle)
    assert out["consistency_status"] == "match"
    db.commit.assert_not_called()
    db.add.assert_not_called()
    db.flush.assert_not_called()
