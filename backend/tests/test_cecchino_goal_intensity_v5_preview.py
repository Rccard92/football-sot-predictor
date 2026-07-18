"""Test Fase 2A: Preview Intensità Goal v5 (bundle, snapshot, monitoring)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.models.cecchino_goal_intensity_v5_preview import (
    BUNDLE_STATUS_ACTIVE,
    BUNDLE_STATUS_SUPERSEDED,
    PREVIEW_BUNDLE_VERSION,
    SNAPSHOT_COMPLETED,
    SNAPSHOT_LOCKED,
    SNAPSHOT_PENDING,
    CecchinoGoalIntensityV5PreviewBundle,
    CecchinoGoalIntensityV5PreviewSnapshot,
)
from app.models.cecchino_today_fixture import ELIGIBILITY_ELIGIBLE
from app.services.cecchino.cecchino_goal_intensity_analysis import VERSION as V4_VERSION
from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
    TrainEcdf,
    VERSION as CANDIDATE_INDICES_VERSION,
    _candidate_definition_hash,
    _composite_scores,
    _loo_composites,
    _pillar_scores_from_pct,
)
from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
    BENCHMARK_ID,
    BUNDLE_FEATURE_KEYS,
    CHALLENGER_ID,
    DIAGNOSTIC_ID,
    EXPECTED_DEFINITION_HASH,
    EXPECTED_FIXTURE_IDS_HASH,
    EXPECTED_TARGETS_HASH,
    MINIMUM_PROSPECTIVE_MATCHES,
    PRIMARY_ID,
    VERSION,
    _apply_linear,
    _apply_logistic,
    build_prospective_monitoring,
    compute_snapshot_for_today_row,
    freeze_preview_bundle,
    get_active_bundle,
    safe_preview_after_today_scan,
    score_features_with_bundle,
)


def _features(seed: float = 1.2) -> dict[str, float]:
    return {
        "home_goals_scored_avg": seed,
        "home_goals_scored_rolling_5": seed + 0.1,
        "home_goals_conceded_avg": seed * 0.8,
        "away_goals_conceded_avg": seed * 0.7,
        "total_goals_avg": seed * 1.5,
        "total_goals_rolling_5": seed * 1.4,
        "goals_scored_std_last_10": seed * 0.3,
    }


def _bundle(
    *,
    active: bool = True,
    definition_hash: str | None = None,
    first_prospective: date | None = None,
    frozen_at: datetime | None = None,
    retrospective_today_ids: list[int] | None = None,
    retrospective_local_ids: list[int] | None = None,
    retrospective_provider_ids: list[int] | None = None,
) -> CecchinoGoalIntensityV5PreviewBundle:
    freeze = frozen_at or datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    train = [0.4 + i * 0.05 for i in range(40)]
    norm = {
        "normalization_method": "train_ecdf_midrank",
        "fit_split": "train",
        "no_target_used_in_normalization": True,
        "features": {
            k: {
                **TrainEcdf(train).metadata(),
                "train_values": train,
                "tie_handling": "midrank",
                "clipping_rules": "clamp_to_train_min_max",
            }
            for k in BUNDLE_FEATURE_KEYS
        },
    }
    cal = {}
    for cid in (PRIMARY_ID, CHALLENGER_ID, BENCHMARK_ID, DIAGNOSTIC_ID):
        cal[cid] = {
            "total_goals_ft": {
                "calibration_method": "train_linear_regression",
                "intercept": 1.0,
                "coefficient": 0.02,
                "train_n": 40,
            },
            "goals_ge_2": {
                "calibration_method": "train_logistic_regression",
                "intercept": -1.0,
                "coefficient": 0.03,
                "train_n": 40,
            },
            "goals_ge_3": {
                "calibration_method": "train_logistic_regression",
                "intercept": -2.0,
                "coefficient": 0.025,
                "train_n": 40,
            },
            "btts_ft": {
                "calibration_method": "train_logistic_regression",
                "intercept": -0.5,
                "coefficient": 0.02,
                "train_n": 40,
            },
        }
    freeze_iso = freeze.isoformat().replace("+00:00", "Z")
    return CecchinoGoalIntensityV5PreviewBundle(
        id=1,
        version=PREVIEW_BUNDLE_VERSION,
        candidate_indices_version=CANDIDATE_INDICES_VERSION,
        candidate_definition_hash=definition_hash or EXPECTED_DEFINITION_HASH,
        fixture_ids_hash=EXPECTED_FIXTURE_IDS_HASH,
        targets_hash=EXPECTED_TARGETS_HASH,
        normalization_method="train_ecdf_midrank",
        normalization_payload=norm,
        calibration_payload=cal,
        candidate_definitions_payload={
            "primary_candidate": PRIMARY_ID,
            "challenger_candidate": CHALLENGER_ID,
            "benchmark_candidate": BENCHMARK_ID,
            "diagnostic_candidate": DIAGNOSTIC_ID,
            "candidate_definition_frozen_at": "2026-07-19T23:59:59Z",
            "bundle_frozen_at": freeze_iso,
            "prospective_window_started_at": freeze_iso,
            "prospective_start_mode": "strict_after_actual_bundle_freeze",
            "prospective_guard": {
                "retrospective_today_fixture_ids": retrospective_today_ids or [],
                "retrospective_local_fixture_ids": retrospective_local_ids or [],
                "retrospective_provider_fixture_ids": retrospective_provider_ids or [],
                "retrospective_identity_count": len(retrospective_today_ids or [])
                + len(retrospective_local_ids or [])
                + len(retrospective_provider_ids or []),
                "exclusion_mode": "exact_frozen_identity_sets",
                "fixture_ids_hash": EXPECTED_FIXTURE_IDS_HASH,
                "targets_hash": EXPECTED_TARGETS_HASH,
            },
        },
        retrospective_date_from=date(2026, 6, 19),
        retrospective_date_to=date(2026, 7, 19),
        first_prospective_scan_date=first_prospective or freeze.date(),
        frozen_at=freeze,
        status=BUNDLE_STATUS_ACTIVE if active else BUNDLE_STATUS_SUPERSEDED,
        is_active=active,
    )


def _today(
    *,
    today_id: int = 100,
    scan_date: date = date(2026, 7, 20),
    eligibility: str = ELIGIBILITY_ELIGIBLE,
    kickoff: datetime | None = None,
    local_fixture_id: int | None = 50,
    provider_fixture_id: int | None = None,
    updated_at: datetime | None = None,
):
    return SimpleNamespace(
        id=today_id,
        scan_date=scan_date,
        eligibility_status=eligibility,
        kickoff=kickoff or datetime(2026, 7, 21, 18, 0, tzinfo=timezone.utc),
        local_fixture_id=local_fixture_id,
        provider_source="api_football",
        provider_fixture_id=provider_fixture_id if provider_fixture_id is not None else 9000 + today_id,
        competition_id=39,
        home_team_name="Home FC",
        away_team_name="Away FC",
        league_name="Premier",
        updated_at=updated_at or datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc),
        goals_home=None,
        goals_away=None,
        score_fulltime_home=None,
        score_fulltime_away=None,
        match_display_status="upcoming",
        fixture_status="NS",
    )


def _fake_indices_ok() -> dict:
    ecdfs = {k: TrainEcdf([0.5 + i * 0.1 for i in range(20)]) for k in BUNDLE_FEATURE_KEYS}
    scored = []
    for i in range(50):
        feats = _features(0.8 + i * 0.02)
        pct = {k: ecdfs[k].transform(feats[k]) for k in BUNDLE_FEATURE_KEYS}
        pillar = _pillar_scores_from_pct(pct)
        comp = _composite_scores(pillar)
        loo = _loo_composites(pillar)
        scored.append({
            "today_fixture_id": 1000 + i,
            "local_fixture_id": i + 1,
            "provider_fixture_id": 5000 + i,
            "scan_date": "2026-06-19",
            "split": "train" if i < 35 else ("validation" if i < 42 else "test"),
            **pillar,
            **comp,
            **{f"GI_A_{k}": v for k, v in loo.items()},
            "total_goals_ft": 1 + (i % 4),
            "goals_ge_2": int((1 + (i % 4)) >= 2),
            "goals_ge_3": int((1 + (i % 4)) >= 3),
            "btts_ft": i % 2,
            "no_target_used_in_score": True,
            "temporal_fold_candidate": "train" if i < 35 else ("validation" if i < 42 else "test"),
            **feats,
            "sample_size": 12,
            "eligibility_status": "eligible",
        })
    from app.services.cecchino.cecchino_goal_intensity_v5_candidate_indices import (
        evaluate_score_metrics,
    )

    metrics = {
        cid: evaluate_score_metrics(
            scored, cid, bootstrap_iterations=50, random_seed=42, bootstrap_cache={}
        )
        for cid in (PRIMARY_ID, CHALLENGER_ID, BENCHMARK_ID, DIAGNOSTIC_ID)
    }
    return {
        "status": "ok",
        "phase_2a_readiness": {"blocking_issues": [], "ready_for_phase_2a": True},
        "cohort_summary": {
            "fixture_ids_hash": EXPECTED_FIXTURE_IDS_HASH,
            "targets_hash": EXPECTED_TARGETS_HASH,
        },
        "prospective_validation_protocol": {
            "candidate_definition_frozen_at": "2026-07-19T23:59:59Z",
            "first_prospective_scan_date": "2026-07-20",
        },
        "composite_metrics": {
            PRIMARY_ID: metrics[PRIMARY_ID],
            CHALLENGER_ID: metrics[CHALLENGER_ID],
        },
        "baseline_metrics": {BENCHMARK_ID: metrics[BENCHMARK_ID]},
        "research_limitations": {},
        "tempo_baseline_comparison": {},
        "pareto_analysis": {
            "primary_candidate": PRIMARY_ID,
            "challenger_candidate": CHALLENGER_ID,
            "selection_evidence_level": "low",
            "selection_motivation": "transparent",
            "nominal_pareto_front": [PRIMARY_ID],
            "statistically_supported_pareto_front": [],
        },
        "_scored_rows": scored,
        "_dataset": {
            "dataset_rows": [
                {
                    **{k: r[k] for k in BUNDLE_FEATURE_KEYS},
                    "temporal_fold_candidate": r["split"],
                    "sample_size": 12,
                    "eligibility_status": "eligible",
                    "row_feature_safe": True,
                    "core_feature_status": "available",
                    "local_fixture_id": r["local_fixture_id"],
                }
                for r in scored
            ]
        },
    }


# --- Bundle ---


def test_definition_hash_matches_expected():
    assert _candidate_definition_hash() == EXPECTED_DEFINITION_HASH


def test_bundle_not_created_when_readiness_false():
    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_goal_intensity_v5_candidate_indices_internal",
        return_value={
            "status": "ok",
            "phase_2a_readiness": {"blocking_issues": ["x"], "ready_for_phase_2a": False},
        },
    ):
        out = freeze_preview_bundle(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            enforce_expected_hashes=False,
        )
    assert out["status"] == "error"
    assert out["error"] == "readiness_false"
    db.add.assert_not_called()


def test_bundle_hash_mismatch_blocks_activation():
    db = MagicMock()
    payload = _fake_indices_ok()
    payload["cohort_summary"]["fixture_ids_hash"] = "deadbeef"
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_goal_intensity_v5_candidate_indices_internal",
        return_value=payload,
    ):
        out = freeze_preview_bundle(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            enforce_expected_hashes=True,
        )
    assert out["status"] == "error"
    assert out["error"] == "hash_mismatch"
    assert "fixture_ids_hash" in out["mismatches"]


def test_bundle_freeze_saves_ecdf_and_calibration():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    freeze_now = datetime(2026, 7, 18, 14, 30, 0, tzinfo=timezone.utc)
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_goal_intensity_v5_candidate_indices_internal",
        return_value=_fake_indices_ok(),
    ):
        out = freeze_preview_bundle(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            bootstrap_iterations=50,
            enforce_expected_hashes=True,
            now=freeze_now,
        )
    assert out["status"] == "ok"
    assert out["version"] == VERSION
    assert out["version"].endswith("v1_1")
    assert out["candidate_definition_hash"] == EXPECTED_DEFINITION_HASH
    assert out["bundle_frozen_at"] == "2026-07-18T14:30:00Z"
    assert out["frozen_at"] == "2026-07-18T14:30:00Z"
    assert out["first_prospective_scan_date"] == "2026-07-18"
    assert out["candidate_definition_frozen_at"] == "2026-07-19T23:59:59Z"
    assert out["prospective_start_mode"] == "strict_after_actual_bundle_freeze"
    assert out["simple_export_cache_skipped"] is True
    assert db.add.called
    bundle = db.add.call_args[0][0]
    assert isinstance(bundle, CecchinoGoalIntensityV5PreviewBundle)
    assert bundle.frozen_at == freeze_now
    assert bundle.first_prospective_scan_date == date(2026, 7, 18)
    assert bundle.frozen_at.isoformat() != "2026-07-19T23:59:59+00:00"
    guard = bundle.candidate_definitions_payload["prospective_guard"]
    assert guard["retrospective_today_fixture_ids"] == sorted(guard["retrospective_today_fixture_ids"])
    assert guard["retrospective_local_fixture_ids"] == sorted(set(guard["retrospective_local_fixture_ids"]))
    assert len(guard["retrospective_today_fixture_ids"]) == 50
    feats = bundle.normalization_payload["features"]
    for k in BUNDLE_FEATURE_KEYS:
        assert "train_values" in feats[k]
        assert feats[k]["train_n"] > 0
    for cid in (PRIMARY_ID, CHALLENGER_ID, BENCHMARK_ID, DIAGNOSTIC_ID):
        cal = bundle.calibration_payload[cid]
        assert cal["total_goals_ft"]["calibration_method"] == "train_linear_regression"
        assert cal["goals_ge_2"]["calibration_method"] == "train_logistic_regression"


def test_only_one_active_bundle_supersedes_previous():
    db = MagicMock()
    old = _bundle()
    old.is_active = True
    db.scalars.return_value.all.return_value = [old]
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_goal_intensity_v5_candidate_indices_internal",
        return_value=_fake_indices_ok(),
    ):
        out = freeze_preview_bundle(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            bootstrap_iterations=50,
        )
    assert out["status"] == "ok"
    assert old.is_active is False
    assert old.status == BUNDLE_STATUS_SUPERSEDED
    # previous not deleted
    assert not hasattr(db, "delete") or not db.delete.called


# --- Scoring ---


def test_score_uses_bundle_ecdf_no_refit():
    bundle = _bundle()
    scored = score_features_with_bundle(_features(1.5), bundle)
    assert scored["no_target_used_in_score"] is True
    assert 0 <= scored["primary_candidate_score"] <= 100
    assert 0 <= scored["challenger_candidate_score"] <= 100
    assert 0 <= scored["benchmark_score"] <= 100
    assert 0 <= scored["diagnostic_score"] <= 100
    assert PRIMARY_ID in scored["candidate_scores"]
    assert CHALLENGER_ID in scored["candidate_scores"]
    assert BENCHMARK_ID in scored["candidate_scores"]
    assert DIAGNOSTIC_ID in scored["candidate_scores"]


def test_gi_a_formula_mean_of_four_pillars():
    bundle = _bundle()
    feats = _features(1.0)
    scored = score_features_with_bundle(feats, bundle)
    pillar = scored["pillar_scores"]
    expected = np.mean([
        pillar["OP1_HOME_LONG_TERM"],
        pillar["DV1_MEAN_CONCEDED"],
        pillar["MT1_LONG_TERM"],
        pillar["OV1_STD"],
    ])
    assert abs(scored["primary_candidate_score"] - expected) < 1e-6


def test_gi_a_without_volatility_excludes_ov1():
    bundle = _bundle()
    scored = score_features_with_bundle(_features(1.0), bundle)
    pillar = scored["pillar_scores"]
    expected = np.mean([
        pillar["OP1_HOME_LONG_TERM"],
        pillar["DV1_MEAN_CONCEDED"],
        pillar["MT1_LONG_TERM"],
    ])
    assert abs(scored["diagnostic_score"] - expected) < 1e-6


def test_solidity_and_stability_are_inverses():
    bundle = _bundle()
    scored = score_features_with_bundle(_features(1.2), bundle)
    p = scored["pillar_scores"]
    assert abs(p["defensive_solidity_display"] - (100 - p["DV1_MEAN_CONCEDED"])) < 1e-6
    assert abs(p["offensive_stability_display"] - (100 - p["OV1_STD"])) < 1e-6


def test_probabilities_not_score_over_100():
    bundle = _bundle()
    scored = score_features_with_bundle(_features(1.3), bundle)
    cal = scored["calibrated_predictions"][PRIMARY_ID]
    score = scored["primary_candidate_score"]
    assert cal["uses_score_over_100_as_probability"] is False
    assert abs(cal["probability_goals_ge_2"] - score / 100) > 1e-6
    assert 0 < cal["probability_goals_ge_2"] < 1
    assert cal["expected_total_goals"] is not None


def test_frozen_linear_and_logistic_apply():
    assert _apply_linear({"intercept": 1.0, "coefficient": 0.5}, 10) == 6.0
    p = _apply_logistic({"intercept": 0.0, "coefficient": 0.0}, 50)
    assert abs(p - 0.5) < 1e-4


# --- Cohort / snapshot ---


def test_ineligible_and_unknown_excluded():
    bundle = _bundle()
    db = MagicMock()
    for status, code in (("ineligible", "ineligible"), ("unknown", "eligibility_unknown"), ("", "eligibility_unknown")):
        out = compute_snapshot_for_today_row(db, _today(eligibility=status), bundle)
        assert out["status"] == "skipped"
        assert code in out["reason_codes"]


def test_scan_before_prospective_no_longer_blocks_same_day_post_freeze():
    """first_prospective_scan_date non blocca una scansione post-freeze dello stesso giorno."""
    freeze = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    bundle = _bundle(frozen_at=freeze, first_prospective=date(2026, 7, 20))
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    local = SimpleNamespace(id=50, home_team_id=1, away_team_id=2, api_fixture_id=99)
    db.get.return_value = local
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.extract_features_for_local_fixture",
        return_value=(
            _features(),
            {
                "sample_size": 12,
                "xg_status": "available",
                "current_fixture_included": False,
                "future_fixture_included": False,
            },
        ),
    ):
        out = compute_snapshot_for_today_row(
            db,
            _today(
                scan_date=date(2026, 7, 20),
                updated_at=freeze + timedelta(seconds=1),
            ),
            bundle,
            now=freeze + timedelta(minutes=5),
        )
    assert out["status"] == "created"


def test_snapshot_before_freeze_excluded():
    freeze = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    bundle = _bundle(frozen_at=freeze)
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    out = compute_snapshot_for_today_row(
        db,
        _today(updated_at=freeze - timedelta(seconds=1)),
        bundle,
        now=freeze + timedelta(hours=1),
    )
    assert out["status"] == "skipped"
    assert "snapshot_not_after_bundle_freeze" in out["reason_codes"]


def test_identity_failed_when_local_missing():
    bundle = _bundle()
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    db.get.return_value = None
    out = compute_snapshot_for_today_row(
        db, _today(local_fixture_id=None), bundle, now=datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
    )
    assert out["status"] == "error"
    assert "identity_failed" in out["reason_codes"]


def test_xg_missing_does_not_exclude():
    bundle = _bundle()
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    local = SimpleNamespace(id=50, home_team_id=1, away_team_id=2, api_fixture_id=99)
    db.get.return_value = local
    feats = _features(1.1)
    leak = {
        "sample_size": 15,
        "xg_status": "missing",
        "current_fixture_included": False,
        "future_fixture_included": False,
    }
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.extract_features_for_local_fixture",
        return_value=(feats, leak),
    ):
        out = compute_snapshot_for_today_row(
            db, _today(), bundle, now=datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
        )
    assert out["status"] == "created"
    snap = db.add.call_args[0][0]
    assert snap.xg_status == "missing"
    assert snap.no_target_used_in_score is True


def test_snapshot_before_kickoff_and_idempotent_update():
    bundle = _bundle()
    db = MagicMock()
    existing = CecchinoGoalIntensityV5PreviewSnapshot(
        id=9,
        bundle_id=1,
        today_fixture_id=100,
        revision_count=1,
        first_computed_at=datetime(2026, 7, 20, 8, tzinfo=timezone.utc),
        locked_at=None,
        snapshot_status=SNAPSHOT_PENDING,
    )
    db.scalars.return_value.first.return_value = existing
    local = SimpleNamespace(id=50, home_team_id=1, away_team_id=2, api_fixture_id=99)
    db.get.return_value = local
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.extract_features_for_local_fixture",
        return_value=(_features(), {"sample_size": 12, "xg_status": "available", "current_fixture_included": False, "future_fixture_included": False}),
    ):
        out = compute_snapshot_for_today_row(
            db, _today(), bundle, now=datetime(2026, 7, 20, 12, tzinfo=timezone.utc)
        )
    assert out["status"] == "updated"
    assert existing.revision_count == 2


def test_lock_after_kickoff_no_score_recompute():
    bundle = _bundle()
    db = MagicMock()
    kickoff = datetime(2026, 7, 20, 15, tzinfo=timezone.utc)
    existing = CecchinoGoalIntensityV5PreviewSnapshot(
        id=9,
        bundle_id=1,
        today_fixture_id=100,
        kickoff=kickoff,
        primary_candidate_score=55.0,
        locked_at=None,
        result_attached_at=None,
        snapshot_status=SNAPSHOT_PENDING,
        local_fixture_id=50,
    )
    db.scalars.return_value.first.return_value = existing
    today = _today(kickoff=kickoff)
    out = compute_snapshot_for_today_row(
        db, today, bundle, now=kickoff + timedelta(minutes=1)
    )
    assert out["status"] == "locked"
    assert existing.locked_at is not None
    assert existing.primary_candidate_score == 55.0
    assert existing.snapshot_status == SNAPSHOT_LOCKED


def test_result_attach_without_score_recompute():
    bundle = _bundle()
    db = MagicMock()
    snap = CecchinoGoalIntensityV5PreviewSnapshot(
        id=9,
        bundle_id=1,
        today_fixture_id=100,
        kickoff=datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
        locked_at=datetime(2026, 7, 20, 12, tzinfo=timezone.utc),
        primary_candidate_score=61.0,
        result_attached_at=None,
        local_fixture_id=50,
        snapshot_status=SNAPSHOT_LOCKED,
    )
    db.scalars.return_value.first.return_value = snap
    today = _today(kickoff=snap.kickoff)
    today.goals_home = 2
    today.goals_away = 1
    today.match_display_status = "finished"
    out = compute_snapshot_for_today_row(
        db, today, bundle, now=datetime(2026, 7, 20, 14, tzinfo=timezone.utc)
    )
    assert out["status"] == "locked"
    assert out["result_attached"] is True
    assert snap.total_goals_ft == 3
    assert snap.goals_ge_2 == 1
    assert snap.btts_ft == 1
    assert snap.primary_candidate_score == 61.0
    assert snap.snapshot_status == SNAPSHOT_COMPLETED
    assert snap.result_attached_at is not None


def test_targets_null_before_result():
    snap = CecchinoGoalIntensityV5PreviewSnapshot(
        bundle_id=1,
        today_fixture_id=1,
        goals_home_ft=None,
        total_goals_ft=None,
        result_attached_at=None,
    )
    assert snap.total_goals_ft is None
    assert snap.result_attached_at is None


# --- Today integration ---


def test_preview_error_does_not_raise():
    db = MagicMock()
    db.get.side_effect = RuntimeError("boom")
    out = safe_preview_after_today_scan(db, 123)
    assert out["status"] == "error"
    assert out["eligibility_unchanged"] is True


def test_no_external_api_in_preview_module():
    import inspect
    import app.services.cecchino.cecchino_goal_intensity_v5_preview as mod

    src = inspect.getsource(mod)
    assert "api-football" not in src.lower()
    assert "requests.get" not in src
    assert "httpx" not in src


# --- Monitoring ---


def test_monitoring_provisional_under_200():
    db = MagicMock()
    bundle = _bundle()
    completed = []
    for i in range(10):
        completed.append(
            CecchinoGoalIntensityV5PreviewSnapshot(
                id=i,
                bundle_id=1,
                today_fixture_id=1000 + i,
                primary_candidate_score=40 + i,
                challenger_candidate_score=41 + i,
                benchmark_score=39 + i,
                diagnostic_score=42 + i,
                candidate_scores_payload={
                    PRIMARY_ID: 40 + i,
                    CHALLENGER_ID: 41 + i,
                    BENCHMARK_ID: 39 + i,
                    DIAGNOSTIC_ID: 42 + i,
                },
                total_goals_ft=2 + (i % 3),
                result_attached_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
                no_target_used_in_score=True,
            )
        )
    db.scalars.return_value.all.return_value = completed
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_active_bundle",
        return_value=bundle,
    ):
        mon = build_prospective_monitoring(db, bundle)
    assert mon["status"] == "collecting_prospective_data"
    assert mon["completed_prospective_matches"] == 10
    assert mon["phase_2b_readiness"]["recommended_next_step"] == "continue_prospective_monitoring"
    assert "GI_B_vs_GI_A" in mon["comparisons"]
    assert "MT1_vs_GI_A" in mon["comparisons"]
    assert "without_volatility_vs_GI_A" in mon["comparisons"]


def test_monitoring_minimum_reached_not_auto_replace():
    assert MINIMUM_PROSPECTIVE_MATCHES == 200
    readiness_next = "continue_prospective_monitoring"
    # below 200 always continue
    assert readiness_next == "continue_prospective_monitoring"


def test_v4_unchanged_constant():
    assert VERSION.startswith("cecchino_goal_intensity_v5_preview")
    assert V4_VERSION  # still imported / available
    assert "preview" in VERSION


def test_get_active_bundle_filters():
    db = MagicMock()
    db.scalars.return_value.first.return_value = _bundle()
    b = get_active_bundle(db)
    assert b is not None
    assert b.is_active is True


@pytest.mark.parametrize(
    "kind",
    [
        "preview_summary",
        "preview_snapshots",
        "preview_completed_results",
        "preview_candidate_monitoring",
        "preview_calibration",
        "preview_bundle_definition",
    ],
)
def test_export_kinds_registered(kind):
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import preview_export_filename

    name = preview_export_filename(kind)  # type: ignore[arg-type]
    assert "preview" in name


def test_targets_hash_and_fixture_hash_constants():
    assert len(EXPECTED_FIXTURE_IDS_HASH) == 64
    assert len(EXPECTED_TARGETS_HASH) == 64
    assert EXPECTED_DEFINITION_HASH == _candidate_definition_hash()


def test_bundle_immutable_fields_after_activation_shape():
    b = _bundle()
    assert b.status == BUNDLE_STATUS_ACTIVE
    assert b.normalization_method == "train_ecdf_midrank"
    assert b.retrospective_date_to == date(2026, 7, 19)
    assert b.first_prospective_scan_date == date(2026, 7, 20)


def test_eligible_today_included_path_creates_snapshot():
    bundle = _bundle()
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    local = SimpleNamespace(id=50, home_team_id=1, away_team_id=2, api_fixture_id=99)
    db.get.return_value = local
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.extract_features_for_local_fixture",
        return_value=(
            _features(),
            {
                "sample_size": 20,
                "xg_status": "partial",
                "current_fixture_included": False,
                "future_fixture_included": False,
            },
        ),
    ):
        out = compute_snapshot_for_today_row(
            db,
            _today(eligibility=ELIGIBILITY_ELIGIBLE),
            bundle,
            now=datetime(2026, 7, 20, 11, tzinfo=timezone.utc),
        )
    assert out["status"] == "created"
    snap = db.add.call_args[0][0]
    assert snap.eligibility_status == ELIGIBILITY_ELIGIBLE
    assert snap.primary_candidate_score is not None


def test_feature_incomplete_diagnosed():
    bundle = _bundle()
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    db.get.return_value = SimpleNamespace(id=50, home_team_id=1, away_team_id=2, api_fixture_id=1)
    incomplete = {k: None for k in BUNDLE_FEATURE_KEYS}
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.extract_features_for_local_fixture",
        return_value=(
            incomplete,
            {
                "sample_size": 3,
                "xg_status": "missing",
                "current_fixture_included": False,
                "future_fixture_included": False,
            },
        ),
    ):
        out = compute_snapshot_for_today_row(
            db, _today(), bundle, now=datetime(2026, 7, 20, 11, tzinfo=timezone.utc)
        )
    assert out["status"] == "error"
    assert "feature_incomplete" in out["reason_codes"]


def test_snapshot_after_kickoff_without_existing_skipped():
    bundle = _bundle()
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    ko = datetime(2026, 7, 20, 10, tzinfo=timezone.utc)
    out = compute_snapshot_for_today_row(
        db, _today(kickoff=ko), bundle, now=ko + timedelta(minutes=5)
    )
    assert out["status"] == "skipped"
    assert "snapshot_after_kickoff" in out["reason_codes"]


def test_gi_b_uses_recency_pillars():
    bundle = _bundle()
    scored = score_features_with_bundle(_features(1.4), bundle)
    p = scored["pillar_scores"]
    expected = np.mean([
        p["OP2_HOME_RECENCY"],
        p["DV1_MEAN_CONCEDED"],
        p["MT2_LONG_TERM_PLUS_RECENCY"],
        p["OV1_STD"],
    ])
    assert abs(scored["challenger_candidate_score"] - expected) < 1e-6


def test_mt1_equals_pillar_mt1():
    bundle = _bundle()
    scored = score_features_with_bundle(_features(0.9), bundle)
    assert scored["benchmark_score"] == scored["pillar_scores"]["MT1_LONG_TERM"]


def test_unique_constraint_declared():
    args = CecchinoGoalIntensityV5PreviewSnapshot.__table_args__
    names = [getattr(c, "name", None) for c in args if hasattr(c, "name")]
    assert "uq_gi_v5_preview_bundle_today_fixture" in names


def test_phase_2b_not_automatic_under_minimum():
    db = MagicMock()
    bundle = _bundle()
    db.scalars.return_value.all.return_value = []
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_active_bundle",
        return_value=bundle,
    ):
        mon = build_prospective_monitoring(db, bundle)
    assert mon["phase_2b_readiness"]["recommended_next_step"] == "continue_prospective_monitoring"
    assert mon["phase_2b_readiness"]["minimum_sample_reached"] is False


def test_list_and_detail_require_active_bundle():
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import (
        get_preview_detail,
        list_preview_snapshots,
    )

    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_active_bundle",
        return_value=None,
    ):
        assert list_preview_snapshots(db)["error"] == "bundle_missing"
        assert get_preview_detail(db, 1)["error"] == "bundle_missing"


def test_refresh_without_bundle_errors():
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import refresh_preview

    db = MagicMock()
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_active_bundle",
        return_value=None,
    ):
        out = refresh_preview(db)
    assert out["status"] == "error"
    assert out["error"] == "bundle_missing"


def test_no_betting_fields_in_detail_payload():
    from app.services.cecchino.cecchino_goal_intensity_v5_preview import get_preview_detail

    db = MagicMock()
    bundle = _bundle()
    snap = CecchinoGoalIntensityV5PreviewSnapshot(
        id=1,
        bundle_id=1,
        today_fixture_id=42,
        scan_date=date(2026, 7, 20),
        primary_candidate_score=50,
        challenger_candidate_score=51,
        benchmark_score=49,
        diagnostic_score=52,
        candidate_scores_payload={},
        calibrated_predictions_payload={},
        pillar_scores_payload={},
        snapshot_status=SNAPSHOT_PENDING,
        preview_status="ok",
        no_target_used_in_score=True,
    )
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.get_active_bundle",
        return_value=bundle,
    ):
        db.scalars.return_value.first.return_value = snap
        with patch(
            "app.services.cecchino.cecchino_goal_intensity_v5_preview._bundle_summary",
            return_value={"bundle_id": 1},
        ):
            detail = get_preview_detail(db, 42)
    blob = str(detail)
    for forbidden in ("over_consigliato", "under_consigliato", "roi", "value_bet", "semaforo"):
        assert forbidden not in blob.lower()
    assert detail["no_betting_signals"] is True
    assert "Preview research" in detail["banner"]


def test_cache_skipped_documented_in_freeze_report():
    db = MagicMock()
    db.scalars.return_value.all.return_value = []
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.build_goal_intensity_v5_candidate_indices_internal",
        return_value=_fake_indices_ok(),
    ):
        out = freeze_preview_bundle(
            db,
            date_from=date(2026, 6, 19),
            date_to=date(2026, 7, 19),
            bootstrap_iterations=50,
        )
    assert out["simple_export_cache_skipped"] is True
    assert "memoria" in (out.get("simple_export_cache_reason") or "").lower()


def test_snapshot_equal_to_freeze_excluded():
    freeze = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    bundle = _bundle(frozen_at=freeze)
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    out = compute_snapshot_for_today_row(
        db, _today(updated_at=freeze), bundle, now=freeze + timedelta(minutes=1)
    )
    assert out["status"] == "skipped"
    assert "snapshot_not_after_bundle_freeze" in out["reason_codes"]


def test_retrospective_today_id_excluded():
    bundle = _bundle(retrospective_today_ids=[100])
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    out = compute_snapshot_for_today_row(db, _today(today_id=100), bundle)
    assert out["status"] == "skipped"
    assert "retrospective_fixture_excluded" in out["reason_codes"]


def test_retrospective_local_id_excluded():
    bundle = _bundle(retrospective_local_ids=[50])
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    out = compute_snapshot_for_today_row(db, _today(today_id=999, local_fixture_id=50), bundle)
    assert out["status"] == "skipped"
    assert "retrospective_fixture_excluded" in out["reason_codes"]


def test_retrospective_provider_id_excluded():
    bundle = _bundle(retrospective_provider_ids=[7777])
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    out = compute_snapshot_for_today_row(
        db, _today(today_id=999, local_fixture_id=88, provider_fixture_id=7777), bundle
    )
    assert out["status"] == "skipped"
    assert "retrospective_fixture_excluded" in out["reason_codes"]


def test_new_match_not_in_retrospective_admitted():
    freeze = datetime(2026, 7, 20, 8, 0, tzinfo=timezone.utc)
    bundle = _bundle(
        frozen_at=freeze,
        retrospective_today_ids=[1, 2],
        retrospective_local_ids=[10, 11],
        retrospective_provider_ids=[20, 21],
    )
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    local = SimpleNamespace(id=99, home_team_id=1, away_team_id=2, api_fixture_id=30)
    db.get.return_value = local
    with patch(
        "app.services.cecchino.cecchino_goal_intensity_v5_preview.extract_features_for_local_fixture",
        return_value=(
            _features(),
            {
                "sample_size": 12,
                "xg_status": "missing",
                "current_fixture_included": False,
                "future_fixture_included": False,
            },
        ),
    ):
        out = compute_snapshot_for_today_row(
            db,
            _today(
                today_id=500,
                local_fixture_id=99,
                provider_fixture_id=30,
                updated_at=freeze + timedelta(seconds=5),
            ),
            bundle,
            now=freeze + timedelta(minutes=1),
        )
    assert out["status"] == "created"


def test_no_hardcoded_july_20_dependency_in_admission():
    import inspect
    import app.services.cecchino.cecchino_goal_intensity_v5_preview as mod

    src = inspect.getsource(mod.compute_snapshot_for_today_row)
    assert "2026-07-20" not in src
    assert "scan_before_prospective" not in src


def test_version_is_v1_1():
    assert VERSION == "cecchino_goal_intensity_v5_preview_v1_1"
    assert PREVIEW_BUNDLE_VERSION == VERSION
